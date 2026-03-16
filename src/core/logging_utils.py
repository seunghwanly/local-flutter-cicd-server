"""Helpers for readable multi-line build logs."""

from __future__ import annotations

from collections.abc import Iterable


def build_log_block(build_id: str | None, title: str, rows: Iterable[tuple[str, object]]) -> str:
    """Format a build log header followed by indented key/value rows."""
    prefix = f"[{build_id}] " if build_id else ""
    lines = [f"{prefix}{title}"]
    for key, value in rows:
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def build_log_line(build_id: str | None, message: str) -> str:
    """Format a single-line build log message with an optional build prefix."""
    prefix = f"[{build_id}] " if build_id else ""
    return f"{prefix}{message}"
