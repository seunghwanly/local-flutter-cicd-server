"""Reusable workspace slot allocation for parallel builds."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock, Timeout

from ..core.config import get_shared_cache_dir

DEFAULT_SLOT_WAIT_TIMEOUT = 3600
DEFAULT_MAX_SLOTS_PER_KEY = 2
SLOT_LOCK_TIMEOUT = 0


def _sanitize(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return normalized[:80] or "default"


@dataclass
class WorkspaceSlotLease:
    """Exclusive lease for a reusable repository workspace slot."""

    slot_key: str
    slot_dir: Path
    repo_dir: Path
    slot_id: str
    _lock: FileLock

    def release(self) -> None:
        metadata = self.slot_dir / "lease.json"
        if metadata.exists():
            metadata.unlink(missing_ok=True)
        if self._lock.is_locked:
            self._lock.release()


class WorkspacePoolManager:
    """Allocate reusable workspace slots keyed by repo/branch/runtime inputs."""

    def __init__(self, *, max_slots_per_key: int = DEFAULT_MAX_SLOTS_PER_KEY, wait_timeout: int = DEFAULT_SLOT_WAIT_TIMEOUT) -> None:
        self.max_slots_per_key = max_slots_per_key
        self.wait_timeout = wait_timeout

    def acquire(
        self,
        *,
        build_id: str,
        repo_url: str,
        branch_name: str,
        flutter_version: str | None,
        platform: str,
        cocoapods_version: str | None = None,
        log,
    ) -> WorkspaceSlotLease:
        slot_key = self._slot_key(
            repo_url=repo_url,
            branch_name=branch_name,
            flutter_version=flutter_version,
            platform=platform,
            cocoapods_version=cocoapods_version,
        )
        slot_root = self._slot_root(slot_key)
        slot_root.mkdir(parents=True, exist_ok=True)

        deadline = time.time() + self.wait_timeout
        while True:
            existing = self._existing_slots(slot_root)
            for slot_dir in existing:
                lease = self._try_acquire_slot(slot_key, slot_dir, build_id, log)
                if lease is not None:
                    return lease

            if len(existing) < self.max_slots_per_key:
                slot_dir = slot_root / f"slot-{len(existing) + 1}"
                slot_dir.mkdir(parents=True, exist_ok=True)
                lease = self._try_acquire_slot(slot_key, slot_dir, build_id, log)
                if lease is not None:
                    return lease

            if time.time() >= deadline:
                raise Timeout(f"Timed out waiting for workspace slot: {slot_key}")
            time.sleep(1.0)

    def _existing_slots(self, slot_root: Path) -> list[Path]:
        return sorted(
            (path for path in slot_root.iterdir() if path.is_dir() and path.name.startswith("slot-")),
            key=lambda path: path.name,
        )

    def _try_acquire_slot(self, slot_key: str, slot_dir: Path, build_id: str, log) -> WorkspaceSlotLease | None:
        lock = FileLock(str(slot_dir / ".lease.lock"), timeout=SLOT_LOCK_TIMEOUT)
        try:
            lock.acquire()
        except Timeout:
            return None

        repo_dir = slot_dir / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        metadata = slot_dir / "lease.json"
        metadata.write_text(
            json.dumps(
                {
                    "build_id": build_id,
                    "slot_key": slot_key,
                    "slot_id": slot_dir.name,
                    "leased_at": time.time(),
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        log(f"[{build_id}] 🧩 Workspace slot acquired: {slot_key}/{slot_dir.name}")
        return WorkspaceSlotLease(
            slot_key=slot_key,
            slot_dir=slot_dir,
            repo_dir=repo_dir,
            slot_id=slot_dir.name,
            _lock=lock,
        )

    def _slot_root(self, slot_key: str) -> Path:
        return get_shared_cache_dir() / "slots" / slot_key

    def _slot_key(
        self,
        *,
        repo_url: str,
        branch_name: str,
        flutter_version: str | None,
        platform: str,
        cocoapods_version: str | None,
    ) -> str:
        repo_hash = hashlib.sha256(repo_url.encode("utf-8")).hexdigest()[:10]
        normalized_repo = _sanitize(Path(repo_url).stem or "repo")
        normalized_branch = _sanitize(branch_name or "unknown")
        normalized_flutter = _sanitize(flutter_version or "auto")
        normalized_platform = _sanitize(platform or "android")
        pieces = [normalized_repo, repo_hash, normalized_branch, normalized_flutter, normalized_platform]
        if platform in {"ios", "all"} and cocoapods_version:
            pieces.append(_sanitize(cocoapods_version))
        return "__".join(pieces)
