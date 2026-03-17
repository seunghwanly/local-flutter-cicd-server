from __future__ import annotations

import unittest

from src.internal.application.build_orchestrator import BuildOrchestrator
from src.core import BuildRuntimeContext
from src.internal.domain import BuildJob, BuildRequestData


class StubRepository:
    def __init__(self) -> None:
        self.jobs: dict[str, BuildJob] = {}

    def save(self, job: BuildJob) -> None:
        self.jobs[job.build_id] = job

    def get(self, build_id: str):
        return self.jobs.get(build_id)

    def list_all(self):
        return list(self.jobs.values())


class StubSetupExecutor:
    def run_setup(self, **kwargs) -> None:
        return None

    def prepare_platform_preflight(self, **kwargs) -> None:
        return None

    def prepare_platform_toolchain(self, *, context, **kwargs) -> None:
        context.env["RBENV_VERSION"] = "3.2.0"
        context.env["GEM_HOME"] = "/tmp/gems/ruby-3.2.0"
        context.env["BUNDLE_PATH"] = "/tmp/gems/ruby-3.2.0/bundle"


class FakeProcess:
    def __init__(self) -> None:
        self.returncode = 0


class CapturingCommandRunner:
    def __init__(self) -> None:
        self.started_envs: list[dict[str, str]] = []

    def start(self, command, *, env, cwd, line_buffered=False):
        self.started_envs.append(dict(env))
        return FakeProcess()

    def wait(self, process) -> int:
        return process.returncode

    def iter_lines(self, process):
        return iter(())

    def terminate(self, process, *, kill_after_seconds: float = 5.0) -> None:
        return None


class BuildOrchestratorTests(unittest.TestCase):
    def test_run_build_scripts_uses_toolchain_updated_runtime_env(self) -> None:
        repository = StubRepository()
        command_runner = CapturingCommandRunner()
        orchestrator = BuildOrchestrator(
            repository=repository,
            validator=None,
            version_resolver=None,
            command_runner=command_runner,
            config_diagnostics=None,
            environment_assembler=None,
            setup_executor=StubSetupExecutor(),
            status_presenter=None,
        )

        request = BuildRequestData(
            flavor="dev",
            platform="ios",
            trigger_source="shorebird_manual",
            build_name="2.2.1",
            build_number="693",
            branch_name="release/2.2.1",
        )
        job = BuildJob.create("build-ios", request, request.branch_name or "develop", "queue-1")
        runtime = BuildRuntimeContext(
            env={},
            repo_dir="/tmp/repo",
            workspace="/tmp/workspace",
            trigger_source=request.trigger_source,
            build_name=request.build_name,
            build_number=request.build_number,
        )

        success = orchestrator._run_build_scripts(job, runtime)

        self.assertTrue(success)
        self.assertEqual(1, len(command_runner.started_envs))
        started_env = command_runner.started_envs[0]
        self.assertEqual("3.2.0", started_env["RBENV_VERSION"])
        self.assertEqual("/tmp/gems/ruby-3.2.0", started_env["GEM_HOME"])
        self.assertEqual("/tmp/gems/ruby-3.2.0/bundle", started_env["BUNDLE_PATH"])
        self.assertEqual("2.2.1", started_env["BUILD_NAME"])
        self.assertEqual("693", started_env["BUILD_NUMBER"])


if __name__ == "__main__":
    unittest.main()
