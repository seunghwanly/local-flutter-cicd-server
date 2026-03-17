"""Dataclass DTOs for service-layer interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BuildPipelineRequestDto:
    """Stable service interface for starting a build pipeline."""

    flavor: str
    platform: str
    trigger_source: str = "manual"
    trigger_event_id: Optional[str] = None
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    branch_name: Optional[str] = None

