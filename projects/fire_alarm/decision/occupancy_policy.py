from __future__ import annotations

from typing import Literal

from ..snapshot.models import OccupancySnapshot

OccupancyMode = Literal["occupied", "unoccupied", "unknown"]


OCCUPIED_MODES = {"occupied", "home", "present", "awake", "sleeping"}
UNOCCUPIED_MODES = {"unoccupied", "away", "vacant", "not_home", "empty"}


def normalize_occupancy_mode(occupancy: OccupancySnapshot) -> OccupancyMode:
    mode = occupancy.mode
    if mode is None:
        return "unknown"
    normalized = str(mode).strip().lower()
    if normalized in OCCUPIED_MODES:
        return "occupied"
    if normalized in UNOCCUPIED_MODES:
        return "unoccupied"
    return "unknown"


def is_occupied(occupancy: OccupancySnapshot) -> bool:
    return normalize_occupancy_mode(occupancy) == "occupied"


def is_unoccupied(occupancy: OccupancySnapshot) -> bool:
    return normalize_occupancy_mode(occupancy) == "unoccupied"


def is_unknown(occupancy: OccupancySnapshot) -> bool:
    return normalize_occupancy_mode(occupancy) == "unknown"
