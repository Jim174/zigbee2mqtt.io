"""Pure rule helpers for fire alarm decision pipeline."""

from __future__ import annotations

from typing import Any

from . import fire_alarm_constants as c


def is_smoke_alarm_like(value: Any) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"alarm", "on", "detected", "triggered", "true", "1"}


def is_gas_alarm_like(value: Any) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"alarm", "on", "detected", "high", "triggered", "true", "1"}


def to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def risk_priority(state: str) -> int:
    priority_map = {
        c.STATE_DISABLED: -1,
        c.STATE_NORMAL: 0,
        c.STATE_OBSERVE: 1,
        c.STATE_PREALARM: 2,
        c.STATE_ALARM: 3,
        c.STATE_CRITICAL: 4,
    }
    return priority_map.get(state, 0)
