"""Application settings powered by pydantic-settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppSettings(BaseSettings):
    """Validated application settings loaded from environment and .env files."""

    app_name: str = "Flutter CI/CD Server API"
    app_description: str = "Flutter 애플리케이션의 CI/CD 파이프라인을 관리하는 서버 API"
    app_version: str = "1.0.0"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"

    repo_url: Optional[str] = Field(default=None, alias="REPO_URL")
    github_webhook_secret: Optional[str] = Field(default=None, alias="GITHUB_WEBHOOK_SECRET")
    webhook_prod_tag_pattern: str = Field(default=r"^\d+\.\d+\.\d+$", alias="WEBHOOK_PROD_TAG_PATTERN")

    shorebird_patch_flavor: str = Field(default="prod", alias="SHOREBIRD_PATCH_FLAVOR")
    shorebird_patch_platform: str = Field(default="all", alias="SHOREBIRD_PATCH_PLATFORM")
    shorebird_patch_branch_name: Optional[str] = Field(default=None, alias="SHOREBIRD_PATCH_BRANCH_NAME")
    prod_branch_name: str = Field(default="main", alias="PROD_BRANCH_NAME")

    cache_cleanup_days: int = Field(default=7, alias="CACHE_CLEANUP_DAYS")
    workspace_root: Path = Field(
        default_factory=lambda: Path.home() / "ci-cd-workspace",
        alias="WORKSPACE_ROOT",
    )

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "src" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


def bootstrap_environment(settings: AppSettings | None = None) -> AppSettings:
    """Load settings once and mirror them into os.environ for legacy internals."""

    resolved = settings or get_settings()
    for field_name, field_info in resolved.__class__.model_fields.items():
        env_name = field_info.alias or field_name.upper()
        value = getattr(resolved, field_name)
        if value is None:
            continue
        os.environ.setdefault(env_name, str(value))
    return resolved

