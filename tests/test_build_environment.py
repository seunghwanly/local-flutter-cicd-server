from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.application.build_environment import BuildEnvironmentAssembler
from src.application.version_resolver import ResolvedVersions
from src.domain import BuildJob, BuildRequestData
from src.infrastructure.repository_workspace import PreparedRepositoryResult


class StubRepositoryWorkspaceManager:
    def __init__(self) -> None:
        self.calls = []

    def prepare(self, **kwargs):
        self.calls.append(kwargs)
        repo_dir = Path(kwargs["repo_dir"])
        repo_dir.mkdir(parents=True, exist_ok=True)
        return PreparedRepositoryResult(
            flutter_version="3.24.0",
            precache_ran=False,
            repo_dir=str(repo_dir),
            workspace_lease=None,
        )


class BuildEnvironmentAssemblerTests(unittest.TestCase):
    def test_shorebird_build_uses_patch_lane_default_for_flavor(self) -> None:
        repo_manager = StubRepositoryWorkspaceManager()
        assembler = BuildEnvironmentAssembler(repo_manager)
        request = BuildRequestData(
            flavor="prod",
            platform="ios",
            trigger_source="shorebird_manual",
            build_name="2.2.1+689",
            build_number="3",
            branch_name="release/2.2.1-hotfix",
        )
        job = BuildJob.create("build-1", request, request.branch_name or "main", "queue-1")
        logs: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            isolated_env = {
                "env": {},
                "repo_dir": str(repo_dir),
                "deriveddata_cache_dir": str(Path(tmp) / "DerivedData"),
            }
            with patch.dict(
                os.environ,
                {
                    "REPO_URL": "git@github.com:org/app.git",
                },
                clear=False,
            ), patch(
                "src.application.build_environment.get_isolated_env",
                return_value=isolated_env,
            ), patch(
                "src.application.build_environment.get_build_workspace",
                return_value=Path(tmp) / "workspace",
            ):
                runtime = assembler.assemble(
                    job,
                    ResolvedVersions(
                        flutter_sdk_version="3.24.0",
                        gradle_version=None,
                        cocoapods_version=None,
                        fastlane_version=None,
                    ),
                    logs.append,
                )

        self.assertEqual("patch_prod", runtime.env["FASTLANE_LANE"])
        self.assertEqual("shorebird_manual", runtime.env["TRIGGER_SOURCE"])
        self.assertTrue(any("Shorebird patch config" in line for line in logs))
        self.assertEqual("release/2.2.1-hotfix", repo_manager.calls[0]["branch_name"])

    def test_shorebird_build_uses_flavor_specific_lane_override(self) -> None:
        repo_manager = StubRepositoryWorkspaceManager()
        assembler = BuildEnvironmentAssembler(repo_manager)
        request = BuildRequestData(
            flavor="stage",
            platform="ios",
            trigger_source="shorebird_manual",
            build_name="2.2.1+689",
            branch_name="release/2.2.1-hotfix",
        )
        job = BuildJob.create("build-override", request, request.branch_name or "main", "queue-override")

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "REPO_URL": "git@github.com:org/app.git",
                "SHOREBIRD_STAGE_FASTLANE_LANE": "custom_patch_stage",
            },
            clear=False,
        ), patch(
            "src.application.build_environment.get_isolated_env",
            return_value={
                "env": {},
                "repo_dir": str(Path(tmp) / "repo"),
                "deriveddata_cache_dir": str(Path(tmp) / "DerivedData"),
            },
        ), patch(
            "src.application.build_environment.get_build_workspace",
            return_value=Path(tmp) / "workspace",
        ):
            runtime = assembler.assemble(
                job,
                ResolvedVersions(
                    flutter_sdk_version="3.24.0",
                    gradle_version=None,
                    cocoapods_version=None,
                    fastlane_version=None,
                ),
                lambda _: None,
            )

        self.assertEqual("custom_patch_stage", runtime.env["FASTLANE_LANE"])

    def test_regular_build_uses_flavor_lane(self) -> None:
        repo_manager = StubRepositoryWorkspaceManager()
        assembler = BuildEnvironmentAssembler(repo_manager)
        request = BuildRequestData(
            flavor="stage",
            platform="ios",
            trigger_source="manual",
            branch_name="stage",
        )
        job = BuildJob.create("build-2", request, request.branch_name or "stage", "queue-2")

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"STAGE_FASTLANE_LANE": "deploy_stage", "REPO_URL": "git@github.com:org/app.git"},
            clear=False,
        ), patch(
            "src.application.build_environment.get_isolated_env",
            return_value={
                "env": {},
                "repo_dir": str(Path(tmp) / "repo"),
                "deriveddata_cache_dir": str(Path(tmp) / "DerivedData"),
            },
        ), patch(
            "src.application.build_environment.get_build_workspace",
            return_value=Path(tmp) / "workspace",
        ):
            runtime = assembler.assemble(
                job,
                ResolvedVersions(
                    flutter_sdk_version="3.24.0",
                    gradle_version=None,
                    cocoapods_version=None,
                    fastlane_version=None,
                ),
                lambda _: None,
            )

        self.assertEqual("deploy_stage", runtime.env["FASTLANE_LANE"])
        self.assertEqual("manual", runtime.env["TRIGGER_SOURCE"])
        self.assertNotIn("SHOREBIRD_RELEASE_VERSION", runtime.env)


if __name__ == "__main__":
    unittest.main()
