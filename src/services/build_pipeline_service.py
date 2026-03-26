"""Compatibility facade for build orchestration."""

from __future__ import annotations

from ..internal.application import (
    BuildEnvironmentAssembler,
    BuildOrchestrator,
    BuildRepository,
    BuildStatusPresenter,
    BuildRequestValidator,
    ConfigDiagnostics,
    VersionResolver,
)
from ..internal.domain import BuildRequestData
from ..internal.infrastructure import CommandRunner, RepositoryWorkspaceManager, SetupExecutor
from ..models import BuildPipelineRequestDto


class BuildService:
    """Facade kept for existing route and webhook integrations."""

    def __init__(self, config_diagnostics: ConfigDiagnostics | None = None) -> None:
        command_runner = CommandRunner()
        diagnostics = config_diagnostics or ConfigDiagnostics()
        self.orchestrator = BuildOrchestrator(
            repository=BuildRepository(),
            validator=BuildRequestValidator(),
            version_resolver=VersionResolver(),
            command_runner=command_runner,
            config_diagnostics=diagnostics,
            environment_assembler=BuildEnvironmentAssembler(
                RepositoryWorkspaceManager(command_runner)
            ),
            setup_executor=SetupExecutor(command_runner),
            status_presenter=BuildStatusPresenter(),
        )

    def start_build_pipeline(self, request: BuildPipelineRequestDto) -> str:
        request = BuildRequestData(
            flavor=request.flavor,
            platform=request.platform,
            trigger_source=request.trigger_source,
            trigger_event_id=request.trigger_event_id,
            build_name=request.build_name,
            build_number=request.build_number,
            branch_name=request.branch_name,
        )
        return self.orchestrator.start_build(request)

    def get_build_status(self, build_id: str):
        return self.orchestrator.get_build_status(build_id)

    def list_builds(self):
        return self.orchestrator.list_builds()

    def cancel_build(self, build_id: str):
        return self.orchestrator.cancel_build(build_id)


build_service = BuildService()
