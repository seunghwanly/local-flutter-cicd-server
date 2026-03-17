"""Health and diagnostics routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.dependencies import get_diagnostics
from ..models import DiagnosticsResponse, RootResponse


router = APIRouter(tags=["Health Check"])


@router.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    return {"message": "👋 Flutter CI/CD Container is running!"}


@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def runtime_diagnostics(diagnostics=Depends(get_diagnostics)) -> DiagnosticsResponse:
    results = diagnostics.get_runtime_diagnostics()
    return {
        "diagnostics": {
            name: {
                "feature": result.feature,
                "ready": result.ready,
                "missing": result.missing,
                "details": result.details,
            }
            for name, result in results.items()
        }
    }

