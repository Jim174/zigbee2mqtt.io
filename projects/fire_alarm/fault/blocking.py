from __future__ import annotations

from time import monotonic

from .models import ClearBlockRecord, FaultState


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


def create_clear_blocker(
    *,
    state: FaultState,
    block_key: str,
    reason_code: str,
    source: str,
    started_at: float | None = None,
    requires_manual_reset: bool = False,
) -> FaultState:
    payload = _clone_state(state)
    clear_blockers = payload["clear_blockers"]
    assert isinstance(clear_blockers, dict)
    existing = clear_blockers.get(block_key)
    clear_blockers[block_key] = ClearBlockRecord(
        block_key=block_key,
        reason_code=reason_code,
        source=source,
        started_at=(existing.started_at if existing is not None else (monotonic() if started_at is None else started_at)),
        requires_manual_reset=requires_manual_reset or (existing.requires_manual_reset if existing is not None else False),
    )
    return FaultState(**payload)


def clear_clear_blocker(*, state: FaultState, block_key: str) -> FaultState:
    payload = _clone_state(state)
    clear_blockers = payload["clear_blockers"]
    assert isinstance(clear_blockers, dict)
    clear_blockers.pop(block_key, None)
    return FaultState(**payload)


def is_clear_blocked(state: FaultState) -> bool:
    return bool(state.clear_blockers)


def clear_block_reason_codes(state: FaultState) -> list[str]:
    return sorted({block.reason_code for block in state.clear_blockers.values()})
