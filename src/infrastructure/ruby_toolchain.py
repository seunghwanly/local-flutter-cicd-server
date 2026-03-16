"""Ruby toolchain preparation helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict

from .command_runner import CommandExecutionError, CommandRunner


class RubyToolchainPreparer:
    """Resolve Ruby/Bundler/gem dependencies for mobile build directories."""

    _VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)+)")

    def __init__(self, command_runner: CommandRunner) -> None:
        self.command_runner = command_runner

    def configure_environment(self, cwd: Path, env: Dict[str, str], build_id: str, log, should_cancel=None) -> None:
        self._prepend_rbenv_to_path(env)

        requested_ruby, requested_source = self._resolve_requested_ruby_version(cwd, env)
        if requested_ruby:
            log(f"[{build_id}] 💎 Requested Ruby version: {requested_ruby}")
            selected_ruby = self._select_ruby_version(
                cwd,
                env,
                requested_ruby,
                requested_source or "unknown",
                build_id,
                log,
                should_cancel=should_cancel,
            )
            if selected_ruby:
                env["RBENV_VERSION"] = selected_ruby

        current_ruby = self.current_ruby_version(cwd, env, should_cancel=should_cancel)
        if current_ruby:
            log(f"[{build_id}] 💎 Active Ruby version: {current_ruby}")

        lockfile_ruby = self._parse_lockfile_ruby_version(cwd)
        if lockfile_ruby and current_ruby and self._compare_versions(current_ruby, lockfile_ruby) < 0:
            raise RuntimeError(
                f"Gemfile.lock requires Ruby {lockfile_ruby}+ but active Ruby is {current_ruby}. "
                "Install that version with rbenv and set RUBY_VERSION, .ruby-version, or .tool-versions."
            )

    def ensure_bundler(
        self,
        cwd: Path,
        env: Dict[str, str],
        build_id: str,
        log,
        should_cancel=None,
    ) -> str | None:
        locked_version = self._parse_lockfile_bundler_version(cwd)
        if locked_version:
            installed = self.command_runner.run(
                ["gem", "list", "-i", "bundler", "-v", locked_version],
                env=env,
                cwd=str(cwd),
                check=False,
                should_stop=should_cancel,
            )
            if installed.returncode != 0:
                log(f"[{build_id}] 💎 Installing bundler {locked_version} from Gemfile.lock")
                self.command_runner.run_checked(
                    ["gem", "install", "-N", "bundler", "-v", locked_version],
                    env=env,
                    cwd=str(cwd),
                    should_stop=should_cancel,
                )
            return locked_version

        installed = self.command_runner.run(
            ["gem", "list", "-i", "bundler"],
            env=env,
            cwd=str(cwd),
            check=False,
            should_stop=should_cancel,
        )
        if installed.returncode != 0:
            log(f"[{build_id}] 💎 Installing bundler")
            self.command_runner.run_checked(
                ["gem", "install", "-N", "bundler"],
                env=env,
                cwd=str(cwd),
                should_stop=should_cancel,
            )
        return None

    def bundle_install(
        self,
        cwd: Path,
        env: Dict[str, str],
        build_id: str,
        log,
        bundler_version: str | None = None,
        should_cancel=None,
    ) -> None:
        bundle_path = str(Path(env["GEM_HOME"]) / "bundle")
        bundle_command = self._bundle_command(bundler_version, "config", "set", "--local", "path", bundle_path)
        self.command_runner.run_checked(
            bundle_command,
            env=env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )
        log(f"[{build_id}] 📦 Installing Ruby bundle in {cwd.name}")
        install_command = self._bundle_command(bundler_version, "install")
        try:
            result = self.command_runner.run_checked(
                install_command,
                env=env,
                cwd=str(cwd),
                should_stop=should_cancel,
            )
        except CommandExecutionError as exc:
            self._raise_bundle_install_error(cwd, env, exc)
        for line in result.stdout.splitlines():
            if line.strip():
                log(f"[{build_id}][SETUP] {line.strip()}")

    def ensure_gem(
        self,
        gem_name: str,
        version: str | None,
        cwd: Path,
        env: Dict[str, str],
        build_id: str,
        log,
        should_cancel=None,
    ) -> None:
        list_command = ["gem", "list", "-i", gem_name]
        if version:
            list_command.extend(["-v", version])
        installed = self.command_runner.run(
            list_command,
            env=env,
            cwd=str(cwd),
            check=False,
            should_stop=should_cancel,
        )
        if installed.returncode == 0:
            log(f"[{build_id}] ✅ {gem_name} already available")
            return

        install_command = ["gem", "install", "-N", gem_name]
        if version:
            install_command.extend(["-v", version])
        log(f"[{build_id}] 💎 Installing {gem_name}{f' {version}' if version else ''}")
        self.command_runner.run_checked(
            install_command,
            env=env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )

    def install_fastlane_plugins(self, ios_dir: Path, env: Dict[str, str], build_id: str, log, should_cancel=None) -> None:
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
                should_stop=should_cancel,
            )
            if installed.returncode == 0:
                continue
            log(f"[{build_id}] 🔌 Installing {plugin_name}")
            self.command_runner.run_checked(
                ["gem", "install", "-N", plugin_name],
                env=env,
                cwd=str(ios_dir),
                should_stop=should_cancel,
            )

    def ensure_digest_crc(self, cwd: Path, env: Dict[str, str], build_id: str, log, should_cancel=None) -> None:
        installed = self.command_runner.run(
            ["gem", "list", "-i", "digest-crc", "-v", "~> 0.4"],
            env=env,
            cwd=str(cwd),
            check=False,
            should_stop=should_cancel,
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
                    should_stop=should_cancel,
                )
                return
            except CommandExecutionError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error

    def current_ruby_version(self, cwd: Path, env: Dict[str, str], should_cancel=None) -> str | None:
        result = self.command_runner.run(
            ["ruby", "-e", "print RUBY_VERSION"],
            env=env,
            cwd=str(cwd),
            check=False,
            should_stop=should_cancel,
        )
        version = result.stdout.strip()
        return version or None

    def _resolve_requested_ruby_version(self, cwd: Path, env: Dict[str, str]) -> tuple[str | None, str | None]:
        ruby_version_file = cwd / ".ruby-version"
        if ruby_version_file.exists():
            version = ruby_version_file.read_text(encoding="utf-8").strip()
            if version:
                return version, ".ruby-version"

        tool_versions_file = cwd / ".tool-versions"
        if tool_versions_file.exists():
            for line in tool_versions_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("ruby "):
                    _, version = stripped.split(None, 1)
                    resolved = version.strip() or None
                    return resolved, ".tool-versions"

        lockfile_version = self._parse_lockfile_ruby_version(cwd)
        if lockfile_version:
            return lockfile_version, "Gemfile.lock"

        configured_version = env.get("RUBY_VERSION") or os.environ.get("RUBY_VERSION")
        if configured_version:
            return configured_version.strip(), "RUBY_VERSION"
        return None, None

    def _parse_lockfile_bundler_version(self, cwd: Path) -> str | None:
        lockfile = cwd / "Gemfile.lock"
        if not lockfile.exists():
            return None

        lines = lockfile.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.strip() != "BUNDLED WITH":
                continue
            for candidate in lines[index + 1:]:
                stripped = candidate.strip()
                if stripped:
                    return stripped
        return None

    def _parse_lockfile_ruby_version(self, cwd: Path) -> str | None:
        lockfile = cwd / "Gemfile.lock"
        if not lockfile.exists():
            return None

        lines = lockfile.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.strip() != "RUBY VERSION":
                continue
            for candidate in lines[index + 1:]:
                stripped = candidate.strip()
                if not stripped:
                    continue
                match = self._VERSION_PATTERN.search(stripped)
                return match.group(1) if match else None
        return None

    def _prepend_rbenv_to_path(self, env: Dict[str, str]) -> None:
        rbenv_root = Path(os.environ.get("RBENV_ROOT", Path.home() / ".rbenv")).expanduser()
        path_entries = env.get("PATH", "").split(":") if env.get("PATH") else []
        additions = [str(rbenv_root / "shims"), str(rbenv_root / "bin")]
        merged: list[str] = []
        for entry in additions + path_entries:
            if entry and entry not in merged:
                merged.append(entry)
        env["PATH"] = ":".join(merged)

    def _select_ruby_version(
        self,
        cwd: Path,
        env: Dict[str, str],
        requested_ruby: str,
        requested_source: str,
        build_id: str,
        log,
        should_cancel=None,
    ) -> str | None:
        rbenv_exists = self.command_runner.run(
            ["rbenv", "versions", "--bare"],
            env=env,
            cwd=str(cwd),
            check=False,
            should_stop=should_cancel,
        )
        if rbenv_exists.returncode != 0:
            log(f"[{build_id}] ⚠️ rbenv not available, continuing with system Ruby")
            return None

        installed_versions = {line.strip() for line in rbenv_exists.stdout.splitlines() if line.strip()}
        if requested_ruby in installed_versions:
            return requested_ruby

        if requested_source in {"Gemfile.lock", "RUBY_VERSION"}:
            compatible_versions = sorted(
                (version for version in installed_versions if self._compare_versions(version, requested_ruby) >= 0),
                key=self._version_sort_key,
            )
            if compatible_versions:
                selected = compatible_versions[0]
                log(
                    f"[{build_id}] 💎 Using compatible installed Ruby {selected} "
                    f"for {requested_source} requirement {requested_ruby}+"
                )
                return selected

        raise RuntimeError(
            f"Requested Ruby {requested_ruby} from {requested_source} is not installed in rbenv. "
            f"Installed versions: {', '.join(sorted(installed_versions)) or 'none'}"
        )

    def _bundle_command(self, bundler_version: str | None, *args: str) -> list[str]:
        if bundler_version:
            return ["bundle", f"_{bundler_version}_", *args]
        return ["bundle", *args]

    def _raise_bundle_install_error(
        self,
        cwd: Path,
        env: Dict[str, str],
        exc: CommandExecutionError,
    ) -> None:
        ruby_requirement = re.search(r"requires ruby version >=\s*([0-9.]+)", exc.output)
        if ruby_requirement:
            required = ruby_requirement.group(1)
            current = self.current_ruby_version(cwd, env) or "unknown"
            raise RuntimeError(
                f"bundle install requires Ruby {required}+ but active Ruby is {current}. "
                "Install a newer Ruby with rbenv and set RUBY_VERSION, .ruby-version, or .tool-versions."
            ) from exc
        raise exc

    def _compare_versions(self, left: str, right: str) -> int:
        left_parts = [int(part) for part in left.split(".")]
        right_parts = [int(part) for part in right.split(".")]
        size = max(len(left_parts), len(right_parts))
        left_parts.extend([0] * (size - len(left_parts)))
        right_parts.extend([0] * (size - len(right_parts)))
        if left_parts < right_parts:
            return -1
        if left_parts > right_parts:
            return 1
        return 0

    def _version_sort_key(self, version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in version.split("."))
