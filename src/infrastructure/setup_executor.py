"""Python-native build setup and toolchain preparation."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Dict

from .command_runner import CommandExecutionError, CommandRunner


class SetupExecutor:
    """Prepare Flutter and Ruby toolchains before platform build scripts run."""

    _GIT_URL_PATTERN = re.compile(r"url:\s*([^\s]+)")

    def __init__(self, command_runner: CommandRunner) -> None:
        self.command_runner = command_runner

    def run_setup(
        self,
        *,
        build_id: str,
        repo_dir: str,
        env: Dict[str, str],
        log,
    ) -> None:
        repo_path = Path(repo_dir)
        pub_cache = Path(env["PUB_CACHE"])

        log(f"[{build_id}] 📦 Running Python setup workflow")
        self._ensure_git_cache(pub_cache, build_id, log)
        self._activate_global_package(repo_path, env, build_id, "melos", log)
        self._activate_global_package(repo_path, env, build_id, "flutterfire_cli", log)
        self._run_pub_get(repo_path, pub_cache, env, build_id, log)

    def prepare_platform_toolchain(
        self,
        *,
        build_id: str,
        platform: str,
        repo_dir: str,
        env: Dict[str, str],
        log,
    ) -> None:
        if platform == "android":
            self._prepare_android_toolchain(build_id, repo_dir, env, log)
            return
        if platform == "ios":
            self._prepare_ios_toolchain(build_id, repo_dir, env, log)
            return
        raise ValueError(f"Unsupported platform for toolchain preparation: {platform}")

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
    ) -> None:
        log(f"[{build_id}] 🔧 Activating {package_name}")
        result = self.command_runner.run_checked(
            ["fvm", "dart", "pub", "global", "activate", package_name],
            env=env,
            cwd=str(repo_path),
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
    ) -> None:
        pubspec = repo_path / "pubspec.yaml"
        has_melos = (repo_path / "melos.yaml").exists() or (repo_path / "pubspec.yaml").exists()
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
            result = self.command_runner.run(command, env=env, cwd=str(repo_path), check=False)
            for line in result.stdout.splitlines():
                if line.strip():
                    log(f"[{build_id}][SETUP] {line.strip()}")
            if result.returncode == 0:
                log(f"[{build_id}] ✅ Dependency resolution succeeded with {' '.join(command)}")
                return

        log(f"[{build_id}] ⚠️ Dependency resolution failed, repairing pub cache and retrying")
        self._log_git_dependency_access(repo_path, env, build_id, git_urls, log)
        self._reset_git_cache(pub_cache, build_id, log)
        repair = self.command_runner.run_checked(
            ["fvm", "flutter", "pub", "cache", "repair"],
            env=env,
            cwd=str(repo_path),
        )
        for line in repair.stdout.splitlines():
            if line.strip():
                log(f"[{build_id}][SETUP] {line.strip()}")

        retry_commands = [
            ["fvm", "exec", "melos", "run", "pub"],
            ["fvm", "flutter", "pub", "get", "--verbose"],
        ]
        for command in retry_commands:
            result = self.command_runner.run(command, env=env, cwd=str(repo_path), check=False)
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
    ) -> None:
        for url in urls:
            result = self.command_runner.run(
                ["git", "ls-remote", url, "HEAD"],
                env=env,
                cwd=str(repo_path),
                check=False,
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

    def _prepare_ios_toolchain(
        self,
        build_id: str,
        repo_dir: str,
        env: Dict[str, str],
        log,
    ) -> None:
        ios_dir = Path(repo_dir) / "ios"
        if not ios_dir.exists():
            return

        if (ios_dir / "Gemfile").exists():
            self._ensure_bundler(ios_dir, env, build_id, log)
            self._bundle_install(ios_dir, env, build_id, log)
            return

        self._ensure_gem("cocoapods", env.get("COCOAPODS_VERSION"), ios_dir, env, build_id, log)
        self._ensure_gem("fastlane", env.get("FASTLANE_VERSION"), ios_dir, env, build_id, log)
        self._install_fastlane_plugins(ios_dir, env, build_id, log)

    def _prepare_android_toolchain(
        self,
        build_id: str,
        repo_dir: str,
        env: Dict[str, str],
        log,
    ) -> None:
        android_dir = Path(repo_dir) / "android"
        if not android_dir.exists():
            return

        if (android_dir / "Gemfile").exists():
            self._ensure_bundler(android_dir, env, build_id, log)
            self._bundle_install(android_dir, env, build_id, log)
            return

        self._ensure_digest_crc(android_dir, env, build_id, log)
        self._ensure_gem("fastlane", env.get("FASTLANE_VERSION"), android_dir, env, build_id, log)

    def _ensure_bundler(self, cwd: Path, env: Dict[str, str], build_id: str, log) -> None:
        installed = self.command_runner.run(
            ["gem", "list", "-i", "bundler"],
            env=env,
            cwd=str(cwd),
            check=False,
        )
        if installed.returncode != 0:
            log(f"[{build_id}] 💎 Installing bundler")
            self.command_runner.run_checked(["gem", "install", "-N", "bundler"], env=env, cwd=str(cwd))

    def _bundle_install(self, cwd: Path, env: Dict[str, str], build_id: str, log) -> None:
        self.command_runner.run_checked(
            ["bundle", "config", "set", "--local", "path", env["GEM_HOME"]],
            env=env,
            cwd=str(cwd),
        )
        log(f"[{build_id}] 📦 Installing Ruby bundle in {cwd.name}")
        result = self.command_runner.run_checked(["bundle", "install"], env=env, cwd=str(cwd))
        for line in result.stdout.splitlines():
            if line.strip():
                log(f"[{build_id}][SETUP] {line.strip()}")

    def _ensure_gem(
        self,
        gem_name: str,
        version: str | None,
        cwd: Path,
        env: Dict[str, str],
        build_id: str,
        log,
    ) -> None:
        list_command = ["gem", "list", "-i", gem_name]
        if version:
            list_command.extend(["-v", version])
        installed = self.command_runner.run(list_command, env=env, cwd=str(cwd), check=False)
        if installed.returncode == 0:
            log(f"[{build_id}] ✅ {gem_name} already available")
            return

        install_command = ["gem", "install", "-N", gem_name]
        if version:
            install_command.extend(["-v", version])
        log(f"[{build_id}] 💎 Installing {gem_name}{f' {version}' if version else ''}")
        self.command_runner.run_checked(install_command, env=env, cwd=str(cwd))

    def _install_fastlane_plugins(self, ios_dir: Path, env: Dict[str, str], build_id: str, log) -> None:
        pluginfile = ios_dir / "fastlane" / "Pluginfile"
        if not pluginfile.exists():
            return

        plugin_pattern = re.compile(r"""gem\s+['"](fastlane-plugin-[^'"]+)['"]""")
        for line in pluginfile.read_text(encoding="utf-8").splitlines():
            match = plugin_pattern.search(line)
            if not match:
                continue
            plugin_name = match.group(1)
            installed = self.command_runner.run(
                ["gem", "list", "-i", plugin_name],
                env=env,
                cwd=str(ios_dir),
                check=False,
            )
            if installed.returncode == 0:
                continue
            log(f"[{build_id}] 🔌 Installing {plugin_name}")
            self.command_runner.run_checked(
                ["gem", "install", "-N", plugin_name],
                env=env,
                cwd=str(ios_dir),
            )

    def _ensure_digest_crc(self, cwd: Path, env: Dict[str, str], build_id: str, log) -> None:
        installed = self.command_runner.run(
            ["gem", "list", "-i", "digest-crc", "-v", "~> 0.4"],
            env=env,
            cwd=str(cwd),
            check=False,
        )
        if installed.returncode == 0:
            return

        log(f"[{build_id}] 💎 Installing digest-crc ~> 0.4 for Android fastlane dependencies")
        candidates = ["~> 0.4", "0.6.1", "0.5.1"]
        last_error: CommandExecutionError | None = None
        for version in candidates:
            try:
                self.command_runner.run_checked(
                    ["gem", "install", "-N", "digest-crc", "-v", version],
                    env=env,
                    cwd=str(cwd),
                )
                return
            except CommandExecutionError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
