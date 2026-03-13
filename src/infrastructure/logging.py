"""Build log persistence."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from threading import Lock

from ..core.config import get_build_workspace

logger = logging.getLogger(__name__)


class BuildLogger:
    """Thread-safe log writer per build."""

    def __init__(self, build_id: str):
        self.build_id = build_id
        self.log_file_path = get_build_workspace(build_id) / "build.log"
        self._lock = Lock()
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with open(self.log_file_path, "w", encoding="utf-8") as file:
                file.write(f"=== Build Log for {build_id} ===\n")
                file.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                file.write("=" * 50 + "\n\n")

    def log(self, message: str) -> None:
        with self._lock:
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as file:
                    file.write(f"{message}\n")
                    file.flush()
            except OSError as exc:
                logger.error("Failed to write build log %s: %s", self.log_file_path, exc)

    def get_log_path(self) -> str:
        return str(self.log_file_path)
