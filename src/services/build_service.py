"""Compatibility facade for build orchestration."""

from __future__ import annotations

from ..application import (
    BuildEnvironmentAssembler,
    BuildOrchestrator,
    BuildRepository,
    BuildStatusPresenter,
    BuildRequestValidator,
    ConfigDiagnostics,
    VersionResolver,
)
from ..domain import BuildRequestData
from ..infrastructure import CommandRunner, RepositoryWorkspaceManager, SetupExecutor


class BuildService:
    """Facade kept for existing route and webhook integrations."""

    def __init__(self) -> None:
        command_runner = CommandRunner()
        self.orchestrator = BuildOrchestrator(
            repository=BuildRepository(),
            validator=BuildRequestValidator(),
            version_resolver=VersionResolver(),
            command_runner=command_runner,
            config_diagnostics=ConfigDiagnostics(),
            environment_assembler=BuildEnvironmentAssembler(
                RepositoryWorkspaceManager(command_runner)
            ),
            setup_executor=SetupExecutor(command_runner),
            status_presenter=BuildStatusPresenter(),
        )

    def start_build_pipeline(
        self,
        flavor: str,
        platform: str,
        trigger_source: str = "manual",
        trigger_event_id: str = None,
        build_name: str = None,
        build_number: str = None,
        branch_name: str = None,
        flutter_sdk_version: str = None,
        gradle_version: str = None,
        cocoapods_version: str = None,
        fastlane_version: str = None,
    ) -> str:
        request = BuildRequestData(
            flavor=flavor,
            platform=platform,
            trigger_source=trigger_source,
            trigger_event_id=trigger_event_id,
            build_name=build_name,
            build_number=build_number,
            branch_name=branch_name,
            flutter_sdk_version=flutter_sdk_version,
            gradle_version=gradle_version,
            cocoapods_version=cocoapods_version,
            fastlane_version=fastlane_version,
        )
        return self.orchestrator.start_build(request)

    def get_build_status(self, build_id: str):
        return self.orchestrator.get_build_status(build_id)

    def list_builds(self):
        return self.orchestrator.list_builds()


build_service = BuildService()
