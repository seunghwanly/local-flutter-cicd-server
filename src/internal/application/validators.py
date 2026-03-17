"""Validation logic for external build requests."""

from __future__ import annotations

import re

from ..domain import BuildRequestData


class BuildRequestValidator:
    """Centralized validation and normalization for build inputs."""

    ALLOWED_FLAVORS = {"dev", "stage", "prod"}
    ALLOWED_PLATFORMS = {"all", "android", "ios"}

    _SAFE_TEXT_PATTERN = re.compile(r"^[A-Za-z0-9._/+:-]+$")
    _SAFE_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
    _SAFE_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")

    def validate(self, request: BuildRequestData) -> BuildRequestData:
        if request.flavor not in self.ALLOWED_FLAVORS:
            raise ValueError(f"Unsupported flavor: {request.flavor}")

        if request.platform not in self.ALLOWED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {request.platform}")

        request.build_name = self._validate_optional(
            "build_name", request.build_name, self._SAFE_TEXT_PATTERN
        )
        request.build_number = self._validate_optional(
            "build_number", request.build_number, self._SAFE_TEXT_PATTERN
        )
        request.branch_name = self._validate_optional(
            "branch_name", request.branch_name, self._SAFE_BRANCH_PATTERN
        )
        request.flutter_sdk_version = self._validate_optional(
            "flutter_sdk_version", request.flutter_sdk_version, self._SAFE_VERSION_PATTERN
        )
        request.gradle_version = self._validate_optional(
            "gradle_version", request.gradle_version, self._SAFE_VERSION_PATTERN
        )
        request.cocoapods_version = self._validate_optional(
            "cocoapods_version", request.cocoapods_version, self._SAFE_VERSION_PATTERN
        )
        request.fastlane_version = self._validate_optional(
            "fastlane_version", request.fastlane_version, self._SAFE_VERSION_PATTERN
        )

        if request.trigger_source in {"shorebird", "shorebird_manual"}:
            if not request.build_name:
                raise ValueError("Shorebird patch requires build_name as release version")

        return request

    def _validate_optional(self, field_name: str, value: str | None, pattern: re.Pattern[str]) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None

        if not pattern.fullmatch(normalized):
            raise ValueError(f"Invalid {field_name}: {value}")

        return normalized
