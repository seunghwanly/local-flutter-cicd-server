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
    CANCELED = "canceled"


class StageStatus(str, Enum):
    """Per-stage lifecycle for pipeline visibility."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class BuildRequestData:
    """Validated input for a build pipeline."""

    flavor: str
    platform: str
    trigger_source: str = "manual"
    trigger_event_id: Optional[str] = None
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    branch_name: Optional[str] = None
    flutter_sdk_version: Optional[str] = None
    gradle_version: Optional[str] = None
    cocoapods_version: Optional[str] = None
    fastlane_version: Optional[str] = None


@dataclass
class BuildLogEntry:
    """Structured log entry with optional stage attribution."""

    message: str
    timestamp: str
    stages: List[str] = field(default_factory=list)


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
    trigger_source: str = "manual"
    trigger_event_id: Optional[str] = None
    flutter_sdk_version: Optional[str] = None
    gradle_version: Optional[str] = None
    cocoapods_version: Optional[str] = None
    fastlane_version: Optional[str] = None
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    resolved_flutter_sdk_version: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancel_requested_at: Optional[str] = None
    canceled_at: Optional[str] = None
    status: BuildStatus = BuildStatus.PENDING
    logs: List[str] = field(default_factory=list)
    log_entries: List[BuildLogEntry] = field(default_factory=list)
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
            if request.trigger_source.startswith("shorebird"):
                stage_names.append("android_preflight")
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
            trigger_source=request.trigger_source,
            trigger_event_id=request.trigger_event_id,
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

    def mark_stage_canceled(self, name: str, message: str = "") -> None:
        stage = self.stages.setdefault(name, StageState(name=name))
        if not stage.started_at:
            stage.started_at = datetime.now().isoformat()
        stage.status = StageStatus.CANCELED
        stage.message = message
        stage.completed_at = datetime.now().isoformat()

    def mark_canceled(self, reason: str) -> None:
        timestamp = datetime.now().isoformat()
        self.status = BuildStatus.CANCELED
        self.cancel_reason = reason
        self.cancel_requested_at = self.cancel_requested_at or timestamp
        self.canceled_at = timestamp
        for name, stage in self.stages.items():
            if stage.status in {StageStatus.PENDING, StageStatus.RUNNING}:
                self.mark_stage_canceled(name, reason)

    def to_dict(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "build_id": self.build_id,
                "started_at": self.started_at,
                "flavor": self.flavor,
                "platform": self.platform,
                "branch_name": self.branch_name,
                "queue_key": self.queue_key,
                "trigger_source": self.trigger_source,
                "trigger_event_id": self.trigger_event_id,
                "flutter_sdk_version": self.flutter_sdk_version,
                "gradle_version": self.gradle_version,
                "cocoapods_version": self.cocoapods_version,
                "fastlane_version": self.fastlane_version,
                "build_name": self.build_name,
                "build_number": self.build_number,
                "resolved_flutter_sdk_version": self.resolved_flutter_sdk_version,
                "cancel_reason": self.cancel_reason,
                "cancel_requested_at": self.cancel_requested_at,
                "canceled_at": self.canceled_at,
                "status": self.status.value,
                "logs": list(self.logs),
                "log_entries": [
                    {
                        "message": entry.message,
                        "timestamp": entry.timestamp,
                        "stages": list(entry.stages),
                    }
                    for entry in self.log_entries
                ],
                "progress": {
                    k: {
                        "current_step": v.current_step,
                        "percentage": v.percentage,
                        "current_message": v.current_message,
                        "steps_completed": list(v.steps_completed),
                    }
                    for k, v in self.progress.items()
                },
                "stages": {
                    k: {
                        "name": v.name,
                        "status": v.status.value,
                        "message": v.message,
                        "started_at": v.started_at,
                        "completed_at": v.completed_at,
                    }
                    for k, v in self.stages.items()
                },
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BuildJob":
        job = cls(
            build_id=data["build_id"],
            started_at=data["started_at"],
            flavor=data["flavor"],
            platform=data["platform"],
            branch_name=data["branch_name"],
            queue_key=data["queue_key"],
            trigger_source=data.get("trigger_source", "manual"),
            trigger_event_id=data.get("trigger_event_id"),
            flutter_sdk_version=data.get("flutter_sdk_version"),
            gradle_version=data.get("gradle_version"),
            cocoapods_version=data.get("cocoapods_version"),
            fastlane_version=data.get("fastlane_version"),
            build_name=data.get("build_name"),
            build_number=data.get("build_number"),
        )
        job.resolved_flutter_sdk_version = data.get("resolved_flutter_sdk_version")
        job.cancel_reason = data.get("cancel_reason")
        job.cancel_requested_at = data.get("cancel_requested_at")
        job.canceled_at = data.get("canceled_at")
        job.status = BuildStatus(data.get("status", "pending"))
        job.logs = data.get("logs", [])
        job.log_entries = [
            BuildLogEntry(
                message=entry.get("message", ""),
                timestamp=entry.get("timestamp", ""),
                stages=entry.get("stages", []),
            )
            for entry in data.get("log_entries", [])
        ]

        if "progress" in data:
            for k, p_data in data["progress"].items():
                job.progress[k] = BuildProgress(
                    current_step=p_data.get("current_step", ""),
                    percentage=p_data.get("percentage", 0),
                    current_message=p_data.get("current_message", ""),
                    steps_completed=p_data.get("steps_completed", []),
                )
        
        if "stages" in data:
            for k, s_data in data["stages"].items():
                job.stages[k] = StageState(
                    name=s_data.get("name", k),
                    status=StageStatus(s_data.get("status", "pending")),
                    message=s_data.get("message", ""),
                    started_at=s_data.get("started_at"),
                    completed_at=s_data.get("completed_at"),
                )
        return job
