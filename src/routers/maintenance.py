"""Maintenance routes."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends

from ..core.dependencies import get_settings
from ..core.settings import AppSettings
from ..models import CleanupResponse
from ..utils.cleanup import manual_cleanup


router = APIRouter(tags=["Maintenance"])


@router.post("/cleanup", response_model=CleanupResponse)
async def trigger_manual_cleanup(settings: AppSettings = Depends(get_settings)) -> CleanupResponse:
    try:
        threading.Thread(
            target=manual_cleanup,
            args=(settings.cache_cleanup_days,),
            daemon=True,
        ).start()
        return {
            "status": "ok",
            "message": f"Manual cleanup started (removing builds older than {settings.cache_cleanup_days} days)",
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to start cleanup: {exc}",
        }

