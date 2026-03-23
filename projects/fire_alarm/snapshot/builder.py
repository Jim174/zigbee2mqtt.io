from __future__ import annotations

from typing import Any, Mapping

from ..fire_alarm_rules import is_gas_alarm_like, is_smoke_alarm_like
from .models import (
    ShutdownSnapshot,
    Snapshot,
    SnapshotSummary,
    TemperatureTrackerState,
)
from .occupancy import build_occupancy_snapshot
from .temperature import build_temperature_snapshot

SEVERITY_ORDER = ("observe", "prealarm", "alarm", "critical")


def _is_unavailable(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in {"unavailable", "unknown", "none", "null", ""}


def _max_severity(severities: list[str | None]) -> str | None:
    ranked = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    available = [severity for severity in severities if severity is not None]
    if not available:
        return None
    return max(available, key=lambda severity: ranked.get(severity, -1))


def _collect_states(sensor_cache: Mapping[str, Mapping[str, Any]] | None, *keys: str) -> dict[str, Any]:
    sensor_cache = sensor_cache or {}
    for key in keys:
        states = sensor_cache.get(key)
        if states is not None:
            return dict(states)
    return {}


def _build_shutdown_snapshot(shutdown_state: Mapping[str, Any] | None = None) -> ShutdownSnapshot:
    shutdown_state = shutdown_state or {}
    return ShutdownSnapshot(
        protective_shutdown_active=bool(shutdown_state.get("protective_shutdown_active", False)),
        hard_lockout_active=bool(shutdown_state.get("hard_lockout_active", False)),
        valve_requested_closed=bool(shutdown_state.get("valve_requested_closed", False)),
        valve_confirmed_closed=bool(shutdown_state.get("valve_confirmed_closed", False)),
        exhaust_requested_on=bool(shutdown_state.get("exhaust_requested_on", False)),
        exhaust_confirmed_on=bool(shutdown_state.get("exhaust_confirmed_on", False)),
        clear_blocked_by_shutdown=bool(shutdown_state.get("clear_blocked_by_shutdown", False)),
    )


def build_snapshot(
    *,
    sensor_cache: Mapping[str, Mapping[str, Any]] | None,
    trigger_entity_id: str,
    trigger_source: str,
    trigger_event: str,
    old_value: Any,
    new_value: Any,
    occupancy_mode: Any = None,
    occupancy_is_home: Any = None,
    occupancy_is_sleeping: Any = None,
    occupied_rooms: list[str] | None = None,
    primary_zone: Any = None,
    presence_entities: Mapping[str, Any] | None = None,
    shutdown_state: Mapping[str, Any] | None = None,
    temperature_tracker_state: TemperatureTrackerState | None = None,
    now_ts: float | None = None,
) -> Snapshot:
    smoke_states = _collect_states(sensor_cache, "smoke")
    gas_states = _collect_states(sensor_cache, "gas")
    stove_states = _collect_states(sensor_cache, "temperature_stove", "stove")
    environment_states = _collect_states(sensor_cache, "temperature_environment", "environment")
    other_room_states = _collect_states(sensor_cache, "temperature_other_room", "other_room")

    smoke_active_entities = sorted(
        entity_id for entity_id, value in smoke_states.items() if is_smoke_alarm_like(value)
    )
    gas_active_entities = sorted(
        entity_id for entity_id, value in gas_states.items() if is_gas_alarm_like(value)
    )
    smoke_unavailable_entities = sorted(
        entity_id for entity_id, value in smoke_states.items() if _is_unavailable(value)
    )
    gas_unavailable_entities = sorted(
        entity_id for entity_id, value in gas_states.items() if _is_unavailable(value)
    )

    temperature_snapshot = build_temperature_snapshot(
        stove_states=stove_states,
        environment_states=environment_states,
        other_room_states=other_room_states,
        tracker_state=temperature_tracker_state,
        now_ts=now_ts,
    )
    occupancy_snapshot = build_occupancy_snapshot(
        mode=occupancy_mode,
        is_home=occupancy_is_home,
        is_sleeping=occupancy_is_sleeping,
        occupied_rooms=occupied_rooms,
        primary_zone=primary_zone,
        presence_entities=presence_entities,
    )
    shutdown_snapshot = _build_shutdown_snapshot(shutdown_state)

    temperature_severity = _max_severity(
        [
            temperature_snapshot.environment_highest_severity,
            temperature_snapshot.other_room_highest_severity,
        ]
    )
    if smoke_active_entities or gas_active_entities:
        fire_monitor_highest_severity = "critical"
    else:
        fire_monitor_highest_severity = temperature_severity

    any_unavailable = bool(smoke_unavailable_entities or gas_unavailable_entities)
    for states in (stove_states, environment_states, other_room_states):
        if any(_is_unavailable(value) for value in states.values()):
            any_unavailable = True
            break

    summary = SnapshotSummary(
        smoke_any_alarm=bool(smoke_active_entities),
        gas_any_alarm=bool(gas_active_entities),
        environment_highest_severity=temperature_snapshot.environment_highest_severity,
        other_room_highest_severity=temperature_snapshot.other_room_highest_severity,
        stove_reminder_active=temperature_snapshot.stove_reminder_active,
        any_unavailable=any_unavailable,
        fire_monitor_highest_severity=fire_monitor_highest_severity,
        occupancy_mode=occupancy_snapshot.mode,
        proposed_clear_is_safe=(
            fire_monitor_highest_severity is None
            and not any_unavailable
            and not shutdown_snapshot.clear_blocked_by_shutdown
        ),
    )

    return Snapshot(
        trigger_entity_id=trigger_entity_id,
        trigger_source=trigger_source,
        trigger_event=trigger_event,
        old_value=old_value,
        new_value=new_value,
        smoke_active_entities=smoke_active_entities,
        gas_active_entities=gas_active_entities,
        smoke_unavailable_entities=smoke_unavailable_entities,
        gas_unavailable_entities=gas_unavailable_entities,
        temperature=temperature_snapshot,
        occupancy=occupancy_snapshot,
        shutdown=shutdown_snapshot,
        summary=summary,
    )
