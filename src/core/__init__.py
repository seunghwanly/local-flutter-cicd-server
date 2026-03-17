"""Compatibility shim for the legacy core package."""

from __future__ import annotations

from importlib import import_module
import sys

_PACKAGE_NAME = "src.internal.core"
_MODULES = [
    "build_runtime",
    "config",
    "logging_utils",
    "queue_manager",
]

for _module_name in _MODULES:
    _module = import_module(f"{_PACKAGE_NAME}.{_module_name}")
    sys.modules[f"{__name__}.{_module_name}"] = _module
    globals()[_module_name] = _module

from ..internal.core.build_runtime import BuildRuntimeContext  # noqa: E402,F401
from ..internal.core.config import (  # noqa: E402,F401
    get_build_workspace,
    get_cache_cleanup_days,
    get_isolated_env,
    get_shared_cache_dir,
    get_version_cache_dirs,
)
from ..internal.core.queue_manager import queue_manager  # noqa: E402,F401

__all__ = [
    "BuildRuntimeContext",
    "get_build_workspace",
    "get_cache_cleanup_days",
    "get_isolated_env",
    "get_shared_cache_dir",
    "get_version_cache_dirs",
    "queue_manager",
]
