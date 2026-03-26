"""Feature-scoped environment diagnostics."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from ..domain import BuildRequestData

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticResult:
    feature: str
    ready: bool
    missing: List[str]
    details: Dict[str, str]


class ConfigDiagnostics:
    """Validate required environment variables per feature instead of at process import time."""

    COMMON_BUILD_VARS = [
        "REPO_URL",
    ]

    IOS_BUILD_VARS = [
        "MATCH_PASSWORD",
    ]

    def __init__(self) -> None:
        self._keychain_result: DiagnosticResult | None = None

    GITHUB_ACTION_VARS = [
        "GITHUB_WEBHOOK_SECRET",
    ]

    def validate_keychain_on_startup(self) -> DiagnosticResult:
        """Run keychain diagnostics once at server startup and cache the result."""
        self._keychain_result = self.get_keychain_diagnostics()
        return self._keychain_result

    @property
    def keychain_ready(self) -> bool:
        """Whether the keychain was validated successfully at startup."""
        if self._keychain_strategy() == "ephemeral":
            return True
        return self._keychain_result is not None and self._keychain_result.ready

    def get_build_diagnostics(self, request: BuildRequestData) -> DiagnosticResult:
        required = list(self.COMMON_BUILD_VARS)

        if request.trigger_source in {"shorebird", "shorebird_manual"}:
            lane_key = f"SHOREBIRD_{request.flavor.upper()}_FASTLANE_LANE"
        else:
            lane_key = f"{request.flavor.upper()}_FASTLANE_LANE"
        branch_key = f"{request.flavor.upper()}_BRANCH_NAME"
        required.extend([lane_key, branch_key])

        if request.platform in {"all", "ios"}:
            required.extend(self.IOS_BUILD_VARS)
            if self._keychain_strategy() == "configured":
                required.append("KEYCHAIN_NAME")

        missing = self._find_missing(required)

        # Check cached keychain state for iOS builds
        if request.platform in {"all", "ios"} and not self.keychain_ready:
            keychain_issues = (
                self._keychain_result.missing if self._keychain_result else ["keychain not validated at startup"]
            )
            for issue in keychain_issues:
                missing.append(f"keychain: {issue}")

        return DiagnosticResult(
            feature="build",
            ready=not missing,
            missing=missing,
            details={
                "flavor": request.flavor,
                "platform": request.platform,
            },
        )

    def get_github_action_diagnostics(self) -> DiagnosticResult:
        missing = self._find_missing(self.GITHUB_ACTION_VARS)
        return DiagnosticResult(feature="github_action", ready=not missing, missing=missing, details={})

    def get_shorebird_action_diagnostics(self) -> DiagnosticResult:
        missing = self._find_missing(self.GITHUB_ACTION_VARS)
        details = {
            "default_flavor": os.environ.get("SHOREBIRD_PATCH_FLAVOR", "prod"),
            "default_platform": os.environ.get("SHOREBIRD_PATCH_PLATFORM", "all"),
            "default_branch_name": os.environ.get("SHOREBIRD_PATCH_BRANCH_NAME", "unset"),
            "signature_source": "GITHUB_WEBHOOK_SECRET",
        }
        return DiagnosticResult(
            feature="shorebird_action",
            ready=not missing,
            missing=missing,
            details=details,
        )

    def get_webhook_diagnostics(self) -> DiagnosticResult:
        return self.get_github_action_diagnostics()

    def get_toolchain_diagnostics(self) -> DiagnosticResult:
        required_commands = ["git", "fvm", "ruby", "gem", "bundle", "pod"]
        details = {
            command: shutil.which(command) or "missing"
            for command in required_commands
        }
        missing = [command for command, resolved in details.items() if resolved == "missing"]
        return DiagnosticResult(
            feature="toolchain",
            ready=not missing,
            missing=missing,
            details=details,
        )

    def get_environment_diagnostics(self) -> DiagnosticResult:
        optional_keys = [
            "WORKSPACE_ROOT",
            "FLUTTER_VERSION",
            "GRADLE_VERSION",
            "COCOAPODS_VERSION",
            "FASTLANE_VERSION",
        ]
        details = {
            key: os.environ.get(key, "unset")
            for key in optional_keys
        }
        return DiagnosticResult(
            feature="environment",
            ready=True,
            missing=[],
            details=details,
        )

    def get_keychain_diagnostics(self) -> DiagnosticResult:
        """Validate macOS keychain readiness for iOS codesigning."""
        missing: List[str] = []
        details: Dict[str, str] = {}
        strategy = self._keychain_strategy()
        details["strategy"] = strategy

        if strategy == "ephemeral":
            details["keychain_name"] = "generated per build"
            return DiagnosticResult(feature="keychain", ready=True, missing=missing, details=details)

        keychain_name = (os.environ.get("KEYCHAIN_NAME") or "").strip()
        keychain_password = os.environ.get("KEYCHAIN_PASSWORD", "")
        if not keychain_name:
            missing.append("KEYCHAIN_NAME")
            return DiagnosticResult(feature="keychain", ready=False, missing=missing, details=details)

        details["keychain_name"] = keychain_name

        # --- resolve keychain path ---
        keychain_path = self._resolve_keychain_path(keychain_name)
        if keychain_path is None:
            missing.append(f"keychain file not found: {keychain_name}")
            return DiagnosticResult(feature="keychain", ready=False, missing=missing, details=details)

        details["keychain_path"] = str(keychain_path)
        is_login = keychain_path.name in {"login.keychain", "login.keychain-db"}
        details["is_login_keychain"] = str(is_login)

        # --- unlock test ---
        env = os.environ.copy()
        cwd = os.getcwd()
        unlock_ok = False
        if keychain_password:
            result = subprocess.run(
                ["security", "unlock-keychain", "-p", keychain_password, str(keychain_path)],
                capture_output=True, text=True, env=env, cwd=cwd,
            )
            if result.returncode == 0:
                unlock_ok = True
                details["unlock"] = "ok"
            else:
                details["unlock"] = f"failed (exit {result.returncode})"
                missing.append("keychain unlock failed with KEYCHAIN_PASSWORD")
        else:
            details["unlock"] = "skipped (missing KEYCHAIN_PASSWORD)"
            missing.append("KEYCHAIN_PASSWORD (required for configured keychain)")

        # --- partition list test ---
        if unlock_ok and keychain_password:
            result = subprocess.run(
                [
                    "security", "set-key-partition-list",
                    "-S", "apple-tool:,apple:,codesign:",
                    "-s", "-k", keychain_password, str(keychain_path),
                ],
                capture_output=True, text=True, env=env, cwd=cwd,
            )
            if result.returncode == 0:
                details["partition_list"] = "ok"
            else:
                details["partition_list"] = f"failed (exit {result.returncode})"
                missing.append(
                    "set-key-partition-list failed — codesign will get errSecInternalComponent"
                )

        # --- codesigning identity check ---
        result = subprocess.run(
            ["security", "find-identity", "-v", "-p", "codesigning", str(keychain_path)],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip() and "valid identities found" not in l.lower()]
            identity_count = len(lines)
            details["codesign_identities"] = str(identity_count)
            if identity_count == 0:
                missing.append("no codesigning identities found in keychain")
        else:
            details["codesign_identities"] = "check failed"

        return DiagnosticResult(
            feature="keychain",
            ready=not missing,
            missing=missing,
            details=details,
        )

    def get_runtime_diagnostics(self) -> Dict[str, DiagnosticResult]:
        results: Dict[str, DiagnosticResult] = {
            "toolchain": self.get_toolchain_diagnostics(),
            "environment": self.get_environment_diagnostics(),
            "github_action": self.get_github_action_diagnostics(),
            "shorebird_action": self.get_shorebird_action_diagnostics(),
        }
        if self._keychain_strategy() in {"configured", "ephemeral"}:
            results["keychain"] = self.get_keychain_diagnostics()
        return results

    def _resolve_keychain_path(self, keychain_name: str) -> Path | None:
        provided = Path(keychain_name).expanduser()
        if provided.is_absolute() and provided.exists():
            return provided.resolve()

        keychain_dir = Path.home() / "Library" / "Keychains"
        candidates = [keychain_name]
        if keychain_name.endswith(".keychain"):
            candidates.append(f"{keychain_name}-db")
        elif not keychain_name.endswith(".keychain-db"):
            candidates.extend([f"{keychain_name}.keychain-db", f"{keychain_name}.keychain"])
        for candidate in candidates:
            path = keychain_dir / candidate
            if path.exists():
                return path.resolve()
        return None

    def _find_missing(self, keys: List[str]) -> List[str]:
        return [key for key in keys if not os.environ.get(key)]

    def _keychain_strategy(self) -> str:
        configured = (os.environ.get("IOS_KEYCHAIN_STRATEGY") or "").strip().lower()
        if configured in {"configured", "ephemeral"}:
            return configured
        return "configured" if (os.environ.get("KEYCHAIN_NAME") or "").strip() else "ephemeral"
