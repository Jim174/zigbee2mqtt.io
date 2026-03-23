from __future__ import annotations

from typing import Any, Mapping

from .models import OccupancySnapshot


def _normalize_mode(mode: Any) -> str | None:
    if mode is None:
        return None
    normalized = str(mode).strip().lower()
    return normalized or None


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "home", "occupied", "sleeping"}:
        return True
    if normalized in {"0", "false", "no", "off", "away", "not_home", "vacant", "awake"}:
        return False
    return None


def build_occupancy_snapshot(
    *,
    mode: Any = None,
    is_home: Any = None,
    is_sleeping: Any = None,
    occupied_rooms: list[str] | None = None,
    primary_zone: Any = None,
    presence_entities: Mapping[str, Any] | None = None,
) -> OccupancySnapshot:
    return OccupancySnapshot(
        mode=_normalize_mode(mode),
        is_home=_to_bool(is_home),
        is_sleeping=_to_bool(is_sleeping),
        occupied_rooms=sorted(str(room) for room in (occupied_rooms or [])),
        primary_zone=None if primary_zone is None else (str(primary_zone).strip() or None),
        presence_entities=dict(presence_entities or {}),
    )
