from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..snapshot.models import Snapshot


@dataclass(frozen=True)
class ControllerContext:
    current_state: str
    current_phase: str
    last_transition_ts: str | None = None
    acked: bool = False
    acked_incident_id: str | None = None
    silenced: bool = False
    silenced_incident_id: str | None = None
    manual_override: bool = False
    last_notify_ts_by_state: dict[str, float] = field(default_factory=dict)
    last_tts_ts_by_state: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class IncidentState:
    incident_id: str | None = None
    opened_at: str | None = None
    current_state: str | None = None
    current_phase: str | None = None
    highest_state: str | None = None
    primary_hazard_source: str | None = None
    hazard_source_set: list[str] = field(default_factory=list)
    smoke_involved: bool = False
    gas_involved: bool = False
    environment_fire_involved: bool = False
    other_room_fire_involved: bool = False
    protective_shutdown_active: bool = False
    hard_lockout_active: bool = False
    acked: bool = False
    acked_incident_id: str | None = None
    silenced: bool = False
    silenced_incident_id: str | None = None
    clear_block_active: bool = False
    clear_block_reason_code: str | None = None


@dataclass(frozen=True)
class ClearBlockRecord:
    block_key: str
    reason_code: str
    source: str
    started_at: str
    requires_manual_reset: bool = False


@dataclass(frozen=True)
class FaultState:
    active_sensor_faults: dict[str, Any] = field(default_factory=dict)
    active_device_faults: dict[str, Any] = field(default_factory=dict)
    pending_confirmations: dict[str, Any] = field(default_factory=dict)
    clear_blockers: dict[str, ClearBlockRecord] = field(default_factory=dict)
    last_fault_notify_ts_by_key: dict[str, float] = field(default_factory=dict)
    last_fault_clear_notify_ts_by_key: dict[str, float] = field(default_factory=dict)
    active_fault_notified_keys: set[str] = field(default_factory=set)
    cleared_fault_notified_keys: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class DecisionResult:
    current_state: str
    next_state: str
    current_phase: str
    next_phase: str
    transition_changed: bool
    primary_hazard_source: str | None
    reason_codes: list[str]
    clear_blocked: bool
    clear_block_reason_code: str | None
    incident_should_open: bool
    incident_should_close: bool
    incident_should_escalate: bool
    protective_shutdown_requested: bool
    hard_lockout_requested: bool
    notify_severity: str | None
    tts_severity: str | None
    log_message: str | None
    log_level: str | None


__all__ = [
    "ClearBlockRecord",
    "ControllerContext",
    "DecisionResult",
    "FaultState",
    "IncidentState",
    "Snapshot",
]
