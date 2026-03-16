"""Project build jobs into API-friendly status payloads."""

from __future__ import annotations

from typing import Dict, Optional

from ..domain import BuildJob, BuildStatus
from ..domain.builds import StageStatus


class BuildStatusPresenter:
    """Convert runtime build state into response dictionaries."""

    def detail(self, job: BuildJob, log_file_path: Optional[str]) -> Dict:
        status = self._effective_status(job).value
        stage_logs = self._stage_logs(job)
        return {
            "build_id": job.build_id,
            "status": status,
            "started_at": job.started_at,
            "flavor": job.flavor,
            "platform": job.platform,
            "trigger_source": job.trigger_source,
            "trigger_event_id": job.trigger_event_id,
            "flutter_sdk_version": job.flutter_sdk_version,
            "resolved_flutter_sdk_version": job.resolved_flutter_sdk_version,
            "gradle_version": job.gradle_version,
            "cocoapods_version": job.cocoapods_version,
            "fastlane_version": job.fastlane_version,
            "branch_name": job.branch_name,
            "build_name": job.build_name,
            "build_number": job.build_number,
            "cancel_reason": job.cancel_reason,
            "cancel_requested_at": job.cancel_requested_at,
            "canceled_at": job.canceled_at,
            "queue_key": job.queue_key,
            "platform_statuses": self._platform_statuses(job),
            "processes": {
                name: {
                    "running": self._is_running(job, name),
                    "return_code": self._return_code(job, name),
                }
                for name in ("android", "ios")
                if name in job.processes or job.platform in {"all", name}
            },
            "progress": {
                name: {
                    "current_step": progress.current_step,
                    "percentage": progress.percentage,
                    "steps_completed": progress.steps_completed,
                    "current_message": progress.current_message,
                }
                for name, progress in job.progress.items()
            },
            "stages": [
                {
                    "name": stage.name,
                    "status": stage.status.value,
                    "message": stage.message,
                    "started_at": stage.started_at,
                    "completed_at": stage.completed_at,
                    "logs": stage_logs.get(stage.name, []),
                }
                for stage in job.stages.values()
            ],
            "logs": job.logs,
            "log_file_path": log_file_path,
        }

    def summary(self, job: BuildJob) -> Dict:
        return {
            "build_id": job.build_id,
            "status": self._effective_status(job).value,
            "started_at": job.started_at,
            "flavor": job.flavor,
            "platform": job.platform,
            "trigger_source": job.trigger_source,
            "trigger_event_id": job.trigger_event_id,
            "flutter_sdk_version": job.flutter_sdk_version,
            "resolved_flutter_sdk_version": job.resolved_flutter_sdk_version,
            "gradle_version": job.gradle_version,
            "cocoapods_version": job.cocoapods_version,
            "fastlane_version": job.fastlane_version,
            "branch_name": job.branch_name,
            "build_name": job.build_name,
            "build_number": job.build_number,
            "cancel_reason": job.cancel_reason,
            "cancel_requested_at": job.cancel_requested_at,
            "canceled_at": job.canceled_at,
            "queue_key": job.queue_key,
            "platform_statuses": self._platform_statuses(job),
            "stages": [
                {
                    "name": stage.name,
                    "status": stage.status.value,
                    "message": stage.message,
                    "started_at": stage.started_at,
                    "completed_at": stage.completed_at,
                }
                for stage in job.stages.values()
            ],
        }

    def _stage_logs(self, job: BuildJob) -> Dict[str, list[str]]:
        stage_logs = {name: [] for name in job.stages.keys()}
        for entry in job.log_entries:
            for stage_name in entry.stages:
                if stage_name in stage_logs:
                    stage_logs[stage_name].append(entry.message)
        return stage_logs

    def _effective_status(self, job: BuildJob) -> BuildStatus:
        if job.status == BuildStatus.CANCELED:
            return BuildStatus.CANCELED
        if any(self._is_running(job, key) for key in ("android", "ios")):
            return BuildStatus.RUNNING
        if any(self._return_code(job, key) not in (None, 0) for key in ("android", "ios")):
            return BuildStatus.FAILED
        if any(stage.status == StageStatus.FAILED for stage in job.stages.values()):
            return BuildStatus.FAILED
        if any(stage.status == StageStatus.CANCELED for stage in job.stages.values()):
            return BuildStatus.CANCELED
        return job.status

    def _platform_statuses(self, job: BuildJob) -> Dict[str, Dict[str, Optional[str]]]:
        return {
            name: self._platform_status(job, name)
            for name in ("android", "ios")
            if job.platform in {"all", name}
        }

    def _platform_status(self, job: BuildJob, platform_name: str) -> Dict[str, Optional[str]]:
        toolchain_stage = job.stages.get(f"{platform_name}_toolchain_ready")
        build_stage = job.stages.get(f"{platform_name}_build")
        progress = job.progress.get(platform_name)
        status = BuildStatus.PENDING.value
        message = None

        if self._is_running(job, platform_name):
            status = BuildStatus.RUNNING.value
        elif build_stage:
            status = build_stage.status.value
        elif toolchain_stage:
            status = toolchain_stage.status.value
        elif job.status == BuildStatus.FAILED:
            status = BuildStatus.FAILED.value

        if progress and progress.current_message:
            message = progress.current_message
        elif build_stage and build_stage.message:
            message = build_stage.message
        elif toolchain_stage and toolchain_stage.message:
            message = toolchain_stage.message

        return {
            "status": status,
            "label": platform_name.upper(),
            "message": message,
        }

    def _is_running(self, job: BuildJob, key: str) -> bool:
        process = job.processes.get(key)
        return bool(process and process.poll() is None)

    def _return_code(self, job: BuildJob, key: str):
        process = job.processes.get(key)
        return process.returncode if process else None
