from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.internal.infrastructure.workspace_pool import WorkspacePoolManager


class WorkspacePoolManagerTests(unittest.TestCase):
    def test_acquire_allocates_additional_slot_when_existing_slot_is_busy(self) -> None:
        manager = WorkspacePoolManager(max_slots_per_key=2, wait_timeout=1)

        with tempfile.TemporaryDirectory() as tmp:
            shared_root = Path(tmp) / "shared"
            with patch("src.internal.infrastructure.workspace_pool.get_shared_cache_dir", return_value=shared_root):
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

    def test_all_platform_slot_key_differs_from_android(self) -> None:
        manager = WorkspacePoolManager(max_slots_per_key=2, wait_timeout=1)
        key_all = manager._slot_key(
            repo_url="git@github.com:org/repo.git",
            branch_name="main",
            flutter_version="3.24.0",
            platform="all",
            cocoapods_version=None,
        )
        key_android = manager._slot_key(
            repo_url="git@github.com:org/repo.git",
            branch_name="main",
            flutter_version="3.24.0",
            platform="android",
            cocoapods_version=None,
        )
        self.assertNotEqual(key_all, key_android)
        self.assertIn("__all", key_all)
        self.assertIn("__android", key_android)

    def test_ios_and_all_include_cocoapods_suffix(self) -> None:
        manager = WorkspacePoolManager(max_slots_per_key=2, wait_timeout=1)
        for platform in ("ios", "all"):
            key = manager._slot_key(
                repo_url="git@github.com:org/repo.git",
                branch_name="main",
                flutter_version="3.24.0",
                platform=platform,
                cocoapods_version="1.16.2",
            )
            self.assertIn("1.16.2", key, f"platform={platform} should include cocoapods version")

        key_android = manager._slot_key(
            repo_url="git@github.com:org/repo.git",
            branch_name="main",
            flutter_version="3.24.0",
            platform="android",
            cocoapods_version="1.16.2",
        )
        self.assertNotIn("1.16.2", key_android)


if __name__ == "__main__":
    unittest.main()
