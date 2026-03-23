from __future__ import annotations

from ..snapshot.models import Snapshot

STATE_RANK = {
    None: 0,
    "observe": 1,
    "prealarm": 2,
    "alarm": 3,
    "critical": 4,
}


def hazard_source_set(snapshot: Snapshot) -> list[str]:
    sources: list[str] = []
    if snapshot.summary.smoke_any_alarm:
        sources.append("smoke")
    if snapshot.summary.gas_any_alarm:
        sources.append("gas")
    if snapshot.summary.environment_highest_severity is not None:
        sources.append("environment_fire")
    if snapshot.summary.other_room_highest_severity is not None:
        sources.append("other_room_fire")
    return sources


def did_escalate(
    *,
    previous_state: str | None,
    next_state: str | None,
    previous_sources: list[str],
    next_sources: list[str],
) -> bool:
    if STATE_RANK.get(next_state, 0) > STATE_RANK.get(previous_state, 0):
        return True
    return set(next_sources) > set(previous_sources)


def is_recovery(
    *,
    previous_state: str | None,
    next_state: str | None,
) -> bool:
    return STATE_RANK.get(next_state, 0) < STATE_RANK.get(previous_state, 0)
