from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SENSOR_UNAVAILABLE = "sensor_unavailable"
SENSOR_UNKNOWN = "sensor_unknown"
VALVE_CLOSE_UNCONFIRMED = "valve_close_unconfirmed"
DEVICE_CONFIRMATION_TIMEOUT = "device_confirmation_timeout"


@dataclass(frozen=True)
class FaultRecord:
    fault_id: str
    fault_type: str
    source: str
    entity_id: str
    category: str
    value: Any
    opened_at: float
    severity: str
    blocks_clear: bool = False


@dataclass(frozen=True)
class ConfirmationRecord:
    confirmation_key: str
    device: str
    requested_action: str
    requested_at: float
    deadline_at: float | None
    confirmed: bool = False
    confirmed_at: float | None = None
    failure_fault_id: str | None = None
    blocks_clear_on_timeout: bool = False


@dataclass(frozen=True)
class ClearBlockRecord:
    block_key: str
    reason_code: str
    source: str
    started_at: float
    requires_manual_reset: bool = False


@dataclass(frozen=True)
class FaultState:
    active_sensor_faults: dict[str, FaultRecord] = field(default_factory=dict)
    active_device_faults: dict[str, FaultRecord] = field(default_factory=dict)
    pending_confirmations: dict[str, ConfirmationRecord] = field(default_factory=dict)
    clear_blockers: dict[str, ClearBlockRecord] = field(default_factory=dict)
    last_fault_notify_ts_by_key: dict[str, float] = field(default_factory=dict)
    last_fault_clear_notify_ts_by_key: dict[str, float] = field(default_factory=dict)
    active_fault_notified_keys: set[str] = field(default_factory=set)
    cleared_fault_notified_keys: set[str] = field(default_factory=set)


__all__ = [
    "ClearBlockRecord",
    "ConfirmationRecord",
    "DEVICE_CONFIRMATION_TIMEOUT",
    "FaultRecord",
    "FaultState",
    "SENSOR_UNAVAILABLE",
    "SENSOR_UNKNOWN",
    "VALVE_CLOSE_UNCONFIRMED",
]
