"""Facade for build setup and toolchain preparation."""

from __future__ import annotations

from ..core import BuildRuntimeContext
from .command_runner import CommandRunner
from .platform_toolchain import PlatformToolchainPreparer
from .pub_setup_executor import PubSetupExecutor


class SetupExecutor:
    """Compatibility facade for setup collaborators."""

    def __init__(self, command_runner: CommandRunner) -> None:
        self.pub_setup = PubSetupExecutor(command_runner)
        self.platform_toolchain = PlatformToolchainPreparer(command_runner)

    def run_setup(
        self,
        *,
        build_id: str,
        context: BuildRuntimeContext,
        log,
        should_cancel=None,
    ) -> None:
        self.pub_setup.run_setup(
            build_id=build_id,
            context=context,
            log=log,
            should_cancel=should_cancel,
        )

    def prepare_platform_preflight(
        self,
        *,
        build_id: str,
        platform: str,
        context: BuildRuntimeContext,
        log,
        should_cancel=None,
    ) -> None:
        self.platform_toolchain.preflight(
            build_id=build_id,
            platform=platform,
            context=context,
            log=log,
            should_cancel=should_cancel,
        )

    def prepare_platform_toolchain(
        self,
        *,
        build_id: str,
        platform: str,
        context: BuildRuntimeContext,
        log,
        should_cancel=None,
    ) -> None:
        self.platform_toolchain.prepare(
            build_id=build_id,
            platform=platform,
            context=context,
            log=log,
            should_cancel=should_cancel,
        )
