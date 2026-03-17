"""Application service orchestrating build execution."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

from ..core.queue_manager import queue_manager
from ..domain import BuildJob, BuildLogEntry, BuildProgress, BuildRequestData, BuildStatus, StageStatus
from ..infrastructure import BuildLogger, CommandRunner, SetupExecutor
from ..infrastructure.command_runner import CommandCancelledError
from .build_environment import BuildEnvironmentAssembler
from .build_repository import BuildRepository
from .build_status_presenter import BuildStatusPresenter
from .config_diagnostics import ConfigDiagnostics
from .validators import BuildRequestValidator
from .version_resolver import VersionResolver

logger = logging.getLogger(__name__)

MAX_LOG_LINES = 500
KEEP_LOG_LINES = 400


class BuildOrchestrator:
    """Coordinates validated build requests end-to-end."""

    def __init__(
        self,
        repository: BuildRepository,
        validator: BuildRequestValidator,
        version_resolver: VersionResolver,
        command_runner: CommandRunner,
        config_diagnostics: ConfigDiagnostics,
        environment_assembler: BuildEnvironmentAssembler,
        setup_executor: SetupExecutor,
        status_presenter: BuildStatusPresenter,
    ) -> None:
        self.repository = repository
        self.validator = validator
        self.version_resolver = version_resolver
        self.command_runner = command_runner
        self.config_diagnostics = config_diagnostics
        self.environment_assembler = environment_assembler
        self.setup_executor = setup_executor
        self.status_presenter = status_presenter
        self.build_loggers: Dict[str, BuildLogger] = {}

    def start_build(self, request: BuildRequestData) -> str:
        validated_request = self.validator.validate(request)
        diagnostic = self.config_diagnostics.get_build_diagnostics(validated_request)
        if not diagnostic.ready:
            raise ValueError(
                f"Missing required environment variables for build: {', '.join(diagnostic.missing)}"
            )
        branch_name = validated_request.branch_name or os.environ.get(
            f"{validated_request.flavor.upper()}_BRANCH_NAME", "develop"
        )
        build_id = self._generate_build_id(validated_request.flavor, validated_request.platform)
        queue_key = build_id

        job = BuildJob.create(build_id, validated_request, branch_name, queue_key)
        job.mark_stage_completed("request_validated", "Build request validated")
        self.repository.save(job)
        self.build_loggers[build_id] = BuildLogger(build_id)

        thread = threading.Thread(
            target=lambda: queue_manager.execute_with_queue(
                queue_key, build_id, self._run_pipeline, job, validated_request
            ),
            daemon=True,
        )
        thread.start()
        return build_id

    def get_build_status(self, build_id: str) -> Optional[Dict]:
        job = self.repository.get(build_id)
        if not job:
            return None

        logger_instance = self.build_loggers.get(build_id)
        return self.status_presenter.detail(
            job,
            logger_instance.get_log_path() if logger_instance else None,
        )

    def list_builds(self) -> list[Dict]:
        builds = []
        for job in self.repository.list_all():
            builds.append(self.status_presenter.summary(job))
        return builds

    def cancel_build(self, build_id: str) -> Optional[Dict]:
        job = self.repository.get(build_id)
        if not job:
            return None

        if job.status in {BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELED}:
            return self.get_build_status(build_id)

        with job.lock:
            job.mark_canceled("Build canceled by user request")

        self._log(job, f"[{job.build_id}] 🛑 Cancellation requested")
        self._terminate_processes(job)
        self.repository.save(job)
        return self.get_build_status(build_id)

    def _generate_build_id(self, flavor: str, platform: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{flavor}-{platform}-{timestamp}-{uuid4().hex[:8]}"

    def _run_pipeline(self, job: BuildJob, request: BuildRequestData) -> None:
        runtime = None
        if self._is_canceled(job):
            self._log(job, f"[{job.build_id}] 🛑 Skipping pipeline because cancellation was requested before execution")
            self.repository.save(job)
            return
        job.status = BuildStatus.RUNNING
        try:
            self._log(job, f"[{job.build_id}] 🛠️ [{job.flavor}] Build started")
            versions = self.version_resolver.resolve(request)
            job.resolved_flutter_sdk_version = versions.flutter_sdk_version
            job.mark_stage_running("environment_prepared", "Preparing isolated build environment")
            runtime = self.environment_assembler.assemble(
                job,
                versions,
                lambda message: self._log(job, message),
                should_cancel=lambda: self._is_canceled(job),
            )
            if self._is_canceled(job):
                self.repository.save(job)
                return
            job.mark_stage_completed("environment_prepared", "Isolated build environment ready")
            if not self._run_setup_script(job, runtime):
                return

            if not self._run_build_scripts(job, runtime):
                if not self._is_canceled(job):
                    job.status = BuildStatus.FAILED
                self.repository.save(job)
                return

            job.status = BuildStatus.COMPLETED
            self._log(
                job,
                f"[{job.build_id}] 🎉 Build pipeline completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            )
            self.repository.save(job)
        except CommandCancelledError:
            self._mark_canceled(job, "Build canceled while executing command")
            self.repository.save(job)
        except Exception as exc:
            if self._is_canceled(job):
                self._mark_canceled(job, "Build canceled by user request")
                self.repository.save(job)
                return
            job.status = BuildStatus.FAILED
            self._log(job, f"[{job.build_id}] 💥 Build pipeline failed: {exc}")
            logger.exception("Build pipeline failed for %s", job.build_id)
            self.repository.save(job)
        finally:
            if runtime and runtime.workspace_lease is not None:
                runtime.workspace_lease.release()
                self._log(job, f"[{job.build_id}] 🔓 Workspace slot released: {runtime.slot_key}/{runtime.slot_id}")

    def _run_setup_script(self, job: BuildJob, runtime) -> bool:
        if self._is_canceled(job):
            self._mark_canceled(job, "Build canceled before setup")
            self.repository.save(job)
            return False
        self._log(job, f"[{job.build_id}] 📦 Running setup...")
        job.mark_stage_running("dependencies_installed", "Resolving Flutter dependencies")
        try:
            self.setup_executor.run_setup(
                build_id=job.build_id,
                context=runtime,
                log=lambda message: self._log(job, message),
                should_cancel=lambda: self._is_canceled(job),
            )
            if self._is_canceled(job):
                self._mark_canceled(job, "Build canceled during setup")
                self.repository.save(job)
                return False
            job.mark_stage_completed("dependencies_installed", "Flutter dependencies resolved")
            return True
        except CommandCancelledError:
            self._mark_canceled(job, "Build canceled during setup")
            self.repository.save(job)
            return False
        except Exception as exc:
            job.mark_stage_failed("dependencies_installed", str(exc))
            self._log(job, f"[{job.build_id}] ❌ Setup failed: {exc}")
            job.status = BuildStatus.FAILED
            self.repository.save(job)
            return False

    def _run_build_scripts(self, job: BuildJob, runtime) -> bool:
        if self._is_canceled(job):
            self._mark_canceled(job, "Build canceled before platform build")
            self.repository.save(job)
            return False
        commands = []
        if job.platform in {"all", "android"}:
            commands.append(("android", self._build_command("action/1_android.sh")))
        if job.platform in {"all", "ios"}:
            commands.append(("ios", self._build_command("action/1_ios.sh")))
        if not commands:
            self._log(job, f"[{job.build_id}] ❌ No build processes started")
            return False

        processes = []
        for platform_name, command in commands:
            try:
                preflight_stage = f"{platform_name}_preflight"
                toolchain_stage = f"{platform_name}_toolchain_ready"
                build_stage = f"{platform_name}_build"
                if preflight_stage in job.stages:
                    job.mark_stage_running(preflight_stage, f"Running {platform_name} preflight checks")
                    self.setup_executor.prepare_platform_preflight(
                        build_id=job.build_id,
                        platform=platform_name,
                        context=runtime,
                        log=lambda message: self._log(job, message),
                        should_cancel=lambda: self._is_canceled(job),
                    )
                    if self._is_canceled(job):
                        self._mark_canceled(job, f"{platform_name.title()} build canceled during preflight")
                        return False
                    job.mark_stage_completed(preflight_stage, f"{platform_name.title()} preflight checks passed")
                job.mark_stage_running(toolchain_stage, f"Preparing {platform_name} toolchain")
                self.setup_executor.prepare_platform_toolchain(
                    build_id=job.build_id,
                    platform=platform_name,
                    context=runtime,
                    log=lambda message: self._log(job, message),
                    should_cancel=lambda: self._is_canceled(job),
                )
                if self._is_canceled(job):
                    self._mark_canceled(job, f"{platform_name.title()} build canceled during toolchain setup")
                    return False
                job.mark_stage_completed(toolchain_stage, f"{platform_name.title()} toolchain ready")
            except CommandCancelledError:
                self._mark_canceled(job, f"{platform_name.title()} build canceled during setup")
                return False
            except Exception as exc:
                failed_stage = (
                    preflight_stage
                    if preflight_stage in job.stages and job.stages[preflight_stage].status == StageStatus.RUNNING
                    else toolchain_stage
                )
                job.mark_stage_failed(failed_stage, str(exc))
                self._log(job, f"[{job.build_id}] ❌ {platform_name.title()} setup failed: {exc}")
                return False
            job.mark_stage_running(build_stage, f"{platform_name.title()} build started")
            self._log(job, f"[{job.build_id}] Starting {platform_name} build...")
            command_env = runtime.build_env()
            process = self.command_runner.start(command, env=command_env, cwd=os.getcwd())
            job.processes[platform_name] = process
            processes.append((platform_name, process))
            threading.Thread(
                target=self._monitor_process_output,
                args=(job, platform_name, process),
                daemon=True,
            ).start()

        success = True
        for platform_name, process in processes:
            self.command_runner.wait(process)
            if self._is_canceled(job):
                self._mark_canceled(job, f"{platform_name.title()} build canceled")
                self.repository.save(job)
                return False
            if process.returncode != 0:
                job.mark_stage_failed(f"{platform_name}_build", f"Exit code {process.returncode}")
                self._log(
                    job,
                    f"[{job.build_id}] ❌ {platform_name.title()} build failed with code {process.returncode}",
                )
                success = False
            else:
                job.mark_stage_completed(f"{platform_name}_build", "Build completed successfully")
                self._log(job, f"[{job.build_id}] ✅ {platform_name.title()} build completed successfully")
        return success

    def _build_command(self, script_path: str) -> list[str]:
        return ["bash", script_path]

    def _monitor_process_output(self, job: BuildJob, platform_name: str, process) -> None:
        self._initialize_progress(job, platform_name)
        for line in self.command_runner.iter_lines(process):
            if not line:
                continue
            self._log(job, self._parse_progress_line(job, platform_name, line))

    def _initialize_progress(self, job: BuildJob, platform_name: str) -> None:
        with job.lock:
            job.progress.setdefault(platform_name, BuildProgress())

    def _parse_progress_line(self, job: BuildJob, platform_name: str, line: str) -> str:
        progress = job.progress[platform_name]
        if line.startswith("PROGRESS:"):
            parts = line.split(":", 3)
            if len(parts) == 4:
                try:
                    progress.current_step = parts[1]
                    progress.current_message = parts[2]
                    progress.percentage = int(parts[3].replace("%", ""))
                    return f"[{job.build_id}][{platform_name.upper()}] 📊 {progress.current_message} ({progress.percentage}%)"
                except ValueError:
                    pass
        elif line.startswith("STEP:"):
            parts = line.split(":", 3)
            if len(parts) == 4:
                step_info = {
                    "step": parts[1],
                    "status": parts[2],
                    "message": parts[3],
                    "timestamp": datetime.now().isoformat(),
                }
                progress.steps_completed.append(step_info)
                status_emoji = "✅" if parts[2] == "SUCCESS" else "❌"
                return f"[{job.build_id}][{platform_name.upper()}] {status_emoji} {parts[3]}"
        return f"[{job.build_id}][{platform_name.upper()}] {line}"

    def _log(self, job: BuildJob, message: str) -> None:
        timestamp = datetime.now().isoformat()
        active_stages = [
            name for name, stage in job.stages.items() if stage.status == StageStatus.RUNNING
        ]
        with job.lock:
            job.logs.append(message)
            job.log_entries.append(
                BuildLogEntry(
                    message=message,
                    timestamp=timestamp,
                    stages=active_stages,
                )
            )
            if len(job.logs) > MAX_LOG_LINES:
                job.logs = job.logs[-KEEP_LOG_LINES:]
            if len(job.log_entries) > MAX_LOG_LINES:
                job.log_entries = job.log_entries[-KEEP_LOG_LINES:]
        logger_instance = self.build_loggers.get(job.build_id)
        if logger_instance:
            logger_instance.log(message)
        self.repository.save(job)

    def _is_canceled(self, job: BuildJob) -> bool:
        return job.status == BuildStatus.CANCELED

    def _mark_canceled(self, job: BuildJob, reason: str) -> None:
        with job.lock:
            job.mark_canceled(reason)
        self._log(job, f"[{job.build_id}] 🛑 {reason}")

    def _terminate_processes(self, job: BuildJob) -> None:
        for platform_name, process in list(job.processes.items()):
            if process.poll() is not None:
                continue
            self._log(job, f"[{job.build_id}] 🧹 Terminating {platform_name} build process")
            self.command_runner.terminate(process)
            stage_name = f"{platform_name}_build"
            if stage_name in job.stages and job.stages[stage_name].status in {StageStatus.PENDING, StageStatus.RUNNING}:
                job.mark_stage_canceled(stage_name, "Build canceled by user request")
