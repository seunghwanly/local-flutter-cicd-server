"""Feature-scoped environment diagnostics."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Dict, List

from ..domain import BuildRequestData


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

    WEBHOOK_VARS = [
        "GITHUB_WEBHOOK_SECRET",
    ]

    def get_build_diagnostics(self, request: BuildRequestData) -> DiagnosticResult:
        required = list(self.COMMON_BUILD_VARS)

        lane_key = f"{request.flavor.upper()}_FASTLANE_LANE"
        branch_key = f"{request.flavor.upper()}_BRANCH_NAME"
        required.extend([lane_key, branch_key])

        if request.platform in {"all", "ios"}:
            required.extend(self.IOS_BUILD_VARS)

        missing = self._find_missing(required)
        return DiagnosticResult(
            feature="build",
            ready=not missing,
            missing=missing,
            details={
                "flavor": request.flavor,
                "platform": request.platform,
            },
        )

    def get_webhook_diagnostics(self) -> DiagnosticResult:
        missing = self._find_missing(self.WEBHOOK_VARS)
        return DiagnosticResult(feature="webhook", ready=not missing, missing=missing, details={})

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

    def get_runtime_diagnostics(self) -> Dict[str, DiagnosticResult]:
        return {
            "toolchain": self.get_toolchain_diagnostics(),
            "environment": self.get_environment_diagnostics(),
            "webhook": self.get_webhook_diagnostics(),
        }

    def _find_missing(self, keys: List[str]) -> List[str]:
        return [key for key in keys if not os.environ.get(key)]
