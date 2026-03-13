"""In-memory repository for build jobs."""

from __future__ import annotations

from typing import Dict, List, Optional

from ..domain import BuildJob


class BuildRepository:
    """Persistence boundary for build jobs."""

    def __init__(self) -> None:
        self._jobs: Dict[str, BuildJob] = {}

    def save(self, job: BuildJob) -> None:
        self._jobs[job.build_id] = job

    def get(self, build_id: str) -> Optional[BuildJob]:
        return self._jobs.get(build_id)

    def list_all(self) -> List[BuildJob]:
        return list(self._jobs.values())
