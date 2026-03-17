"""UI routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    dashboard_path = Path(__file__).parent / "dashboard.html"
    try:
        return dashboard_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dashboard UI file not found") from exc

