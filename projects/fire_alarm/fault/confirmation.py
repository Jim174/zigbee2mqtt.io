from __future__ import annotations

from time import monotonic
from uuid import uuid4

from .blocking import create_clear_blocker
from .detector import device_fault_key, open_or_update_device_fault
from .models import (
    ConfirmationRecord,
    DEVICE_CONFIRMATION_TIMEOUT,
    FaultState,
    VALVE_CLOSE_UNCONFIRMED,
)


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


def register_pending_confirmation(
    *,
    state: FaultState,
    device: str,
    requested_action: str,
    confirmation_key: str | None = None,
    timeout_sec: float | None = None,
    requested_at: float | None = None,
    blocks_clear_on_timeout: bool = False,
) -> FaultState:
    requested_at = monotonic() if requested_at is None else requested_at
    confirmation_key = confirmation_key or f"confirm-{uuid4().hex}"
    payload = _clone_state(state)
    pending = payload["pending_confirmations"]
    assert isinstance(pending, dict)
    pending[confirmation_key] = ConfirmationRecord(
        confirmation_key=confirmation_key,
        device=device,
        requested_action=requested_action,
        requested_at=requested_at,
        deadline_at=None if timeout_sec is None else requested_at + timeout_sec,
        confirmed=False,
        confirmed_at=None,
        failure_fault_id=None,
        blocks_clear_on_timeout=blocks_clear_on_timeout,
    )
    return FaultState(**payload)


def confirm_pending_confirmation(
    *,
    state: FaultState,
    confirmation_key: str,
    confirmed_at: float | None = None,
) -> FaultState:
    confirmed_at = monotonic() if confirmed_at is None else confirmed_at
    payload = _clone_state(state)
    pending = payload["pending_confirmations"]
    assert isinstance(pending, dict)
    existing = pending.get(confirmation_key)
    if existing is None:
        return FaultState(**payload)
    pending[confirmation_key] = ConfirmationRecord(
        confirmation_key=existing.confirmation_key,
        device=existing.device,
        requested_action=existing.requested_action,
        requested_at=existing.requested_at,
        deadline_at=existing.deadline_at,
        confirmed=True,
        confirmed_at=confirmed_at,
        failure_fault_id=existing.failure_fault_id,
        blocks_clear_on_timeout=existing.blocks_clear_on_timeout,
    )
    return FaultState(**payload)


def expire_pending_confirmations(
    *,
    state: FaultState,
    now_ts: float | None = None,
) -> FaultState:
    now_ts = monotonic() if now_ts is None else now_ts
    next_state = state
    expired_keys: list[str] = []
    for confirmation_key, record in state.pending_confirmations.items():
        if record.confirmed:
            continue
        if record.deadline_at is None or record.deadline_at > now_ts:
            continue
        expired_keys.append(confirmation_key)
        category = VALVE_CLOSE_UNCONFIRMED if record.requested_action == "close_valve" else DEVICE_CONFIRMATION_TIMEOUT
        next_state = open_or_update_device_fault(
            state=next_state,
            device=record.device,
            action=record.requested_action,
            category=category,
            value={"confirmation_key": confirmation_key, "deadline_at": record.deadline_at},
            severity="error",
            blocks_clear=record.blocks_clear_on_timeout,
            opened_at=record.deadline_at,
        )
        if record.blocks_clear_on_timeout:
            next_state = create_clear_blocker(
                state=next_state,
                block_key=device_fault_key(record.device, record.requested_action),
                reason_code=category,
                source=record.device,
                started_at=record.deadline_at,
            )

    if not expired_keys:
        return next_state

    payload = _clone_state(next_state)
    pending = payload["pending_confirmations"]
    assert isinstance(pending, dict)
    for confirmation_key in expired_keys:
        pending.pop(confirmation_key, None)
    return FaultState(**payload)
