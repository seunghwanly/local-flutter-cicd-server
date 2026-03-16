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


class PlatformToolchainPreparer:
    """Prepare per-platform Ruby and native build toolchains."""

    def __init__(
        self,
        command_runner: CommandRunner,
        ruby_toolchain: RubyToolchainPreparer | None = None,
        shorebird_validator: ShorebirdCacheValidator | None = None,
    ) -> None:
        self.command_runner = command_runner
        self.ruby_toolchain = ruby_toolchain or RubyToolchainPreparer(command_runner)
        self.shorebird_validator = shorebird_validator or ShorebirdCacheValidator(command_runner)

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
