"""Application service orchestrating build execution."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

from ..core.queue_manager import queue_manager
from ..domain import BuildJob, BuildProgress, BuildRequestData, BuildStatus
from ..infrastructure import BuildLogger, CommandRunner, SetupExecutor
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
        queue_key = queue_manager.get_queue_key(
            branch_name, validated_request.flutter_sdk_version, validated_request.flavor
        )

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

    def _generate_build_id(self, flavor: str, platform: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{flavor}-{platform}-{timestamp}-{uuid4().hex[:8]}"

    def _run_pipeline(self, job: BuildJob, request: BuildRequestData) -> None:
        job.status = BuildStatus.RUNNING
        try:
            self._log(job, f"[{job.build_id}] 🛠️ [{job.flavor}] Build started")
            versions = self.version_resolver.resolve(request)
            job.resolved_flutter_sdk_version = versions.flutter_sdk_version
            job.mark_stage_running("environment_prepared", "Preparing isolated build environment")
            runtime = self.environment_assembler.assemble(job, versions, lambda message: self._log(job, message))
            job.mark_stage_completed("environment_prepared", "Isolated build environment ready")
            env = runtime.env

            if not self._run_setup_script(job, env):
                return

            if not self._run_build_scripts(job, env):
                job.status = BuildStatus.FAILED
                return

            job.status = BuildStatus.COMPLETED
            self._log(
                job,
                f"[{job.build_id}] 🎉 Build pipeline completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            )
        except Exception as exc:
            job.status = BuildStatus.FAILED
            self._log(job, f"[{job.build_id}] 💥 Build pipeline failed: {exc}")
            logger.exception("Build pipeline failed for %s", job.build_id)

    def _run_setup_script(self, job: BuildJob, env: Dict[str, str]) -> bool:
        self._log(job, f"[{job.build_id}] 📦 Running setup...")
        job.mark_stage_running("dependencies_installed", "Resolving Flutter dependencies")
        try:
            self.setup_executor.run_setup(
                build_id=job.build_id,
                repo_dir=env["LOCAL_DIR"],
                env=env,
                log=lambda message: self._log(job, message),
            )
            job.mark_stage_completed("dependencies_installed", "Flutter dependencies resolved")
            return True
        except Exception as exc:
            job.mark_stage_failed("dependencies_installed", str(exc))
            self._log(job, f"[{job.build_id}] ❌ Setup failed: {exc}")
            job.status = BuildStatus.FAILED
            return False

    def _run_build_scripts(self, job: BuildJob, env: Dict[str, str]) -> bool:
        commands = []
        if job.platform in {"all", "android"}:
            commands.append(("android", self._build_command("action/1_android.sh"), self._build_env(env, job)))
        if job.platform in {"all", "ios"}:
            commands.append(("ios", self._build_command("action/1_ios.sh"), self._build_env(env, job)))
        if not commands:
            self._log(job, f"[{job.build_id}] ❌ No build processes started")
            return False

        processes = []
        for platform_name, command, command_env in commands:
            try:
                toolchain_stage = f"{platform_name}_toolchain_ready"
                build_stage = f"{platform_name}_build"
                job.mark_stage_running(toolchain_stage, f"Preparing {platform_name} toolchain")
                self.setup_executor.prepare_platform_toolchain(
                    build_id=job.build_id,
                    platform=platform_name,
                    repo_dir=env["LOCAL_DIR"],
                    env=env,
                    log=lambda message: self._log(job, message),
                )
                job.mark_stage_completed(toolchain_stage, f"{platform_name.title()} toolchain ready")
            except Exception as exc:
                job.mark_stage_failed(toolchain_stage, str(exc))
                self._log(job, f"[{job.build_id}] ❌ {platform_name.title()} toolchain setup failed: {exc}")
                return False
            job.mark_stage_running(build_stage, f"{platform_name.title()} build started")
            self._log(job, f"[{job.build_id}] Starting {platform_name} build...")
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

    def _build_env(self, env: Dict[str, str], job: BuildJob) -> Dict[str, str]:
        command_env = dict(env)
        if job.build_name:
            command_env["BUILD_NAME"] = job.build_name
        if job.build_number:
            command_env["BUILD_NUMBER"] = job.build_number
        return command_env

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
        with job.lock:
            job.logs.append(message)
            if len(job.logs) > MAX_LOG_LINES:
                job.logs = job.logs[-KEEP_LOG_LINES:]
        logger_instance = self.build_loggers.get(job.build_id)
        if logger_instance:
            logger_instance.log(message)
