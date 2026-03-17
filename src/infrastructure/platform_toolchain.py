"""Platform-specific toolchain preparation helpers."""

from __future__ import annotations

import platform
import shutil
from pathlib import Path
from typing import Dict

from ..core import BuildRuntimeContext
from .command_runner import CommandRunner
from .ruby_toolchain import RubyToolchainPreparer


class ShorebirdCacheValidator:
    """Validate Shorebird cached artifacts before patch builds."""

    def __init__(self, command_runner: CommandRunner) -> None:
        self.command_runner = command_runner

    def prepare_if_needed(self, build_id: str, context: BuildRuntimeContext, cwd: Path, log, should_cancel=None) -> None:
        if not context.is_shorebird_patch():
            return

        shorebird_path = shutil.which("shorebird", path=context.env.get("PATH"))
        if not shorebird_path:
            log(f"[{build_id}] ⚠️ Shorebird CLI is not on PATH; skipping cache architecture validation")
            return

        patch_binary = Path(shorebird_path).resolve().parent / "cache" / "artifacts" / "patch" / "patch"
        if not patch_binary.exists():
            log(f"[{build_id}] 📦 Shorebird patch artifact is not cached yet; it will be downloaded during patch creation")
            return

        host_arch = platform.machine().strip().lower()
        artifact_arch = self._detect_binary_architecture(patch_binary, context.env, cwd, should_cancel=should_cancel)
        if not artifact_arch:
            log(f"[{build_id}] ⚠️ Unable to detect Shorebird patch artifact architecture at {patch_binary}")
            return

        if self._is_compatible_binary_architecture(host_arch, artifact_arch):
            log(f"[{build_id}] ✅ Shorebird patch artifact is compatible with host architecture ({host_arch})")
            return

        log(
            f"[{build_id}] 🧹 Shorebird patch artifact architecture mismatch "
            f"(host={host_arch}, artifact={artifact_arch}); clearing Shorebird cache"
        )
        self.command_runner.run_checked(
            ["shorebird", "cache", "clean"],
            env=context.env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )

    def _detect_binary_architecture(
        self,
        binary_path: Path,
        env: Dict[str, str],
        cwd: Path,
        should_cancel=None,
    ) -> str | None:
        result = self.command_runner.run(
            ["file", str(binary_path)],
            env=env,
            cwd=str(cwd),
            check=False,
            should_stop=should_cancel,
        )
        output = result.stdout.lower()
        if "arm64" in output:
            return "arm64"
        if "x86_64" in output:
            return "x86_64"
        if "universal" in output:
            return "universal"
        return None

    def _is_compatible_binary_architecture(self, host_arch: str, artifact_arch: str) -> bool:
        normalized_host = "arm64" if host_arch in {"arm64", "aarch64"} else host_arch
        if artifact_arch == "universal":
            return True
        return normalized_host == artifact_arch


class IOSKeychainPreparer:
    """Unlock and register the macOS keychain used by iOS signing."""

    def __init__(self, command_runner: CommandRunner) -> None:
        self.command_runner = command_runner

    def prepare(self, build_id: str, context: BuildRuntimeContext, cwd: Path, log, should_cancel=None) -> None:
        keychain_name = (context.env.get("KEYCHAIN_NAME") or "").strip()
        keychain_password = context.env.get("KEYCHAIN_PASSWORD")
        if not keychain_name:
            log(f"[{build_id}] ℹ️ KEYCHAIN_NAME not set; skipping keychain preparation")
            return
        if not keychain_password:
            raise RuntimeError("KEYCHAIN_PASSWORD is required when KEYCHAIN_NAME is set")

        keychain_path = self._resolve_keychain_path(keychain_name)
        if not keychain_path:
            raise RuntimeError(f"Configured keychain '{keychain_name}' could not be found")

        keychain_str = str(keychain_path)
        existing = self.command_runner.run(
            ["security", "list-keychains", "-d", "user"],
            env=context.env,
            cwd=str(cwd),
            check=False,
            should_stop=should_cancel,
        )
        search_list = self._parse_keychains(existing.stdout)
        if keychain_str not in search_list:
            search_list.append(keychain_str)
            self.command_runner.run_checked(
                ["security", "list-keychains", "-d", "user", "-s", *search_list],
                env=context.env,
                cwd=str(cwd),
                should_stop=should_cancel,
            )

        self.command_runner.run_checked(
            ["security", "unlock-keychain", "-p", keychain_password, keychain_str],
            env=context.env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )
        self.command_runner.run_checked(
            ["security", "set-keychain-settings", "-lut", "21600", keychain_str],
            env=context.env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )
        self.command_runner.run_checked(
            ["security", "default-keychain", "-d", "user", "-s", keychain_str],
            env=context.env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )
        context.env["MATCH_KEYCHAIN_NAME"] = keychain_str
        context.env["MATCH_KEYCHAIN_PASSWORD"] = keychain_password
        log(f"[{build_id}] 🔐 Prepared keychain: {keychain_path.name}")

    def _resolve_keychain_path(self, keychain_name: str) -> Path | None:
        provided = Path(keychain_name).expanduser()
        if provided.exists():
            return provided.resolve()

        keychain_dir = Path.home() / "Library" / "Keychains"
        candidates = [keychain_name]
        if keychain_name.endswith(".keychain"):
            candidates.append(f"{keychain_name}-db")
        elif not keychain_name.endswith(".keychain-db"):
            candidates.extend(
                [
                    f"{keychain_name}.keychain-db",
                    f"{keychain_name}.keychain",
                ]
            )
        for candidate in candidates:
            path = (keychain_dir / candidate).expanduser()
            if path.exists():
                return path.resolve()
        return None

    def _parse_keychains(self, output: str) -> list[str]:
        parsed: list[str] = []
        for line in output.splitlines():
            stripped = line.strip().strip('"')
            if stripped:
                parsed.append(str(Path(stripped).expanduser()))
        return parsed


class PlatformToolchainPreparer:
    """Prepare per-platform Ruby and native build toolchains."""

    def __init__(
        self,
        command_runner: CommandRunner,
        ruby_toolchain: RubyToolchainPreparer | None = None,
        shorebird_validator: ShorebirdCacheValidator | None = None,
        ios_keychain: IOSKeychainPreparer | None = None,
    ) -> None:
        self.command_runner = command_runner
        self.ruby_toolchain = ruby_toolchain or RubyToolchainPreparer(command_runner)
        self.shorebird_validator = shorebird_validator or ShorebirdCacheValidator(command_runner)
        self.ios_keychain = ios_keychain or IOSKeychainPreparer(command_runner)

    def prepare(
        self,
        *,
        build_id: str,
        platform: str,
        context: BuildRuntimeContext,
        log,
        should_cancel=None,
    ) -> None:
        if platform == "android":
            self._prepare_android_toolchain(build_id, context, log, should_cancel=should_cancel)
            return
        if platform == "ios":
            self._prepare_ios_toolchain(build_id, context, log, should_cancel=should_cancel)
            return
        raise ValueError(f"Unsupported platform for toolchain preparation: {platform}")

    def preflight(
        self,
        *,
        build_id: str,
        platform: str,
        context: BuildRuntimeContext,
        log,
        should_cancel=None,
    ) -> None:
        if platform != "android":
            return
        android_dir = Path(context.repo_dir) / "android"
        if not android_dir.exists():
            return
        self.shorebird_validator.prepare_if_needed(build_id, context, android_dir, log, should_cancel=should_cancel)

    def _prepare_ios_toolchain(
        self,
        build_id: str,
        context: BuildRuntimeContext,
        log,
        should_cancel=None,
    ) -> None:
        ios_dir = Path(context.repo_dir) / "ios"
        if not ios_dir.exists():
            return

        self.ios_keychain.prepare(build_id, context, ios_dir, log, should_cancel=should_cancel)
        self.ruby_toolchain.configure_environment(ios_dir, context.env, build_id, log, should_cancel=should_cancel)
        if (ios_dir / "Gemfile").exists():
            self.ruby_toolchain.ensure_gem(
                "cocoapods", context.env.get("COCOAPODS_VERSION"), ios_dir, context.env, build_id, log, should_cancel=should_cancel
            )
            bundler_version = self.ruby_toolchain.ensure_bundler(
                ios_dir, context.env, build_id, log, should_cancel=should_cancel
            )
            self.ruby_toolchain.bundle_install(
                ios_dir,
                context.env,
                build_id,
                log,
                bundler_version=bundler_version,
                should_cancel=should_cancel,
            )
            return

        self.ruby_toolchain.ensure_gem(
            "cocoapods", context.env.get("COCOAPODS_VERSION"), ios_dir, context.env, build_id, log, should_cancel=should_cancel
        )
        self.ruby_toolchain.ensure_gem(
            "fastlane", context.env.get("FASTLANE_VERSION"), ios_dir, context.env, build_id, log, should_cancel=should_cancel
        )
        self.ruby_toolchain.install_fastlane_plugins(ios_dir, context.env, build_id, log, should_cancel=should_cancel)

    def _prepare_android_toolchain(
        self,
        build_id: str,
        context: BuildRuntimeContext,
        log,
        should_cancel=None,
    ) -> None:
        android_dir = Path(context.repo_dir) / "android"
        if not android_dir.exists():
            return

        self.ruby_toolchain.configure_environment(android_dir, context.env, build_id, log, should_cancel=should_cancel)
        if (android_dir / "Gemfile").exists():
            bundler_version = self.ruby_toolchain.ensure_bundler(
                android_dir, context.env, build_id, log, should_cancel=should_cancel
            )
            self.ruby_toolchain.bundle_install(
                android_dir,
                context.env,
                build_id,
                log,
                bundler_version=bundler_version,
                should_cancel=should_cancel,
            )
            return

        self.ruby_toolchain.ensure_digest_crc(android_dir, context.env, build_id, log, should_cancel=should_cancel)
        self.ruby_toolchain.ensure_gem(
            "fastlane", context.env.get("FASTLANE_VERSION"), android_dir, context.env, build_id, log, should_cancel=should_cancel
        )
