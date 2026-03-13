"""Core build domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional


class BuildStatus(str, Enum):
    """High-level lifecycle for a build job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(str, Enum):
    """Per-stage lifecycle for pipeline visibility."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BuildRequestData:
    """Validated input for a build pipeline."""

    flavor: str
    platform: str
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    branch_name: Optional[str] = None
    flutter_sdk_version: Optional[str] = None
    gradle_version: Optional[str] = None
    cocoapods_version: Optional[str] = None
    fastlane_version: Optional[str] = None


@dataclass
class BuildProgress:
    """Structured progress for a single platform build."""

    current_step: str = "starting"
    percentage: int = 0
    current_message: str = "Starting build..."
    steps_completed: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StageState:
    """Structured state for one pipeline stage."""

    name: str
    status: StageStatus = StageStatus.PENDING
    message: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class BuildJob:
    """Runtime representation of an in-flight or completed build."""

    build_id: str
    started_at: str
    flavor: str
    platform: str
    branch_name: str
    queue_key: str
    flutter_sdk_version: Optional[str] = None
    gradle_version: Optional[str] = None
    cocoapods_version: Optional[str] = None
    fastlane_version: Optional[str] = None
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    resolved_flutter_sdk_version: Optional[str] = None
    status: BuildStatus = BuildStatus.PENDING
    logs: List[str] = field(default_factory=list)
    progress: Dict[str, BuildProgress] = field(default_factory=dict)
    stages: Dict[str, StageState] = field(default_factory=dict)
    processes: Dict[str, Any] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock, repr=False)

    @classmethod
    def create(
        cls,
        build_id: str,
        request: BuildRequestData,
        branch_name: str,
        queue_key: str,
    ) -> "BuildJob":
        """Create a new job from a validated request."""
        stage_names = [
            "request_validated",
            "environment_prepared",
            "repository_synced",
            "flutter_sdk_resolved",
            "flutter_precached",
            "dependencies_installed",
        ]
        if request.platform in {"all", "android"}:
            stage_names.extend(["android_toolchain_ready", "android_build"])
        if request.platform in {"all", "ios"}:
            stage_names.extend(["ios_toolchain_ready", "ios_build"])

        return cls(
            build_id=build_id,
            started_at=datetime.now().isoformat(),
            flavor=request.flavor,
            platform=request.platform,
            branch_name=branch_name,
            queue_key=queue_key,
            flutter_sdk_version=request.flutter_sdk_version,
            gradle_version=request.gradle_version,
            cocoapods_version=request.cocoapods_version,
            fastlane_version=request.fastlane_version,
            build_name=request.build_name,
            build_number=request.build_number,
            stages={name: StageState(name=name) for name in stage_names},
        )

    def mark_stage_running(self, name: str, message: str = "") -> None:
        stage = self.stages.setdefault(name, StageState(name=name))
        stage.status = StageStatus.RUNNING
        stage.message = message
        if not stage.started_at:
            stage.started_at = datetime.now().isoformat()

    def mark_stage_completed(self, name: str, message: str = "") -> None:
        stage = self.stages.setdefault(name, StageState(name=name))
        if not stage.started_at:
            stage.started_at = datetime.now().isoformat()
        stage.status = StageStatus.COMPLETED
        stage.message = message
        stage.completed_at = datetime.now().isoformat()

    def mark_stage_failed(self, name: str, message: str = "") -> None:
        stage = self.stages.setdefault(name, StageState(name=name))
        if not stage.started_at:
            stage.started_at = datetime.now().isoformat()
        stage.status = StageStatus.FAILED
        stage.message = message
        stage.completed_at = datetime.now().isoformat()
