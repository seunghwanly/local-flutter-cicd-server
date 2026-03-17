"""Repository sync and Flutter workspace preparation utilities."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Optional

from ..core.config import get_shared_cache_dir
from .command_runner import CommandExecutionError, CommandRunner
from .workspace_pool import WorkspacePoolManager, WorkspaceSlotLease


class PreparedRepositoryResult:
    """Result of repository sync and Flutter SDK alignment."""

    def __init__(
        self,
        flutter_version: Optional[str],
        precache_ran: bool,
        repo_dir: str,
        workspace_lease: WorkspaceSlotLease | None,
        flutter_version_changed: bool = False,
    ) -> None:
        self.flutter_version = flutter_version
        self.precache_ran = precache_ran
        self.repo_dir = repo_dir
        self.workspace_lease = workspace_lease
        self.flutter_version_changed = flutter_version_changed


class RepositoryWorkspaceManager:
    """Prepare a repo checkout and align the Flutter SDK for a build."""

    def __init__(
        self,
        command_runner: CommandRunner,
        workspace_pool: WorkspacePoolManager | None = None,
    ) -> None:
        self.command_runner = command_runner
        self.workspace_pool = workspace_pool or WorkspacePoolManager()

    def prepare(
        self,
        *,
        build_id: str,
        repo_url: str,
        branch_name: str,
        repo_dir: str,
        env: Dict[str, str],
        requested_flutter_version: Optional[str],
        platform: str,
        log,
        should_cancel=None,
    ) -> PreparedRepositoryResult:
        seeded_version = requested_flutter_version or self._read_previous_flutter_version(repo_url, branch_name)
        workspace_lease = self.workspace_pool.acquire(
            build_id=build_id,
            repo_url=repo_url,
            branch_name=branch_name,
            flutter_version=seeded_version,
            platform=platform,
            cocoapods_version=env.get("COCOAPODS_VERSION"),
            log=log,
        )
        repo_path = workspace_lease.repo_dir

        try:
            self._sync_repository(
                build_id=build_id,
                repo_url=repo_url,
                branch_name=branch_name,
                repo_path=repo_path,
                env=env,
                log=log,
                should_cancel=should_cancel,
            )

            resolved_version = self._resolve_flutter_version(repo_path, requested_flutter_version)
            if not resolved_version:
                log(f"[{build_id}] ⚠️ Flutter SDK version could not be resolved from request or repository")
                return PreparedRepositoryResult(
                    flutter_version=None,
                    precache_ran=False,
                    repo_dir=str(repo_path),
                    workspace_lease=workspace_lease,
                )

            previous_version = self._read_previous_flutter_version(repo_url, branch_name)
            version_changed = previous_version is not None and previous_version != resolved_version

            log(f"[{build_id}] 🔧 Effective Flutter SDK version: {resolved_version}")
            if previous_version:
                log(f"[{build_id}] 📚 Previously synced Flutter SDK version: {previous_version}")

            self._ensure_melos_sdk_path(build_id, repo_path, log)
            self._run_fvm_use(build_id, repo_path, env, resolved_version, log, should_cancel=should_cancel)

            precache_ran = False
            should_precache_ios = platform in {"all", "ios"}
            missing_ios_engine_artifacts = should_precache_ios and self._is_ios_engine_artifact_missing(
                build_id,
                repo_path,
                log,
            )
            if should_precache_ios and (version_changed or missing_ios_engine_artifacts):
                self._run_flutter_precache(
                    build_id,
                    repo_path,
                    env,
                    resolved_version,
                    platform,
                    log,
                    reason=self._build_precache_reason(
                        version_changed=version_changed,
                        missing_ios_engine_artifacts=missing_ios_engine_artifacts,
                        repo_path=repo_path,
                    ),
                    should_cancel=should_cancel,
                )
                precache_ran = True

            self._write_previous_flutter_version(repo_url, branch_name, resolved_version)
            return PreparedRepositoryResult(
                flutter_version=resolved_version,
                precache_ran=precache_ran,
                repo_dir=str(repo_path),
                workspace_lease=workspace_lease,
                flutter_version_changed=version_changed,
            )
        except Exception:
            workspace_lease.release()
            raise

    def _sync_repository(
        self,
        *,
        build_id: str,
        repo_url: str,
        branch_name: str,
        repo_path: Path,
        env: Dict[str, str],
        log,
        should_cancel=None,
    ) -> None:
        fresh_clone = not (repo_path / ".git").exists()
        if fresh_clone:
            log(f"[{build_id}] 📦 Cloning repository into isolated workspace")
            self.command_runner.run_checked(
                ["git", "clone", "--depth", "1", "--single-branch", "--branch", branch_name, repo_url, str(repo_path)],
                env=env,
                cwd=str(repo_path.parent),
                should_stop=should_cancel,
            )
            return

        self.command_runner.run_checked(
            ["git", "remote", "set-url", "origin", repo_url],
            env=env,
            cwd=str(repo_path),
            should_stop=should_cancel,
        )

        log(f"[{build_id}] 🔄 Fetching latest branch state from origin/{branch_name}")
        self.command_runner.run_checked(
            ["git", "fetch", "origin"],
            env=env,
            cwd=str(repo_path),
            should_stop=should_cancel,
        )

        branch_exists = self.command_runner.run(
            ["git", "ls-remote", "--heads", "origin", branch_name],
            env=env,
            cwd=str(repo_path),
            check=False,
            should_stop=should_cancel,
        )
        if branch_exists.returncode != 0 or not branch_exists.stdout.strip():
            raise ValueError(f"Branch '{branch_name}' does not exist in remote repository")

        local_branch = self.command_runner.run(
            ["git", "rev-parse", "--verify", branch_name],
            env=env,
            cwd=str(repo_path),
            check=False,
            should_stop=should_cancel,
        )
        if local_branch.returncode == 0:
            self.command_runner.run_checked(
                ["git", "checkout", branch_name],
                env=env,
                cwd=str(repo_path),
                should_stop=should_cancel,
            )
        else:
            self.command_runner.run_checked(
                ["git", "checkout", "-B", branch_name, f"origin/{branch_name}"],
                env=env,
                cwd=str(repo_path),
                should_stop=should_cancel,
            )

        self.command_runner.run_checked(
            ["git", "reset", "--hard", f"origin/{branch_name}"],
            env=env,
            cwd=str(repo_path),
            should_stop=should_cancel,
        )
        self.command_runner.run_checked(
            ["git", "clean", "-fdx"],
            env=env,
            cwd=str(repo_path),
            should_stop=should_cancel,
        )

    def _resolve_flutter_version(
        self,
        repo_path: Path,
        requested_flutter_version: Optional[str],
    ) -> Optional[str]:
        if requested_flutter_version:
            return requested_flutter_version

        fvmrc_path = repo_path / ".fvmrc"
        if fvmrc_path.exists():
            raw = fvmrc_path.read_text(encoding="utf-8").strip()
            if not raw:
                return None
            if raw.startswith("{"):
                data = json.loads(raw)
                version = str(data.get("flutter", "")).strip()
                return version or None
            return raw

        tool_versions_path = repo_path / ".tool-versions"
        if tool_versions_path.exists():
            for line in tool_versions_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("flutter "):
                    _, version = stripped.split(None, 1)
                    return version.strip() or None

        fallback = os.environ.get("FLUTTER_VERSION")
        return fallback.strip() if fallback else None

    def _run_fvm_use(
        self,
        build_id: str,
        repo_path: Path,
        env: Dict[str, str],
        flutter_version: str,
        log,
        should_cancel=None,
    ) -> None:
        log(f"[{build_id}] 📦 Running fvm use {flutter_version}")
        try:
            result = self.command_runner.run_checked(
                ["fvm", "use", flutter_version, "--force", "--skip-pub-get", "--skip-setup"],
                env=env,
                cwd=str(repo_path),
                should_stop=should_cancel,
            )
        except CommandExecutionError as exc:
            raise RuntimeError(f"Failed to activate Flutter SDK {flutter_version}: {exc}") from exc

        for line in result.stdout.splitlines():
            if line.strip():
                log(f"[{build_id}][FVM] {line.strip()}")

    def _ensure_melos_sdk_path(self, build_id: str, repo_path: Path, log) -> None:
        melos_path = repo_path / "melos.yaml"
        if not melos_path.exists():
            return

        content = melos_path.read_text(encoding="utf-8")
        if "sdkPath:" in content:
            log(f"[{build_id}] ✅ melos.yaml already declares sdkPath")
            return

        melos_path.write_text(f"sdkPath: .fvm/flutter_sdk\n{content}", encoding="utf-8")
        log(f"[{build_id}] 🔧 Added sdkPath to melos.yaml before running fvm use")

    def _run_flutter_precache(
        self,
        build_id: str,
        repo_path: Path,
        env: Dict[str, str],
        flutter_version: str,
        platform: str,
        log,
        reason: str,
        should_cancel=None,
    ) -> None:
        log(
            f"[{build_id}] 🔄 Running required Flutter iOS precache "
            f"({flutter_version}, platform={platform}, reason={reason})"
        )
        try:
            result = self.command_runner.run_checked(
                ["fvm", "flutter", "precache", "--ios"],
                env=env,
                cwd=str(repo_path),
                should_stop=should_cancel,
            )
        except CommandExecutionError as exc:
            raise RuntimeError(
                f"Flutter SDK changed to {flutter_version} but fvm flutter precache --ios failed: {exc}"
            ) from exc

        for line in result.stdout.splitlines():
            if line.strip():
                log(f"[{build_id}][PRECACHE] {line.strip()}")

    def _is_ios_engine_artifact_missing(self, build_id: str, repo_path: Path, log) -> bool:
        artifact_path = self._ios_engine_artifact_path(repo_path)
        if artifact_path.exists():
            return False

        log(f"[{build_id}] ⚠️ Missing Flutter iOS engine artifact: {artifact_path}")
        return True

    def _ios_engine_artifact_path(self, repo_path: Path) -> Path:
        return repo_path / ".fvm" / "flutter_sdk" / "bin" / "cache" / "artifacts" / "engine" / "ios" / "Flutter.xcframework"

    def _build_precache_reason(
        self,
        *,
        version_changed: bool,
        missing_ios_engine_artifacts: bool,
        repo_path: Path,
    ) -> str:
        reasons: list[str] = []
        if version_changed:
            reasons.append("flutter_sdk_version_changed")
        if missing_ios_engine_artifacts:
            reasons.append(f"missing_ios_engine_artifact:{self._ios_engine_artifact_path(repo_path)}")
        return ",".join(reasons) if reasons else "unknown"

    def _metadata_file(self, repo_url: str, branch_name: str) -> Path:
        shared_dir = get_shared_cache_dir() / "repo_state"
        shared_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(f"{repo_url}::{branch_name}".encode("utf-8")).hexdigest()
        return shared_dir / f"{key}.json"

    def _read_previous_flutter_version(self, repo_url: str, branch_name: str) -> Optional[str]:
        metadata_file = self._metadata_file(repo_url, branch_name)
        if not metadata_file.exists():
            return None

        try:
            data = json.loads(metadata_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

        version = data.get("flutter_sdk_version")
        if not version:
            return None
        return str(version).strip() or None

    def _write_previous_flutter_version(
        self,
        repo_url: str,
        branch_name: str,
        flutter_version: str,
    ) -> None:
        metadata_file = self._metadata_file(repo_url, branch_name)
        metadata_file.write_text(
            json.dumps(
                {
                    "repo_url": repo_url,
                    "branch_name": branch_name,
                    "flutter_sdk_version": flutter_version,
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
