"""FastAPI application factory using routers, dependencies, and lifespan."""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from ..internal.application import ConfigDiagnostics
from ..services.build_pipeline_service import BuildService
from ..services.trigger_service import GitHubActionService
from ..utils.cleanup import start_cleanup_scheduler
from .dependencies import ServiceContainer
from .settings import AppSettings, bootstrap_environment, get_settings


logger = logging.getLogger(__name__)


def _log_startup_details(settings: AppSettings, diagnostics: ConfigDiagnostics) -> None:
    logger.info("Server startup diagnostics")
    ssh_auth_sock_value = os.environ.get("SSH_AUTH_SOCK")
    ssh_auth_sock = Path(ssh_auth_sock_value) if ssh_auth_sock_value else None

    if ssh_auth_sock:
        logger.info("SSH_AUTH_SOCK: %s", ssh_auth_sock)
        logger.info("SSH agent socket exists: %s", ssh_auth_sock.exists())
    else:
        logger.warning("SSH_AUTH_SOCK not set")

    ssh_key = Path.home() / ".ssh" / "id_rsa"
    if ssh_key.exists():
        logger.info("SSH key exists: %s", ssh_key)
    else:
        logger.warning("SSH key not found: %s", ssh_key)

    _validate_keychain_at_startup(diagnostics)

    logger.info("Cleanup scheduler started (keeping %s days)", settings.cache_cleanup_days)
    logger.info("Server ready at http://localhost:8000")


def _validate_keychain_at_startup(diagnostics: ConfigDiagnostics) -> None:
    result = diagnostics.validate_keychain_on_startup()
    for key, value in result.details.items():
        logger.info("Keychain %s: %s", key, value)

    if result.ready:
        logger.info("✅ Keychain ready for iOS codesigning")
    else:
        for issue in result.missing:
            logger.error("❌ Keychain issue: %s", issue)
        logger.error(
            "iOS builds will be rejected until keychain is fixed. "
            "Fix the issue and restart the server."
        )


def build_container(settings: AppSettings) -> ServiceContainer:
    diagnostics = ConfigDiagnostics()
    build_service = BuildService(config_diagnostics=diagnostics)
    return ServiceContainer(
        settings=settings,
        diagnostics=diagnostics,
        build_service=build_service,
        github_action_service=GitHubActionService(
            build_service=build_service,
            webhook_secret=settings.github_webhook_secret,
        ),
    )


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = bootstrap_environment(settings or get_settings())
    container = build_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container
        cleanup_thread = threading.Thread(
            target=start_cleanup_scheduler,
            args=(resolved_settings.cache_cleanup_days,),
            daemon=True,
        )
        cleanup_thread.start()
        app.state.cleanup_thread = cleanup_thread
        _log_startup_details(resolved_settings, container.diagnostics)
        yield

    app = FastAPI(
        title=resolved_settings.app_name,
        description=resolved_settings.app_description,
        version=resolved_settings.app_version,
        docs_url=resolved_settings.docs_url,
        redoc_url=resolved_settings.redoc_url,
        lifespan=lifespan,
    )

    from ..routers import actions_router, builds_router, health_router, maintenance_router, ui_router

    app.include_router(health_router)
    app.include_router(ui_router)
    app.include_router(builds_router)
    app.include_router(actions_router)
    app.include_router(maintenance_router)
    return app


app = create_app()
