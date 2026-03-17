"""FastAPI dependencies for app-level services."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from ..internal.application import ConfigDiagnostics
from ..services.build_pipeline_service import BuildService
from ..services.trigger_service import GitHubActionService
from .settings import AppSettings


@dataclass(frozen=True)
class ServiceContainer:
    settings: AppSettings
    diagnostics: ConfigDiagnostics
    build_service: BuildService
    github_action_service: GitHubActionService


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container


def get_settings(container: ServiceContainer = Depends(get_container)) -> AppSettings:
    return container.settings


def get_diagnostics(container: ServiceContainer = Depends(get_container)) -> ConfigDiagnostics:
    return container.diagnostics


def get_build_service(container: ServiceContainer = Depends(get_container)) -> BuildService:
    return container.build_service


def get_github_action_service(
    container: ServiceContainer = Depends(get_container),
) -> GitHubActionService:
    return container.github_action_service
