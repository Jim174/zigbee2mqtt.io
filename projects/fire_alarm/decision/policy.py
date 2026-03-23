from __future__ import annotations

from . import reason_codes as rc
from ..snapshot.models import Snapshot
from .models import ControllerContext, DecisionResult, FaultState, IncidentState
from .occupancy_policy import normalize_occupancy_mode
from .shutdown_policy import should_request_hard_lockout, should_request_protective_shutdown


PHASE_BY_STATE = {
    "observe": "observe",
    "prealarm": "verify",
    "alarm": "alert",
    "critical": "emergency",
}
SEVERITY_TO_STATE = {
    None: "observe",
    "observe": "observe",
    "prealarm": "prealarm",
    "alarm": "alarm",
    "critical": "critical",
}
RANK = {
    "observe": 1,
    "prealarm": 2,
    "alarm": 3,
    "critical": 4,
}


def _max_state(state_a: str, state_b: str) -> str:
    return state_a if RANK.get(state_a, 0) >= RANK.get(state_b, 0) else state_b


def _temperature_driven_state(snapshot: Snapshot) -> str:
    return SEVERITY_TO_STATE.get(snapshot.summary.fire_monitor_highest_severity, "observe")


def _base_state(snapshot: Snapshot) -> str:
    state = _temperature_driven_state(snapshot)
    if snapshot.summary.smoke_any_alarm and snapshot.summary.gas_any_alarm:
        return "critical"
    if snapshot.summary.smoke_any_alarm or snapshot.summary.gas_any_alarm:
        return _max_state(state, "alarm")
    return state


def _primary_hazard_source(snapshot: Snapshot, clear_blocked: bool) -> str | None:
    smoke_active = snapshot.summary.smoke_any_alarm
    gas_active = snapshot.summary.gas_any_alarm
    if smoke_active and gas_active:
        return "multi_hazard"
    if smoke_active:
        return "smoke"
    if gas_active:
        return "gas"
    if snapshot.temperature.environment_highest_severity is not None:
        return "environment_fire"
    if snapshot.temperature.other_room_highest_severity is not None:
        return "other_room_fire"
    if snapshot.temperature.stove_reminder_active:
        return "stove_reminder"
    if clear_blocked:
        return "fault_only"
    return None


def _reason_codes(snapshot: Snapshot, occupancy_mode: str, clear_blocked: bool, hard_lockout_requested: bool, protective_shutdown_requested: bool) -> list[str]:
    reasons: list[str] = []
    if snapshot.summary.smoke_any_alarm:
        reasons.append(rc.SMOKE_ACTIVE)
    if snapshot.summary.gas_any_alarm:
        reasons.append(rc.GAS_ACTIVE)
    if snapshot.summary.smoke_any_alarm and snapshot.summary.gas_any_alarm:
        reasons.append(rc.MULTI_HAZARD)

    if snapshot.summary.environment_highest_severity == "observe":
        reasons.append(rc.ENVIRONMENT_OBSERVE)
    elif snapshot.summary.environment_highest_severity == "prealarm":
        reasons.append(rc.ENVIRONMENT_PREALARM)
    elif snapshot.summary.environment_highest_severity == "alarm":
        reasons.append(rc.ENVIRONMENT_ALARM)
    elif snapshot.summary.environment_highest_severity == "critical":
        reasons.append(rc.ENVIRONMENT_CRITICAL)

    if snapshot.summary.other_room_highest_severity == "observe":
        reasons.append(rc.OTHER_ROOM_OBSERVE)
    elif snapshot.summary.other_room_highest_severity == "prealarm":
        reasons.append(rc.OTHER_ROOM_PREALARM)
    elif snapshot.summary.other_room_highest_severity == "alarm":
        reasons.append(rc.OTHER_ROOM_ALARM)
    elif snapshot.summary.other_room_highest_severity == "critical":
        reasons.append(rc.OTHER_ROOM_CRITICAL)

    if snapshot.temperature.stove_reminder_active:
        reasons.append(rc.STOVE_REMINDER)
    if snapshot.summary.fire_monitor_highest_severity is not None:
        reasons.append(rc.TEMPERATURE_DRIVEN_RISK)

    if occupancy_mode == "occupied":
        reasons.append(rc.OCCUPANCY_OCCUPIED)
    elif occupancy_mode == "unoccupied":
        reasons.append(rc.OCCUPANCY_UNOCCUPIED)
    else:
        reasons.append(rc.OCCUPANCY_UNKNOWN)

    if clear_blocked:
        reasons.append(rc.CLEAR_BLOCK_ACTIVE)
    if hard_lockout_requested:
        reasons.append(rc.HARD_LOCKOUT_REQUESTED)
    if protective_shutdown_requested:
        reasons.append(rc.PROTECTIVE_SHUTDOWN_REQUESTED)
    if not snapshot.summary.smoke_any_alarm and not snapshot.summary.gas_any_alarm and snapshot.summary.fire_monitor_highest_severity is None:
        reasons.append(rc.NO_FIRE_MONITOR_RISK)
    return reasons


def build_decision_result(
    *,
    snapshot: Snapshot,
    controller_context: ControllerContext,
    incident_state: IncidentState,
    fault_state: FaultState,
) -> DecisionResult:
    clear_blocked = bool(fault_state.clear_blockers)
    clear_block_reason_code = None
    if clear_blocked:
        clear_block_reason_code = next(iter(fault_state.clear_blockers.values())).reason_code

    next_state = _base_state(snapshot)
    hard_lockout_requested = should_request_hard_lockout(
        snapshot=snapshot,
        incident_state=incident_state,
        fault_state=fault_state,
    )
    protective_shutdown_requested = should_request_protective_shutdown(
        snapshot=snapshot,
        proposed_state=next_state,
        hard_lockout_requested=hard_lockout_requested,
    )
    occupancy_mode = normalize_occupancy_mode(snapshot.occupancy)
    primary_hazard_source = _primary_hazard_source(snapshot, clear_blocked)
    reason_codes = _reason_codes(
        snapshot=snapshot,
        occupancy_mode=occupancy_mode,
        clear_blocked=clear_blocked,
        hard_lockout_requested=hard_lockout_requested,
        protective_shutdown_requested=protective_shutdown_requested,
    )

    if primary_hazard_source is None and clear_blocked:
        primary_hazard_source = "fault_only"
        if rc.FAULT_ONLY not in reason_codes:
            reason_codes.append(rc.FAULT_ONLY)

    current_state = controller_context.current_state
    current_phase = controller_context.current_phase
    next_phase = PHASE_BY_STATE.get(next_state, current_phase)
    transition_changed = next_state != current_state or next_phase != current_phase
    incident_should_open = incident_state.incident_id is None and primary_hazard_source not in {None, "stove_reminder", "fault_only"}
    incident_should_close = (
        incident_state.incident_id is not None
        and primary_hazard_source in {None, "stove_reminder", "fault_only"}
        and not clear_blocked
    )
    incident_should_escalate = (
        incident_state.incident_id is not None
        and not incident_should_close
        and RANK.get(next_state, 0) > RANK.get(incident_state.current_state or "observe", 0)
    )

    log_message = None
    log_level = None
    if clear_blocked:
        log_message = f"decision clear blocked: reason={clear_block_reason_code}"
        log_level = "WARNING"
    elif transition_changed:
        log_message = f"decision next_state={next_state} hazard={primary_hazard_source}"
        log_level = "INFO"

    notify_severity = next_state if primary_hazard_source not in {None, "fault_only"} else None
    tts_severity = next_state if next_state in {"alarm", "critical"} else None

    return DecisionResult(
        current_state=current_state,
        next_state=next_state,
        current_phase=current_phase,
        next_phase=next_phase,
        transition_changed=transition_changed,
        primary_hazard_source=primary_hazard_source,
        reason_codes=reason_codes,
        clear_blocked=clear_blocked,
        clear_block_reason_code=clear_block_reason_code,
        incident_should_open=incident_should_open,
        incident_should_close=incident_should_close,
        incident_should_escalate=incident_should_escalate,
        protective_shutdown_requested=protective_shutdown_requested,
        hard_lockout_requested=hard_lockout_requested,
        notify_severity=notify_severity,
        tts_severity=tts_severity,
        log_message=log_message,
        log_level=log_level,
    )
