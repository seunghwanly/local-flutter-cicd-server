from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.infrastructure.command_runner import CompletedCommand
from src.infrastructure.repository_workspace import RepositoryWorkspaceManager


class CapturingRepositoryWorkspaceManager(RepositoryWorkspaceManager):
    def __init__(self) -> None:
        super().__init__(command_runner=None)  # type: ignore[arg-type]
        self.calls: list[tuple[str, str]] = []
        self.previous_version: str | None = None
        self.written_version: str | None = None

    def _sync_repository(self, **kwargs) -> None:  # type: ignore[override]
        self.calls.append(("sync", kwargs["branch_name"]))

    def _run_fvm_use(self, build_id, repo_path, env, flutter_version, log, should_cancel=None) -> None:
        self.calls.append(("fvm_use", flutter_version))

    def _run_flutter_precache(self, build_id, repo_path, env, flutter_version, platform, log, should_cancel=None) -> None:
        self.calls.append(("precache", f"{flutter_version}:{platform}"))

    def _read_previous_flutter_version(self, repo_url: str, branch_name: str) -> str | None:
        return self.previous_version

    def _write_previous_flutter_version(
        self,
        repo_url: str,
        branch_name: str,
        flutter_version: str,
    ) -> None:
        self.written_version = flutter_version
        self.calls.append(("write_version", flutter_version))


class FakeCommandRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run_checked(self, command, *, env, cwd, should_stop=None):
        self.calls.append(tuple(command))
        return CompletedCommand(args=list(command), returncode=0, stdout="")

    def run(self, command, *, env, cwd, check=True, should_stop=None):
        self.calls.append(tuple(command))
        return CompletedCommand(args=list(command), returncode=0, stdout="")


class RepositoryWorkspaceManagerTests(unittest.TestCase):
    def test_prepare_runs_precache_when_flutter_version_changes(self) -> None:
        manager = CapturingRepositoryWorkspaceManager()
        manager.previous_version = "3.22.0"
        logs: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            (repo_dir / ".fvmrc").write_text('{"flutter":"3.24.0"}', encoding="utf-8")

            prepared = manager.prepare(
                build_id="build-1",
                repo_url="git@github.com:org/repo.git",
                branch_name="develop",
                repo_dir=str(repo_dir),
                env={},
                requested_flutter_version=None,
                platform="ios",
                log=logs.append,
            )

        self.assertEqual("3.24.0", prepared.flutter_version)
        self.assertTrue(prepared.precache_ran)
        self.assertIn(("fvm_use", "3.24.0"), manager.calls)
        self.assertIn(("precache", "3.24.0:ios"), manager.calls)
        self.assertEqual("3.24.0", manager.written_version)

    def test_prepare_skips_ios_precache_for_android_only_build(self) -> None:
        manager = CapturingRepositoryWorkspaceManager()
        manager.previous_version = "3.22.0"

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            (repo_dir / ".fvmrc").write_text('{"flutter":"3.24.0"}', encoding="utf-8")

            prepared = manager.prepare(
                build_id="build-android",
                repo_url="git@github.com:org/repo.git",
                branch_name="develop",
                repo_dir=str(repo_dir),
                env={},
                requested_flutter_version=None,
                platform="android",
                log=lambda _: None,
            )

        self.assertEqual("3.24.0", prepared.flutter_version)
        self.assertFalse(prepared.precache_ran)
        self.assertNotIn(("precache", "3.24.0:android"), manager.calls)

    def test_sync_repository_uses_shallow_clone_for_fresh_workspace(self) -> None:
        runner = FakeCommandRunner()
        manager = RepositoryWorkspaceManager(runner)

        with tempfile.TemporaryDirectory() as tmp:
            repo_path = Path(tmp) / "repo"
            repo_path.mkdir()

            manager._sync_repository(
                build_id="build-1",
                repo_url="git@github.com:org/repo.git",
                branch_name="main",
                repo_path=repo_path,
                env={},
                log=lambda _: None,
            )

        self.assertEqual(
            [
                (
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--single-branch",
                    "--branch",
                    "main",
                    "git@github.com:org/repo.git",
                    str(repo_path),
                )
            ],
            runner.calls,
        )

    def test_run_fvm_use_uses_non_interactive_flags(self) -> None:
        runner = FakeCommandRunner()
        manager = RepositoryWorkspaceManager(runner)

        with tempfile.TemporaryDirectory() as tmp:
            repo_path = Path(tmp)
            manager._run_fvm_use(
                build_id="build-1",
                repo_path=repo_path,
                env={},
                flutter_version="3.41.2",
                log=lambda _: None,
            )

        self.assertEqual(
            [
                (
                    "fvm",
                    "use",
                    "3.41.2",
                    "--force",
                    "--skip-pub-get",
                    "--skip-setup",
                )
            ],
            runner.calls,
        )

    def test_ensure_melos_sdk_path_adds_sdk_path_when_missing(self) -> None:
        manager = RepositoryWorkspaceManager(FakeCommandRunner())
        logs: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            repo_path = Path(tmp)
            melos_path = repo_path / "melos.yaml"
            melos_path.write_text("name: workspace\npackages:\n  - packages/**\n", encoding="utf-8")

            manager._ensure_melos_sdk_path("build-1", repo_path, logs.append)

            self.assertTrue(melos_path.read_text(encoding="utf-8").startswith("sdkPath: .fvm/flutter_sdk\n"))

        self.assertTrue(any("Added sdkPath to melos.yaml" in line for line in logs))

    def test_resolve_flutter_version_prefers_tool_versions_then_env_fallback(self) -> None:
        manager = CapturingRepositoryWorkspaceManager()

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp)
            (repo_dir / ".tool-versions").write_text("flutter 3.27.1\n", encoding="utf-8")
            self.assertEqual("3.27.1", manager._resolve_flutter_version(repo_dir, None))

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp)
            with patch.dict("os.environ", {"FLUTTER_VERSION": "3.19.0"}, clear=False):
                self.assertEqual("3.19.0", manager._resolve_flutter_version(repo_dir, None))


if __name__ == "__main__":
    unittest.main()
