"""Flutter and pub dependency setup helpers."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Dict

from ..core import BuildRuntimeContext
from .command_runner import CommandRunner


class PubSetupExecutor:
    """Prepare Flutter/pub dependencies before platform-specific work starts."""

    _GIT_URL_PATTERN = re.compile(r"url:\s*([^\s]+)")

    def __init__(self, command_runner: CommandRunner) -> None:
        self.command_runner = command_runner

    def run_setup(
        self,
        *,
        build_id: str,
        context: BuildRuntimeContext,
        log,
        should_cancel=None,
    ) -> None:
        repo_path = Path(context.repo_dir)
        pub_cache = Path(context.env["PUB_CACHE"])

        log(f"[{build_id}] 📦 Running Python setup workflow")
        self._ensure_git_cache(pub_cache, build_id, log)
        self._activate_global_package(repo_path, context.env, build_id, "melos", log, should_cancel=should_cancel)
        self._activate_global_package(repo_path, context.env, build_id, "flutterfire_cli", log, should_cancel=should_cancel)
        self._run_pub_get(repo_path, pub_cache, context.env, build_id, log, should_cancel=should_cancel)

    def _ensure_git_cache(self, pub_cache: Path, build_id: str, log) -> None:
        git_dir = pub_cache / "git"
        cache_dir = git_dir / "cache"

        log(f"[{build_id}] 📦 Checking PUB_CACHE git cache")
        if git_dir.is_symlink():
            if git_dir.exists():
                log(f"[{build_id}] 🔗 PUB_CACHE git cache is a valid symlink")
                return
            log(f"[{build_id}] ⚠️ Broken git cache symlink detected, recreating local cache")
            git_dir.unlink(missing_ok=True)
            cache_dir.mkdir(parents=True, exist_ok=True)
            return

        cache_dir.mkdir(parents=True, exist_ok=True)
        corrupted = 0
        for entry in cache_dir.iterdir():
            if not entry.is_dir() or entry.is_symlink():
                continue
            result = self.command_runner.run(
                ["git", "-C", str(entry), "rev-parse", "--git-dir"],
                env={},
                cwd=str(entry),
                check=False,
            )
            if result.returncode != 0:
                shutil.rmtree(entry)
                corrupted += 1
        if corrupted:
            log(f"[{build_id}] 🧹 Cleaned {corrupted} corrupted git cache(s)")
        else:
            log(f"[{build_id}] ✅ PUB_CACHE git cache is ready")

    def _activate_global_package(
        self,
        repo_path: Path,
        env: Dict[str, str],
        build_id: str,
        package_name: str,
        log,
        should_cancel=None,
    ) -> None:
        log(f"[{build_id}] 🔧 Activating {package_name}")
        result = self.command_runner.run_checked(
            ["fvm", "dart", "pub", "global", "activate", package_name],
            env=env,
            cwd=str(repo_path),
            should_stop=should_cancel,
        )
        for line in result.stdout.splitlines():
            if line.strip():
                log(f"[{build_id}][SETUP] {line.strip()}")

    def _run_pub_get(
        self,
        repo_path: Path,
        pub_cache: Path,
        env: Dict[str, str],
        build_id: str,
        log,
        should_cancel=None,
    ) -> None:
        pubspec = repo_path / "pubspec.yaml"
        has_melos = (repo_path / "melos.yaml").exists()
        if pubspec.exists():
            git_urls = self._extract_git_dependency_urls(pubspec)
            if git_urls:
                log(f"[{build_id}] 📋 Detected git dependencies in pubspec.yaml")
        else:
            git_urls = []

        commands = []
        if has_melos:
            commands.append(["fvm", "exec", "melos", "run", "pub"])
        commands.append(["fvm", "flutter", "pub", "get", "--verbose"])

        for command in commands:
            result = self.command_runner.run(
                command,
                env=env,
                cwd=str(repo_path),
                check=False,
                should_stop=should_cancel,
            )
            for line in result.stdout.splitlines():
                if line.strip():
                    log(f"[{build_id}][SETUP] {line.strip()}")
            if result.returncode == 0:
                log(f"[{build_id}] ✅ Dependency resolution succeeded with {' '.join(command)}")
                return

        log(f"[{build_id}] ⚠️ Dependency resolution failed, repairing pub cache and retrying")
        self._log_git_dependency_access(repo_path, env, build_id, git_urls, log, should_cancel=should_cancel)
        self._reset_git_cache(pub_cache, build_id, log)
        repair = self.command_runner.run_checked(
            ["fvm", "flutter", "pub", "cache", "repair"],
            env=env,
            cwd=str(repo_path),
            should_stop=should_cancel,
        )
        for line in repair.stdout.splitlines():
            if line.strip():
                log(f"[{build_id}][SETUP] {line.strip()}")

        retry_commands = []
        if has_melos:
            retry_commands.append(["fvm", "exec", "melos", "run", "pub"])
        retry_commands.append(["fvm", "flutter", "pub", "get", "--verbose"])
        for command in retry_commands:
            result = self.command_runner.run(
                command,
                env=env,
                cwd=str(repo_path),
                check=False,
                should_stop=should_cancel,
            )
            for line in result.stdout.splitlines():
                if line.strip():
                    log(f"[{build_id}][SETUP] {line.strip()}")
            if result.returncode == 0:
                log(f"[{build_id}] ✅ Dependency resolution recovered with {' '.join(command)}")
                return

        raise RuntimeError("pub get failed even after cache repair")

    def _extract_git_dependency_urls(self, pubspec: Path) -> list[str]:
        urls: list[str] = []
        for line in pubspec.read_text(encoding="utf-8").splitlines():
            match = self._GIT_URL_PATTERN.search(line)
            if match:
                urls.append(match.group(1).strip().strip("'\""))
        return urls

    def _log_git_dependency_access(
        self,
        repo_path: Path,
        env: Dict[str, str],
        build_id: str,
        urls: list[str],
        log,
        should_cancel=None,
    ) -> None:
        for url in urls:
            result = self.command_runner.run(
                ["git", "ls-remote", url, "HEAD"],
                env=env,
                cwd=str(repo_path),
                check=False,
                should_stop=should_cancel,
            )
            status = "OK" if result.returncode == 0 else "FAILED"
            log(f"[{build_id}] 🔍 Git dependency access {status}: {url}")

    def _reset_git_cache(self, pub_cache: Path, build_id: str, log) -> None:
        git_dir = pub_cache / "git"
        cache_dir = git_dir / "cache"
        if git_dir.is_symlink():
            log(f"[{build_id}] 🔗 Removing symlinked git cache before repair")
            git_dir.unlink(missing_ok=True)
            cache_dir.mkdir(parents=True, exist_ok=True)
            return

        cache_dir.mkdir(parents=True, exist_ok=True)
        for entry in cache_dir.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
        log(f"[{build_id}] 🧹 Cleared isolated git cache before repair")
