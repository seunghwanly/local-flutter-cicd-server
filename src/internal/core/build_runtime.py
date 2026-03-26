"""Shared runtime context for an in-flight build."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class BuildRuntimeContext:
    """Resolved runtime metadata used across setup and build execution."""

    env: Dict[str, str]
    repo_dir: str
    workspace: str
    trigger_source: str = "manual"
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    slot_key: Optional[str] = None
    slot_id: Optional[str] = None
    workspace_lease: Optional[Any] = None
    cleanup_callbacks: list[Callable[[], None]] = field(default_factory=list)

    def is_shorebird_patch(self) -> bool:
        return self.trigger_source.startswith("shorebird")

    def build_env(self) -> Dict[str, str]:
        command_env = dict(self.env)
        if self.build_name:
            command_env["BUILD_NAME"] = self.build_name
        if self.build_number:
            command_env["BUILD_NUMBER"] = self.build_number
        return command_env
