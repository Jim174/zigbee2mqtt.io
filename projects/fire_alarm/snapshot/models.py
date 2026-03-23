from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TemperatureTrackerState:
    stove_reminder_since_by_entity: dict[str, float | None] = field(default_factory=dict)
    environment_observe_since_by_entity: dict[str, float | None] = field(default_factory=dict)
    environment_prealarm_since_by_entity: dict[str, float | None] = field(default_factory=dict)
    environment_alarm_since_by_entity: dict[str, float | None] = field(default_factory=dict)
    environment_critical_since_by_entity: dict[str, float | None] = field(default_factory=dict)
    other_room_observe_since_by_entity: dict[str, float | None] = field(default_factory=dict)
    other_room_prealarm_since_by_entity: dict[str, float | None] = field(default_factory=dict)
    other_room_alarm_since_by_entity: dict[str, float | None] = field(default_factory=dict)
    other_room_critical_since_by_entity: dict[str, float | None] = field(default_factory=dict)
    stove_reminder_active_by_entity: dict[str, bool] = field(default_factory=dict)
    environment_observe_active_by_entity: dict[str, bool] = field(default_factory=dict)
    environment_prealarm_active_by_entity: dict[str, bool] = field(default_factory=dict)
    environment_alarm_active_by_entity: dict[str, bool] = field(default_factory=dict)
    environment_critical_active_by_entity: dict[str, bool] = field(default_factory=dict)
    other_room_observe_active_by_entity: dict[str, bool] = field(default_factory=dict)
    other_room_prealarm_active_by_entity: dict[str, bool] = field(default_factory=dict)
    other_room_alarm_active_by_entity: dict[str, bool] = field(default_factory=dict)
    other_room_critical_active_by_entity: dict[str, bool] = field(default_factory=dict)
    environment_last_value_by_entity: dict[str, float] = field(default_factory=dict)
    environment_last_ts_by_entity: dict[str, float] = field(default_factory=dict)
    other_room_last_value_by_entity: dict[str, float] = field(default_factory=dict)
    other_room_last_ts_by_entity: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TemperatureSnapshot:
    stove_entities: dict[str, Any]
    environment_entities: dict[str, Any]
    other_room_entities: dict[str, Any]
    stove_max: float | None
    environment_max: float | None
    other_room_max: float | None
    stove_reminder_active: bool
    stove_reminder_entities: list[str]
    environment_highest_severity: str | None
    other_room_highest_severity: str | None
    environment_observe_entities: list[str]
    environment_prealarm_entities: list[str]
    environment_alarm_entities: list[str]
    environment_critical_entities: list[str]
    other_room_observe_entities: list[str]
    other_room_prealarm_entities: list[str]
    other_room_alarm_entities: list[str]
    other_room_critical_entities: list[str]
    non_numeric_entities: list[str]
    tracker_state: TemperatureTrackerState


@dataclass(frozen=True)
class OccupancySnapshot:
    mode: str | None
    is_home: bool | None
    is_sleeping: bool | None
    occupied_rooms: list[str]
    primary_zone: str | None
    presence_entities: dict[str, Any]


@dataclass(frozen=True)
class ShutdownSnapshot:
    protective_shutdown_active: bool
    hard_lockout_active: bool
    valve_requested_closed: bool
    valve_confirmed_closed: bool
    exhaust_requested_on: bool
    exhaust_confirmed_on: bool
    clear_blocked_by_shutdown: bool


@dataclass(frozen=True)
class SnapshotSummary:
    smoke_any_alarm: bool
    gas_any_alarm: bool
    environment_highest_severity: str | None
    other_room_highest_severity: str | None
    stove_reminder_active: bool
    any_unavailable: bool
    fire_monitor_highest_severity: str | None
    occupancy_mode: str | None
    proposed_clear_is_safe: bool


@dataclass(frozen=True)
class Snapshot:
    trigger_entity_id: str
    trigger_source: str
    trigger_event: str
    old_value: Any
    new_value: Any
    smoke_active_entities: list[str]
    gas_active_entities: list[str]
    smoke_unavailable_entities: list[str]
    gas_unavailable_entities: list[str]
    temperature: TemperatureSnapshot
    occupancy: OccupancySnapshot
    shutdown: ShutdownSnapshot
    summary: SnapshotSummary
