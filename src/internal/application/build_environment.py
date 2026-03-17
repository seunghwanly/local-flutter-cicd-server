"""Build environment assembly and runtime context creation."""

from __future__ import annotations

import os

from ..core import BuildRuntimeContext
from ..core.config import get_build_workspace, get_isolated_env
from ..core.logging_utils import build_log_block
from ..domain import BuildJob
from ..infrastructure import RepositoryWorkspaceManager
from .version_resolver import ResolvedVersions


class BuildEnvironmentAssembler:
    """Build the isolated runtime environment for a job."""

    def __init__(self, repository_workspace_manager: RepositoryWorkspaceManager) -> None:
        self.repository_workspace_manager = repository_workspace_manager

    def assemble(self, job: BuildJob, versions: ResolvedVersions, log, should_cancel=None) -> BuildRuntimeContext:
        isolated = get_isolated_env(
            job.build_id,
            flutter_version=versions.flutter_sdk_version,
            gradle_version=versions.gradle_version,
            cocoapods_version=versions.cocoapods_version,
        )
        env = isolated["env"]
        repo_url = os.environ.get("REPO_URL", "")
        fastlane_lane = self._resolve_fastlane_lane(job)
        env.update(
            {
                "LOCAL_DIR": isolated["repo_dir"],
                "BRANCH_NAME": job.branch_name,
                "FLAVOR": job.flavor,
                "TRIGGER_SOURCE": job.trigger_source,
                "FASTLANE_LANE": fastlane_lane,
                "IOS_USE_BUNDLER": self._resolve_ios_use_bundler(job),
                "IOS_RUN_POD_INSTALL": self._resolve_ios_run_pod_install(),
                "DATADOG_API_KEY": os.environ.get("DATADOG_API_KEY", ""),
                "GYM_DERIVED_DATA_PATH": isolated["deriveddata_cache_dir"],
                "GYM_XCARCHIVE_PATH": os.path.join(isolated["deriveddata_cache_dir"], "Archives"),
                "FLUTTER_BUILD_DERIVED_DATA_PATH": isolated["deriveddata_cache_dir"],
            }
        )

        prepared = self.repository_workspace_manager.prepare(
            build_id=job.build_id,
            repo_url=repo_url,
            branch_name=job.branch_name,
            repo_dir=isolated["repo_dir"],
            env=env,
            requested_flutter_version=versions.flutter_sdk_version,
            platform=job.platform,
            log=log,
            should_cancel=should_cancel,
        )
        env["LOCAL_DIR"] = prepared.repo_dir
        # Force pod install auto-detection when iOS precache had to repair SDK state.
        env["IOS_FLUTTER_SDK_CHANGED"] = "true" if (prepared.flutter_version_changed or prepared.precache_ran) else "false"
        job.mark_stage_completed("repository_synced", f"Repository synchronized for {job.branch_name}")
        resolved_flutter_version = prepared.flutter_version
        if resolved_flutter_version:
            env["FLUTTER_SDK_VERSION"] = resolved_flutter_version
        versions.flutter_sdk_version = resolved_flutter_version
        job.resolved_flutter_sdk_version = resolved_flutter_version
        job.mark_stage_completed(
            "flutter_sdk_resolved",
            resolved_flutter_version or "No Flutter SDK version resolved",
        )

        if prepared.precache_ran:
            job.mark_stage_completed("flutter_precached", "fvm flutter precache --ios completed")
        elif resolved_flutter_version:
            job.mark_stage_completed("flutter_precached", "No precache required")

        for key, value in (
            ("GRADLE_VERSION", versions.gradle_version),
            ("COCOAPODS_VERSION", versions.cocoapods_version),
            ("FASTLANE_VERSION", versions.fastlane_version),
        ):
            if value:
                env[key] = value

        match_password = os.environ.get("MATCH_PASSWORD")
        if match_password:
            env["MATCH_PASSWORD"] = match_password

        summary_rows: list[tuple[str, object]] = [
            ("Workspace", get_build_workspace(job.build_id)),
            ("Repo slot", prepared.repo_dir),
            ("Branch", job.branch_name),
            ("Fastlane lane", fastlane_lane),
        ]
        if prepared.workspace_lease is not None:
            summary_rows.append(("Slot key", prepared.workspace_lease.slot_key))
            summary_rows.append(("Slot id", prepared.workspace_lease.slot_id))
        if versions.gradle_version:
            summary_rows.append(("Gradle version", versions.gradle_version))
        if versions.cocoapods_version:
            summary_rows.append(("CocoaPods version", versions.cocoapods_version))
        if versions.fastlane_version:
            summary_rows.append(("Fastlane version", versions.fastlane_version))

        if job.trigger_source in {"shorebird", "shorebird_manual"}:
            log(
                f"[{job.build_id}] 🐦 Shorebird patch config: "
                f"flavor={job.flavor}, branch={job.branch_name}, "
                f"release_version={job.build_name}, platform={job.platform}"
            )
            if job.build_number:
                log(
                    f"[{job.build_id}] ℹ️ Shorebird patch number received: {job.build_number} "
                    f"(currently retained for logs/status only)"
                )

        log(build_log_block(job.build_id, "📂 Build environment ready", summary_rows))

        return BuildRuntimeContext(
            env=env,
            repo_dir=prepared.repo_dir,
            workspace=str(get_build_workspace(job.build_id)),
            trigger_source=job.trigger_source,
            build_name=job.build_name,
            build_number=job.build_number,
            slot_key=prepared.workspace_lease.slot_key if prepared.workspace_lease else None,
            slot_id=prepared.workspace_lease.slot_id if prepared.workspace_lease else None,
            workspace_lease=prepared.workspace_lease,
        )

    def _resolve_fastlane_lane(self, job: BuildJob) -> str:
        if job.trigger_source in {"shorebird", "shorebird_manual"}:
            return os.environ.get(f"SHOREBIRD_{job.flavor.upper()}_FASTLANE_LANE", f"patch_{job.flavor}")
        return os.environ.get(f"{job.flavor.upper()}_FASTLANE_LANE", "beta")

    def _resolve_ios_use_bundler(self, job: BuildJob) -> str:
        if job.platform in {"ios", "all"} and job.trigger_source in {"shorebird", "shorebird_manual"}:
            return "false"
        return "true"

    def _resolve_ios_run_pod_install(self) -> str:
        return os.environ.get("IOS_RUN_POD_INSTALL", "auto")
