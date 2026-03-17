"""Build-related routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import ValidationError

from ..core.dependencies import get_build_service, get_settings
from ..core.settings import AppSettings
from ..models import (
    BuildPipelineRequestDto,
    BuildRequest,
    BuildStatusResponse,
    BuildsResponse,
    CancelBuildResponse,
    ManualBuildResponse,
)
from ..services.build_pipeline_service import BuildService


router = APIRouter(tags=["Build Status"])


def _normalize_shorebird_manual_flavor(value: str) -> str:
    aliases = {
        "dev": "dev",
        "development": "dev",
        "stg": "stage",
        "stage": "stage",
        "prd": "prod",
        "prod": "prod",
        "production": "prod",
    }
    normalized = aliases.get(value.strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported flavor: {value}")
    return normalized


@router.get("/build/{build_id}", response_model=BuildStatusResponse)
async def get_build_status(
    build_id: str,
    build_service: BuildService = Depends(get_build_service),
) -> BuildStatusResponse:
    build_status = build_service.get_build_status(build_id)
    if not build_status:
        raise HTTPException(status_code=404, detail="Build not found")
    return build_status


@router.get("/builds", response_model=BuildsResponse)
async def list_builds(build_service: BuildService = Depends(get_build_service)) -> BuildsResponse:
    return {"builds": build_service.list_builds()}


@router.post("/build/{build_id}/cancel", response_model=CancelBuildResponse)
async def cancel_build(
    build_id: str,
    build_service: BuildService = Depends(get_build_service),
) -> CancelBuildResponse:
    build_status = build_service.cancel_build(build_id)
    if not build_status:
        raise HTTPException(status_code=404, detail="Build not found")

    status = build_status.get("status")
    if status in {"completed", "failed"}:
        raise HTTPException(status_code=409, detail=f"Build already finished with status '{status}'")

    return {
        "status": "ok",
        "build_id": build_id,
        "message": "Build cancellation requested",
    }


@router.post("/build/shorebird", response_model=ManualBuildResponse, tags=["Manual Build"])
async def manual_shorebird_build(
    flavor: str = Form("", description="flavor 설정. 비우면 SHOREBIRD_PATCH_FLAVOR 또는 prod 사용. dev, stg, stage, prd, prod 지원"),
    platform: str = Form("", description="platform 설정. 비우면 SHOREBIRD_PATCH_PLATFORM 또는 all 사용. all, ios, android 지원"),
    build_name: Optional[str] = Form("", description="shorebird patch 대상 release version. 예: 2.2.1+689"),
    build_number: Optional[str] = Form("", description="shorebird patch number 또는 내부 기록용 값. 현재 fastlane patch 인자에는 직접 사용하지 않음"),
    branch_name: Optional[str] = Form("", description="branch name 설정. 비우면 SHOREBIRD_PATCH_BRANCH_NAME 또는 main 사용"),
    build_service: BuildService = Depends(get_build_service),
    settings: AppSettings = Depends(get_settings),
) -> ManualBuildResponse:
    raw_flavor = (flavor or settings.shorebird_patch_flavor or "prod").strip()
    resolved_platform = (platform or settings.shorebird_patch_platform or "all").strip()
    resolved_branch = (
        branch_name
        or settings.shorebird_patch_branch_name
        or settings.prod_branch_name
        or "main"
    ).strip()

    try:
        resolved_flavor = _normalize_shorebird_manual_flavor(raw_flavor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        request_model = BuildRequest(
            flavor=resolved_flavor,
            platform=resolved_platform,
            build_name=build_name,
            build_number=build_number,
            branch_name=resolved_branch,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    try:
        build_id = build_service.start_build_pipeline(
            BuildPipelineRequestDto(
                flavor=request_model.flavor,
                platform=request_model.platform,
                trigger_source="shorebird_manual",
                build_name=request_model.build_name,
                build_number=request_model.build_number,
                branch_name=request_model.branch_name,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "manual trigger ok", "build_id": build_id}


@router.post("/build", response_model=ManualBuildResponse, tags=["Manual Build"])
async def manual_build(
    flavor: str = Form("dev", description="flavor 설정: dev, stage, prod"),
    platform: str = Form("all", description="platform 설정: all, android, ios"),
    build_name: Optional[str] = Form("", description="build name 설정"),
    build_number: Optional[str] = Form("", description="build number 설정"),
    branch_name: Optional[str] = Form("", description="branch name 설정"),
    build_service: BuildService = Depends(get_build_service),
) -> ManualBuildResponse:
    try:
        request_model = BuildRequest(
            flavor=flavor,
            platform=platform,
            build_name=build_name,
            build_number=build_number,
            branch_name=branch_name,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    try:
        build_id = build_service.start_build_pipeline(
            BuildPipelineRequestDto(
                flavor=request_model.flavor,
                platform=request_model.platform,
                trigger_source="manual",
                build_name=request_model.build_name,
                build_number=request_model.build_number,
                branch_name=request_model.branch_name,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "manual trigger ok", "build_id": build_id}

