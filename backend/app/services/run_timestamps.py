"""Stable timestamp helpers for research runs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def completed_at_sql(alias: str = "r") -> str:
    """SQL expression for the immutable run completion timestamp."""
    return f"COALESCE(({alias}.state->>'completed_at')::timestamptz, {alias}.created_at)"


def stable_completed_at_from_state(state: Any, fallback: datetime) -> datetime:
    """Return state.completed_at when present, otherwise a stable fallback."""
    if isinstance(state, dict):
        raw = state.get("completed_at")
        if isinstance(raw, str) and raw:
            normalized = raw.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
    return fallback


def mark_terminal_completed_at(state: Any, now: datetime | None = None) -> None:
    """Set completed_at once; later archive/position updates must not move it."""
    completed_at = (now or datetime.now(timezone.utc)).isoformat()
    if isinstance(state, dict):
        state.setdefault("completed_at", completed_at)
        return

    if getattr(state, "completed_at", None) is None:
        setattr(state, "completed_at", completed_at)
