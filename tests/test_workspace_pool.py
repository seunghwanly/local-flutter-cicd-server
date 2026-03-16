from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.infrastructure.workspace_pool import WorkspacePoolManager


class WorkspacePoolManagerTests(unittest.TestCase):
    def test_acquire_allocates_additional_slot_when_existing_slot_is_busy(self) -> None:
        manager = WorkspacePoolManager(max_slots_per_key=2, wait_timeout=1)

        with tempfile.TemporaryDirectory() as tmp:
            shared_root = Path(tmp) / "shared"
            with patch("src.infrastructure.workspace_pool.get_shared_cache_dir", return_value=shared_root):
                lease1 = manager.acquire(
                    build_id="build-1",
                    repo_url="git@github.com:org/repo.git",
                    branch_name="main",
                    flutter_version="3.24.0",
                    platform="android",
                    log=lambda _: None,
                )
                lease2 = manager.acquire(
                    build_id="build-2",
                    repo_url="git@github.com:org/repo.git",
                    branch_name="main",
                    flutter_version="3.24.0",
                    platform="android",
                    log=lambda _: None,
                )

                self.assertEqual("slot-1", lease1.slot_id)
                self.assertEqual("slot-2", lease2.slot_id)
                self.assertNotEqual(lease1.repo_dir, lease2.repo_dir)

                lease1.release()
                lease2.release()


if __name__ == "__main__":
    unittest.main()
