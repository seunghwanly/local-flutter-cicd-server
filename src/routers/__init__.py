"""Application routers."""

from .actions import router as actions_router
from .builds import router as builds_router
from .health import router as health_router
from .maintenance import router as maintenance_router
from .ui import router as ui_router

__all__ = [
    "actions_router",
    "builds_router",
    "health_router",
    "maintenance_router",
    "ui_router",
]

