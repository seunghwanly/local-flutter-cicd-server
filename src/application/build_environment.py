"""Build environment assembly and runtime context creation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict

from ..core.config import get_build_workspace, get_isolated_env
from ..domain import BuildJob
from ..infrastructure import RepositoryWorkspaceManager
from .version_resolver import ResolvedVersions


@dataclass
class BuildRuntimeContext:
    """Resolved environment and workspace paths for a build job."""

    env: Dict[str, str]
    repo_dir: str
    workspace: str


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
                "FASTLANE_LANE": fastlane_lane,
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

        log(f"[{job.build_id}] 📂 Workspace: {get_build_workspace(job.build_id)}")
        log(f"[{job.build_id}] 🌿 Branch: {job.branch_name}")
        log(f"[{job.build_id}] 🛣️ Fastlane lane: {fastlane_lane}")
        if versions.gradle_version:
            log(f"[{job.build_id}] 🔧 Gradle version: {versions.gradle_version}")
        if versions.cocoapods_version:
            log(f"[{job.build_id}] 🔧 CocoaPods version: {versions.cocoapods_version}")
        if versions.fastlane_version:
            log(f"[{job.build_id}] 🔧 Fastlane version: {versions.fastlane_version}")
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

        return BuildRuntimeContext(
            env=env,
            repo_dir=isolated["repo_dir"],
            workspace=str(get_build_workspace(job.build_id)),
        )

    def _resolve_fastlane_lane(self, job: BuildJob) -> str:
        if job.trigger_source in {"shorebird", "shorebird_manual"}:
            return os.environ.get(f"SHOREBIRD_{job.flavor.upper()}_FASTLANE_LANE", f"patch_{job.flavor}")
        return os.environ.get(f"{job.flavor.upper()}_FASTLANE_LANE", "beta")
