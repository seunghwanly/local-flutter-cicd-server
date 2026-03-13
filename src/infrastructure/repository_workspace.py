"""Repository sync and Flutter workspace preparation utilities."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Optional

from ..core.config import get_shared_cache_dir
from .command_runner import CommandExecutionError, CommandRunner


class PreparedRepositoryResult:
    """Result of repository sync and Flutter SDK alignment."""

    def __init__(self, flutter_version: Optional[str], precache_ran: bool) -> None:
        self.flutter_version = flutter_version
        self.precache_ran = precache_ran


class RepositoryWorkspaceManager:
    """Prepare a repo checkout and align the Flutter SDK for a build."""

    def __init__(self, command_runner: CommandRunner) -> None:
        self.command_runner = command_runner

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
    ) -> PreparedRepositoryResult:
        repo_path = Path(repo_dir)
        repo_path.mkdir(parents=True, exist_ok=True)

        self._sync_repository(
            build_id=build_id,
            repo_url=repo_url,
            branch_name=branch_name,
            repo_path=repo_path,
            env=env,
            log=log,
        )

        resolved_version = self._resolve_flutter_version(repo_path, requested_flutter_version)
        if not resolved_version:
            log(f"[{build_id}] ⚠️ Flutter SDK version could not be resolved from request or repository")
            return PreparedRepositoryResult(flutter_version=None, precache_ran=False)

        previous_version = self._read_previous_flutter_version(repo_url, branch_name)
        version_changed = previous_version is not None and previous_version != resolved_version

        log(f"[{build_id}] 🔧 Effective Flutter SDK version: {resolved_version}")
        if previous_version:
            log(f"[{build_id}] 📚 Previously synced Flutter SDK version: {previous_version}")

        self._run_fvm_use(build_id, repo_path, env, resolved_version, log)

        precache_ran = False
        if version_changed:
            self._run_flutter_precache(build_id, repo_path, env, resolved_version, platform, log)
            precache_ran = True

        self._write_previous_flutter_version(repo_url, branch_name, resolved_version)
        return PreparedRepositoryResult(flutter_version=resolved_version, precache_ran=precache_ran)

    def _sync_repository(
        self,
        *,
        build_id: str,
        repo_url: str,
        branch_name: str,
        repo_path: Path,
        env: Dict[str, str],
        log,
    ) -> None:
        if not (repo_path / ".git").exists():
            log(f"[{build_id}] 📦 Cloning repository into isolated workspace")
            self.command_runner.run_checked(
                ["git", "clone", repo_url, str(repo_path)],
                env=env,
                cwd=str(repo_path.parent),
            )

        self.command_runner.run_checked(["git", "remote", "set-url", "origin", repo_url], env=env, cwd=str(repo_path))

        log(f"[{build_id}] 🔄 Fetching latest branch state from origin/{branch_name}")
        self.command_runner.run_checked(["git", "fetch", "origin"], env=env, cwd=str(repo_path))

        branch_exists = self.command_runner.run(
            ["git", "ls-remote", "--heads", "origin", branch_name],
            env=env,
            cwd=str(repo_path),
            check=False,
        )
        if branch_exists.returncode != 0 or not branch_exists.stdout.strip():
            raise ValueError(f"Branch '{branch_name}' does not exist in remote repository")

        local_branch = self.command_runner.run(
            ["git", "rev-parse", "--verify", branch_name],
            env=env,
            cwd=str(repo_path),
            check=False,
        )
        if local_branch.returncode == 0:
            self.command_runner.run_checked(["git", "checkout", branch_name], env=env, cwd=str(repo_path))
        else:
            self.command_runner.run_checked(
                ["git", "checkout", "-B", branch_name, f"origin/{branch_name}"],
                env=env,
                cwd=str(repo_path),
            )

        self.command_runner.run_checked(
            ["git", "reset", "--hard", f"origin/{branch_name}"],
            env=env,
            cwd=str(repo_path),
        )
        self.command_runner.run_checked(["git", "clean", "-fdx"], env=env, cwd=str(repo_path))

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
    ) -> None:
        log(f"[{build_id}] 📦 Running fvm use {flutter_version}")
        try:
            result = self.command_runner.run_checked(
                ["fvm", "use", flutter_version],
                env=env,
                cwd=str(repo_path),
            )
        except CommandExecutionError as exc:
            raise RuntimeError(f"Failed to activate Flutter SDK {flutter_version}: {exc}") from exc

        for line in result.stdout.splitlines():
            if line.strip():
                log(f"[{build_id}][FVM] {line.strip()}")

    def _run_flutter_precache(
        self,
        build_id: str,
        repo_path: Path,
        env: Dict[str, str],
        flutter_version: str,
        platform: str,
        log,
    ) -> None:
        log(
            f"[{build_id}] 🔄 Flutter SDK changed, running required precache for iOS "
            f"({flutter_version}, platform={platform})"
        )
        try:
            result = self.command_runner.run_checked(
                ["fvm", "flutter", "precache", "--ios"],
                env=env,
                cwd=str(repo_path),
            )
        except CommandExecutionError as exc:
            raise RuntimeError(
                f"Flutter SDK changed to {flutter_version} but fvm flutter precache --ios failed: {exc}"
            ) from exc

        for line in result.stdout.splitlines():
            if line.strip():
                log(f"[{build_id}][PRECACHE] {line.strip()}")

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
