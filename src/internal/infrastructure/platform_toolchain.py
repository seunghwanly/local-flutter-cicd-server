"""Platform-specific toolchain preparation helpers."""

from __future__ import annotations

from dataclasses import dataclass
import platform
import secrets
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


@dataclass(frozen=True)
class PreparedKeychain:
    path: Path
    password: str | None
    search_list: list[str]
    original_default_keychain: str | None
    ephemeral: bool = False

    def match_name(self) -> str:
        keychain_dir = (Path.home() / "Library" / "Keychains").resolve()
        if self.path.parent == keychain_dir or self.path.parent.resolve() == keychain_dir:
            return self.path.name
        return str(self.path)


class IOSKeychainPreparer:
    """Unlock and register the macOS keychain used by iOS signing."""

    _KEYCHAIN_UNLOCK_TIMEOUT_SECONDS = "21600"
    _PARTITION_LIST_SERVICES = "apple-tool:,apple:,codesign:"

    def __init__(self, command_runner: CommandRunner) -> None:
        self.command_runner = command_runner

    def prepare(self, build_id: str, context: BuildRuntimeContext, cwd: Path, log, should_cancel=None) -> PreparedKeychain:
        """Ensure the keychain is unlocked and registered for this build.

        Heavy validation (existence and codesigning identities) is performed
        once at server startup via ``ConfigDiagnostics.validate_keychain_on_startup``.
        This method performs the per-build runtime steps that must be refreshed
        for each archive session: unlock, extend the auto-lock timeout,
        register in the search list, and set as default.
        For ephemeral keychains, Fastlane imports the signing identity later,
        so applying the partition list here would fail before any private key
        exists in the new keychain.
        """
        strategy = self._strategy(context)
        keychain_name = (context.env.get("KEYCHAIN_NAME") or "").strip()
        keychain_password = context.env.get("KEYCHAIN_PASSWORD")
        if strategy == "ephemeral":
            keychain_path, keychain_password = self._create_ephemeral_keychain(
                build_id,
                context,
                cwd,
                log,
                should_cancel=should_cancel,
            )
        else:
            if not keychain_name:
                raise RuntimeError("KEYCHAIN_NAME is required for iOS signing environment preparation")
            keychain_path = self._resolve_keychain_path(keychain_name) or self._planned_keychain_path(keychain_name)
            if keychain_path is None:
                raise RuntimeError(f"Configured keychain '{keychain_name}' could not be resolved")

        keychain_str = str(keychain_path)
        default_keychain = self.command_runner.run(
            ["security", "default-keychain", "-d", "user"],
            env=context.env,
            cwd=str(cwd),
            check=False,
            should_stop=should_cancel,
        )
        original_default_keychain = self._parse_default_keychain(default_keychain.stdout)

        # Ensure keychain remains available for long-running archive sessions.
        self.command_runner.run_checked(
            ["security", "set-keychain-settings", "-lut", self._KEYCHAIN_UNLOCK_TIMEOUT_SECONDS, keychain_str],
            env=context.env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )

        # Ensure keychain is in the search list
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

        # Unlock keychain for this build session
        if keychain_password:
            self.command_runner.run_checked(
                ["security", "unlock-keychain", "-p", keychain_password, keychain_str],
                env=context.env,
                cwd=str(cwd),
                should_stop=should_cancel,
            )
            if strategy != "ephemeral":
                self.command_runner.run_checked(
                    [
                        "security",
                        "set-key-partition-list",
                        "-S",
                        self._PARTITION_LIST_SERVICES,
                        "-s",
                        "-k",
                        keychain_password,
                        keychain_str,
                    ],
                    env=context.env,
                    cwd=str(cwd),
                    should_stop=should_cancel,
                )

        # Set as default keychain
        self.command_runner.run_checked(
            ["security", "default-keychain", "-d", "user", "-s", keychain_str],
            env=context.env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )
        log(f"[{build_id}] 🔐 Keychain ready: {keychain_path.name}")
        normalized_password = keychain_password.strip() if isinstance(keychain_password, str) else keychain_password
        return PreparedKeychain(
            path=keychain_path,
            password=normalized_password or None,
            search_list=search_list,
            original_default_keychain=original_default_keychain,
            ephemeral=(strategy == "ephemeral"),
        )

    def _resolve_keychain_path(self, keychain_name: str) -> Path | None:
        provided = Path(keychain_name).expanduser()
        if provided.exists():
            return provided.resolve()

        planned = self._planned_keychain_path(keychain_name)
        if planned and planned.exists():
            return planned.resolve()
        return None

    def _planned_keychain_path(self, keychain_name: str) -> Path | None:
        provided = Path(keychain_name).expanduser()
        if provided.is_absolute():
            return provided

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
        if keychain_name.endswith(".keychain-db"):
            return (keychain_dir / keychain_name).expanduser()
        if keychain_name.endswith(".keychain"):
            return (keychain_dir / f"{keychain_name}-db").expanduser()
        return (keychain_dir / f"{keychain_name}.keychain-db").expanduser()

    def _parse_keychains(self, output: str) -> list[str]:
        parsed: list[str] = []
        for line in output.splitlines():
            stripped = line.strip().strip('"')
            if stripped:
                parsed.append(str(Path(stripped).expanduser()))
        return parsed

    def _parse_default_keychain(self, output: str) -> str | None:
        for line in output.splitlines():
            stripped = line.strip().strip('"')
            if stripped:
                return str(Path(stripped).expanduser())
        return None

    def _is_login_keychain(self, keychain_path: Path) -> bool:
        name = keychain_path.name
        return name in {"login.keychain", "login.keychain-db"}

    def _strategy(self, context: BuildRuntimeContext) -> str:
        configured = (context.env.get("IOS_KEYCHAIN_STRATEGY") or "").strip().lower()
        if configured in {"configured", "ephemeral"}:
            return configured
        return "configured" if (context.env.get("KEYCHAIN_NAME") or "").strip() else "ephemeral"

    def _create_ephemeral_keychain(
        self,
        build_id: str,
        context: BuildRuntimeContext,
        cwd: Path,
        log,
        should_cancel=None,
    ) -> tuple[Path, str]:
        keychain_dir = Path(context.workspace) / "keychains"
        keychain_dir.mkdir(parents=True, exist_ok=True)
        keychain_path = (keychain_dir / f"{build_id}.keychain-db").resolve()
        keychain_password = secrets.token_urlsafe(24)
        self.command_runner.run_checked(
            ["security", "create-keychain", "-p", keychain_password, str(keychain_path)],
            env=context.env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )
        self.command_runner.run_checked(
            ["security", "set-keychain-settings", "-lut", "21600", str(keychain_path)],
            env=context.env,
            cwd=str(cwd),
            should_stop=should_cancel,
        )
        log(f"[{build_id}] 🔐 Created ephemeral keychain: {keychain_path.name}")
        return keychain_path, keychain_password


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

        self._validate_ios_runtime_requirements(build_id, context, log)
        prepared_keychain = self.ios_keychain.prepare(
            build_id,
            context,
            ios_dir,
            log,
            should_cancel=should_cancel,
        )
        self._configure_fastlane_keychain_env(build_id, context, prepared_keychain, log)
        self._register_keychain_cleanup(build_id, context, ios_dir, prepared_keychain, log)
        self._prepare_flutter_ios_artifacts(build_id, context, ios_dir, log, should_cancel=should_cancel)
        self._plan_ios_pod_install(build_id, context, ios_dir, log)
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
            if context.is_shorebird_patch():
                self.ruby_toolchain.ensure_gem(
                    "fastlane", context.env.get("FASTLANE_VERSION"), ios_dir, context.env, build_id, log, should_cancel=should_cancel
                )
                self.ruby_toolchain.install_fastlane_plugins(ios_dir, context.env, build_id, log, should_cancel=should_cancel)
            return

        self.ruby_toolchain.ensure_gem(
            "cocoapods", context.env.get("COCOAPODS_VERSION"), ios_dir, context.env, build_id, log, should_cancel=should_cancel
        )
        self.ruby_toolchain.ensure_gem(
            "fastlane", context.env.get("FASTLANE_VERSION"), ios_dir, context.env, build_id, log, should_cancel=should_cancel
        )
        self.ruby_toolchain.install_fastlane_plugins(ios_dir, context.env, build_id, log, should_cancel=should_cancel)

    def _validate_ios_runtime_requirements(self, build_id: str, context: BuildRuntimeContext, log) -> None:
        strategy = self.ios_keychain._strategy(context)
        if strategy == "configured":
            keychain_name = (context.env.get("KEYCHAIN_NAME") or "").strip()
            if not keychain_name:
                raise RuntimeError("KEYCHAIN_NAME is required for iOS builds")

            keychain_password = context.env.get("KEYCHAIN_PASSWORD", "").strip()
            keychain_path = (
                self.ios_keychain._resolve_keychain_path(keychain_name)
                or self.ios_keychain._planned_keychain_path(keychain_name)
            )
            if not keychain_password:
                resolved_name = keychain_path.name if keychain_path else keychain_name
                raise RuntimeError(
                    "KEYCHAIN_PASSWORD is required for configured iOS keychains "
                    f"to enable non-interactive codesigning ({resolved_name})"
                )

        match_password = (context.env.get("MATCH_PASSWORD") or "").strip()
        if not match_password:
            raise RuntimeError("MATCH_PASSWORD is required for iOS builds")

        has_appstore_api = all(
            (context.env.get(key) or "").strip()
            for key in ("APPSTORE_API_KEY_ID", "APPSTORE_ISSUER_ID", "APPSTORE_API_PRIVATE_KEY")
        )
        has_fastlane_session = all(
            (context.env.get(key) or "").strip()
            for key in ("FASTLANE_USER", "FASTLANE_PASSWORD")
        )
        if not has_appstore_api and not has_fastlane_session:
            raise RuntimeError(
                "App Store authentication is required for iOS builds. "
                "Set APPSTORE_API_KEY_ID/APPSTORE_ISSUER_ID/APPSTORE_API_PRIVATE_KEY or FASTLANE_USER/FASTLANE_PASSWORD."
            )

        log(f"[{build_id}] ✅ iOS signing prerequisites are present before Fastlane")

    def _configure_fastlane_keychain_env(
        self,
        build_id: str,
        context: BuildRuntimeContext,
        prepared_keychain: PreparedKeychain,
        log,
    ) -> None:
        match_keychain_name = prepared_keychain.match_name()
        context.env["KEYCHAIN_NAME"] = match_keychain_name
        context.env["MATCH_KEYCHAIN_NAME"] = match_keychain_name
        if prepared_keychain.password:
            context.env["KEYCHAIN_PASSWORD"] = prepared_keychain.password
            context.env["MATCH_KEYCHAIN_PASSWORD"] = prepared_keychain.password
            log(
                f"[{build_id}] 🔐 Fastlane match will use keychain "
                f"{context.env['MATCH_KEYCHAIN_NAME']}"
            )
            return

        context.env.pop("KEYCHAIN_PASSWORD", None)
        context.env.pop("MATCH_KEYCHAIN_PASSWORD", None)
        log(
            f"[{build_id}] ⚠️ Fastlane match keychain password is unavailable for "
            f"{context.env['MATCH_KEYCHAIN_NAME']}; the Fastfile must tolerate an existing session"
        )

    def _register_keychain_cleanup(
        self,
        build_id: str,
        context: BuildRuntimeContext,
        cwd: Path,
        prepared_keychain: PreparedKeychain,
        log,
    ) -> None:
        if not prepared_keychain.ephemeral:
            return

        def cleanup() -> None:
            if prepared_keychain.original_default_keychain:
                self.command_runner.run(
                    ["security", "default-keychain", "-d", "user", "-s", prepared_keychain.original_default_keychain],
                    env=context.env,
                    cwd=str(cwd),
                    check=False,
                )
            if prepared_keychain.search_list:
                self.command_runner.run(
                    ["security", "list-keychains", "-d", "user", "-s", *prepared_keychain.search_list],
                    env=context.env,
                    cwd=str(cwd),
                    check=False,
                )
            self.command_runner.run(
                ["security", "delete-keychain", str(prepared_keychain.path)],
                env=context.env,
                cwd=str(cwd),
                check=False,
            )
            log(f"[{build_id}] 🧹 Removed ephemeral keychain: {prepared_keychain.path.name}")

        context.cleanup_callbacks.append(cleanup)

    def _prepare_flutter_ios_artifacts(
        self,
        build_id: str,
        context: BuildRuntimeContext,
        ios_dir: Path,
        log,
        should_cancel=None,
    ) -> None:
        project_root = ios_dir.parent
        artifact_path = project_root / ".fvm" / "flutter_sdk" / "bin" / "cache" / "artifacts" / "engine" / "ios" / "Flutter.xcframework"
        if artifact_path.exists():
            return

        log(f"[{build_id}] 📦 Flutter iOS engine artifact missing; running fvm flutter precache --ios")
        self.command_runner.run_checked(
            ["fvm", "flutter", "precache", "--ios"],
            env=context.env,
            cwd=str(project_root),
            should_stop=should_cancel,
        )
        context.env["IOS_FLUTTER_SDK_CHANGED"] = "true"

    def _plan_ios_pod_install(self, build_id: str, context: BuildRuntimeContext, ios_dir: Path, log) -> None:
        requested_policy = (context.env.get("IOS_RUN_POD_INSTALL") or "auto").strip()
        normalized_policy = requested_policy.lower()
        reasons: list[str] = []
        should_run = False

        if normalized_policy in {"true", "1", "yes"}:
            should_run = True
            reasons.append(f"forced by IOS_RUN_POD_INSTALL={requested_policy}")
        elif normalized_policy in {"false", "0", "no"}:
            should_run = False
        else:
            if normalized_policy not in {"auto", ""}:
                log(f"[{build_id}] ⚠️ Unknown IOS_RUN_POD_INSTALL={requested_policy}; falling back to auto detection")
            should_run, reasons = self._detect_ios_pod_install_reasons(context, ios_dir)

        context.env["IOS_SHOULD_RUN_POD_INSTALL"] = "true" if should_run else "false"
        context.env["IOS_POD_INSTALL_REASONS"] = " | ".join(reasons)
        if should_run:
            log(f"[{build_id}] 📚 pod install scheduled: {' | '.join(reasons)}")
        else:
            log(f"[{build_id}] ⏭️ pod install not required before Fastlane")

    def _detect_ios_pod_install_reasons(self, context: BuildRuntimeContext, ios_dir: Path) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        podfile_lock = ios_dir / "Podfile.lock"
        pods_manifest = ios_dir / "Pods" / "Manifest.lock"
        pod_state_file = pods_manifest if pods_manifest.exists() else podfile_lock if podfile_lock.exists() else None

        if not podfile_lock.exists():
            reasons.append("Podfile.lock missing")
        if not (ios_dir / "Pods" / "Pods.xcodeproj").exists():
            reasons.append("Pods/Pods.xcodeproj missing")
        if not (ios_dir / "Runner.xcworkspace").exists():
            reasons.append("Runner.xcworkspace missing")
        if not (ios_dir / "Flutter" / "Generated.xcconfig").exists():
            reasons.append("Flutter/Generated.xcconfig missing")
        if podfile_lock.exists() and pods_manifest.exists() and podfile_lock.read_bytes() != pods_manifest.read_bytes():
            reasons.append("Podfile.lock and Pods/Manifest.lock differ")
        if (
            pod_state_file
            and (ios_dir / "Podfile").exists()
            and (ios_dir / "Podfile").stat().st_mtime > pod_state_file.stat().st_mtime
        ):
            reasons.append(f"Podfile is newer than {pod_state_file.relative_to(ios_dir)}")

        plugins_dependencies = ios_dir.parent / ".flutter-plugins-dependencies"
        if plugins_dependencies.exists():
            if pod_state_file is None:
                reasons.append(".flutter-plugins-dependencies changed without an existing pod state file")
            elif plugins_dependencies.stat().st_mtime > pod_state_file.stat().st_mtime:
                reasons.append(f".flutter-plugins-dependencies is newer than {pod_state_file.relative_to(ios_dir)}")

        if (context.env.get("IOS_FLUTTER_SDK_CHANGED") or "").strip().lower() == "true":
            reasons.append("Flutter SDK version changed since previous sync")

        return bool(reasons), reasons

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
