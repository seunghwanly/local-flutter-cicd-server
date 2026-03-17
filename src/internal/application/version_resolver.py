"""Version resolution policies for build tools."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from ..domain import BuildRequestData


@dataclass
class ResolvedVersions:
    flutter_sdk_version: Optional[str]
    gradle_version: Optional[str]
    cocoapods_version: Optional[str]
    fastlane_version: Optional[str]


class VersionResolver:
    """Resolve requested versions against environment defaults."""

    def resolve(self, request: BuildRequestData) -> ResolvedVersions:
        return ResolvedVersions(
            flutter_sdk_version=request.flutter_sdk_version,
            gradle_version=request.gradle_version or os.environ.get("GRADLE_VERSION"),
            cocoapods_version=request.cocoapods_version or os.environ.get("COCOAPODS_VERSION"),
            fastlane_version=request.fastlane_version or os.environ.get("FASTLANE_VERSION"),
        )
