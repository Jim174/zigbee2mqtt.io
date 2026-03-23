from __future__ import annotations

from time import monotonic
from uuid import uuid4
from typing import Any

from .blocking import clear_clear_blocker, create_clear_blocker
from .models import FaultRecord, FaultState, SENSOR_UNAVAILABLE, SENSOR_UNKNOWN


def _clone_state(state: FaultState) -> dict[str, object]:
    return {
        "active_sensor_faults": dict(state.active_sensor_faults),
        "active_device_faults": dict(state.active_device_faults),
        "pending_confirmations": dict(state.pending_confirmations),
        "clear_blockers": dict(state.clear_blockers),
        "last_fault_notify_ts_by_key": dict(state.last_fault_notify_ts_by_key),
        "last_fault_clear_notify_ts_by_key": dict(state.last_fault_clear_notify_ts_by_key),
        "active_fault_notified_keys": set(state.active_fault_notified_keys),
        "cleared_fault_notified_keys": set(state.cleared_fault_notified_keys),
    }


def _fault_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def sensor_fault_key(source: str, entity_id: str) -> str:
    return f"sensor:{source}:{entity_id}"


def device_fault_key(device: str, action: str) -> str:
    return f"device:{device}:{action}"


def _sensor_fault_category(value: Any) -> str:
    normalized = str(value).strip().lower()
    if normalized == "unknown":
        return SENSOR_UNKNOWN
    return SENSOR_UNAVAILABLE


def is_unavailable_like(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in {"unavailable", "unknown", "none", "null", ""}


def open_sensor_fault(
    *,
    state: FaultState,
    source: str,
    entity_id: str,
    value: Any,
    severity: str = "warning",
    blocks_clear: bool = False,
    opened_at: float | None = None,
) -> FaultState:
    payload = _clone_state(state)
    key = sensor_fault_key(source, entity_id)
    active_sensor_faults = payload["active_sensor_faults"]
    assert isinstance(active_sensor_faults, dict)
    existing = active_sensor_faults.get(key)
    category = _sensor_fault_category(value)
    active_sensor_faults[key] = FaultRecord(
        fault_id=existing.fault_id if existing is not None else _fault_id("sensor"),
        fault_type="sensor",
        source=source,
        entity_id=entity_id,
        category=category,
        value=value,
        opened_at=existing.opened_at if existing is not None else (monotonic() if opened_at is None else opened_at),
        severity=severity,
        blocks_clear=blocks_clear,
    )

    active_notified = payload["active_fault_notified_keys"]
    cleared_notified = payload["cleared_fault_notified_keys"]
    assert isinstance(active_notified, set)
    assert isinstance(cleared_notified, set)
    cleared_notified.discard(key)
    if blocks_clear:
        next_state = FaultState(**payload)
        return create_clear_blocker(
            state=next_state,
            block_key=key,
            reason_code=category,
            source=source,
            started_at=monotonic() if opened_at is None else opened_at,
        )
    return FaultState(**payload)


def clear_sensor_fault(
    *,
    state: FaultState,
    source: str,
    entity_id: str,
    cleared_at: float | None = None,
) -> FaultState:
    payload = _clone_state(state)
    key = sensor_fault_key(source, entity_id)
    active_sensor_faults = payload["active_sensor_faults"]
    assert isinstance(active_sensor_faults, dict)
    existing = active_sensor_faults.pop(key, None)
    if existing is None:
        return FaultState(**payload)

    clear_ts = monotonic() if cleared_at is None else cleared_at
    last_clear = payload["last_fault_clear_notify_ts_by_key"]
    active_notified = payload["active_fault_notified_keys"]
    cleared_notified = payload["cleared_fault_notified_keys"]
    assert isinstance(last_clear, dict)
    assert isinstance(active_notified, set)
    assert isinstance(cleared_notified, set)
    last_clear[key] = clear_ts
    active_notified.discard(key)
    cleared_notified.add(key)
    next_state = FaultState(**payload)
    return clear_clear_blocker(state=next_state, block_key=key)


def open_or_update_device_fault(
    *,
    state: FaultState,
    device: str,
    action: str,
    category: str,
    value: Any,
    severity: str = "error",
    blocks_clear: bool = False,
    opened_at: float | None = None,
) -> FaultState:
    payload = _clone_state(state)
    key = device_fault_key(device, action)
    active_device_faults = payload["active_device_faults"]
    assert isinstance(active_device_faults, dict)
    existing = active_device_faults.get(key)
    active_device_faults[key] = FaultRecord(
        fault_id=existing.fault_id if existing is not None else _fault_id("device"),
        fault_type="device",
        source=device,
        entity_id=device,
        category=category,
        value=value,
        opened_at=existing.opened_at if existing is not None else (monotonic() if opened_at is None else opened_at),
        severity=severity,
        blocks_clear=blocks_clear,
    )
    if blocks_clear:
        next_state = FaultState(**payload)
        return create_clear_blocker(
            state=next_state,
            block_key=key,
            reason_code=category,
            source=device,
            started_at=monotonic() if opened_at is None else opened_at,
        )
    return FaultState(**payload)
