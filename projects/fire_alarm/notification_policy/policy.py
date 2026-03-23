from __future__ import annotations

from time import monotonic

from ..decision.models import ControllerContext, DecisionResult
from ..incident.models import IncidentState
from ..snapshot.models import Snapshot
from .models import MarkUpdateSet, NotificationAction, NotificationActionPlan

DEFAULT_NOTIFY_COOLDOWN_SEC = 300
DEFAULT_TTS_COOLDOWN_SEC = 300


def _now_ts(now_ts: float | None = None) -> float:
    return monotonic() if now_ts is None else now_ts


def _incident_ack_matches(incident_state: IncidentState, controller_context: ControllerContext) -> bool:
    incident_id = incident_state.incident_id
    return bool(
        incident_id
        and controller_context.acked
        and controller_context.acked_incident_id == incident_id
    )


def _incident_silence_matches(incident_state: IncidentState, controller_context: ControllerContext) -> bool:
    incident_id = incident_state.incident_id
    return bool(
        incident_id
        and controller_context.silenced
        and controller_context.silenced_incident_id == incident_id
    )


def _occupancy_mode(snapshot: Snapshot) -> str:
    mode = snapshot.occupancy.mode or snapshot.summary.occupancy_mode
    if mode is None:
        return "unknown"
    normalized = str(mode).strip().lower()
    if normalized in {"occupied", "home", "present", "awake", "sleeping"}:
        return "occupied"
    if normalized in {"unoccupied", "away", "vacant", "not_home", "empty"}:
        return "unoccupied"
    return "unknown"


def _notify_allowed(
    *,
    state: str,
    controller_context: ControllerContext,
    incident_state: IncidentState,
    cooldown_sec: int,
    now_ts: float,
) -> bool:
    if _incident_silence_matches(incident_state, controller_context):
        return False
    last_ts = controller_context.last_notify_ts_by_state.get(state)
    if last_ts is None:
        return True
    return (now_ts - last_ts) >= max(0, cooldown_sec)


def _tts_allowed(
    *,
    state: str,
    controller_context: ControllerContext,
    incident_state: IncidentState,
    cooldown_sec: int,
    now_ts: float,
) -> bool:
    if _incident_silence_matches(incident_state, controller_context):
        return False
    if _incident_ack_matches(incident_state, controller_context):
        return False
    last_ts = controller_context.last_tts_ts_by_state.get(state)
    if last_ts is None:
        return True
    return (now_ts - last_ts) >= max(0, cooldown_sec)


def _build_action(
    *,
    channel: str,
    severity: str,
    message_key: str,
    audience_mode: str,
    payload: dict[str, object],
    suppressed: bool,
) -> NotificationAction:
    return NotificationAction(
        channel=channel,
        severity=severity,
        message_key=message_key,
        audience_mode=audience_mode,
        payload=payload,
        suppressed=suppressed,
    )


def _append_unique(actions: list[NotificationAction], action: NotificationAction) -> None:
    for existing in actions:
        if (
            existing.channel == action.channel
            and existing.message_key == action.message_key
            and existing.severity == action.severity
            and existing.audience_mode == action.audience_mode
        ):
            return
    actions.append(action)


def _plan_stove_warning(
    *,
    actions: list[NotificationAction],
    decision_result: DecisionResult,
    snapshot: Snapshot,
    audience_mode: str,
    notify_allowed: bool,
    tts_allowed: bool,
) -> None:
    if decision_result.primary_hazard_source != "stove_reminder":
        return
    payload = {
        "category": "stove_warning",
        "stove_entities": list(snapshot.temperature.stove_reminder_entities),
        "stove_max": snapshot.temperature.stove_max,
    }
    _append_unique(
        actions,
        _build_action(
            channel="notify",
            severity="warning",
            message_key="stove_warning",
            audience_mode=audience_mode,
            payload=payload,
            suppressed=not notify_allowed,
        ),
    )
    _append_unique(
        actions,
        _build_action(
            channel="tts",
            severity="attention_tone" if audience_mode == "occupied" else "warning_tone",
            message_key="stove_warning",
            audience_mode=audience_mode,
            payload=payload,
            suppressed=not tts_allowed,
        ),
    )


def _plan_environment_fire(
    *,
    actions: list[NotificationAction],
    decision_result: DecisionResult,
    snapshot: Snapshot,
    audience_mode: str,
    notify_allowed: bool,
    tts_allowed: bool,
) -> None:
    if decision_result.primary_hazard_source not in {"environment_fire", "other_room_fire", "smoke", "gas", "multi_hazard"}:
        return
    payload = {
        "category": "environment_fire_warning",
        "hazard_source": decision_result.primary_hazard_source,
        "reason_codes": list(decision_result.reason_codes),
        "fire_monitor_highest_severity": snapshot.summary.fire_monitor_highest_severity,
    }
    _append_unique(
        actions,
        _build_action(
            channel="notify",
            severity=decision_result.notify_severity or decision_result.next_state,
            message_key="environment_fire_warning",
            audience_mode=audience_mode,
            payload=payload,
            suppressed=not notify_allowed,
        ),
    )
    tone = "attention_tone" if audience_mode == "occupied" else "warning_tone"
    if decision_result.next_state in {"alarm", "critical"}:
        tone = "warning_tone"
    _append_unique(
        actions,
        _build_action(
            channel="tts",
            severity=tone,
            message_key="environment_fire_warning",
            audience_mode=audience_mode,
            payload=payload,
            suppressed=not tts_allowed,
        ),
    )


def _plan_close_failure(
    *,
    actions: list[NotificationAction],
    decision_result: DecisionResult,
    audience_mode: str,
    notify_allowed: bool,
    tts_allowed: bool,
) -> None:
    if decision_result.clear_block_reason_code != "valve_close_unconfirmed":
        return
    payload = {
        "category": "close_failure",
        "clear_block_reason_code": decision_result.clear_block_reason_code,
        "reason_codes": list(decision_result.reason_codes),
    }
    _append_unique(
        actions,
        _build_action(
            channel="notify",
            severity="error",
            message_key="close_failure",
            audience_mode=audience_mode,
            payload=payload,
            suppressed=not notify_allowed,
        ),
    )
    _append_unique(
        actions,
        _build_action(
            channel="tts",
            severity="warning_tone",
            message_key="close_failure",
            audience_mode=audience_mode,
            payload=payload,
            suppressed=not tts_allowed,
        ),
    )


def _plan_prohibited_start(
    *,
    actions: list[NotificationAction],
    decision_result: DecisionResult,
    incident_state: IncidentState,
    audience_mode: str,
    notify_allowed: bool,
    tts_allowed: bool,
) -> None:
    if not (decision_result.hard_lockout_requested or incident_state.hard_lockout_active):
        return
    payload = {
        "category": "prohibited_start",
        "hard_lockout_active": True,
        "hazard_source": decision_result.primary_hazard_source,
    }
    _append_unique(
        actions,
        _build_action(
            channel="notify",
            severity="critical",
            message_key="prohibited_start",
            audience_mode=audience_mode,
            payload=payload,
            suppressed=not notify_allowed,
        ),
    )
    _append_unique(
        actions,
        _build_action(
            channel="tts",
            severity="warning_tone",
            message_key="prohibited_start",
            audience_mode=audience_mode,
            payload=payload,
            suppressed=not tts_allowed,
        ),
    )


def _build_mark_updates(
    *,
    state: str,
    actions: list[NotificationAction],
    now_ts: float,
) -> MarkUpdateSet:
    notify_marks: dict[str, float | None] = {}
    tts_marks: dict[str, float | None] = {}
    for action in actions:
        if action.suppressed:
            continue
        if action.channel == "notify":
            notify_marks[state] = now_ts
        elif action.channel == "tts":
            tts_marks[state] = now_ts
    return MarkUpdateSet(
        notify_state_marks=notify_marks,
        tts_state_marks=tts_marks,
        fault_marks={},
        fault_clear_marks={},
    )


def build_notification_action_plan(
    *,
    decision_result: DecisionResult,
    snapshot: Snapshot,
    controller_context: ControllerContext,
    incident_state: IncidentState,
    notify_cooldown_sec: int = DEFAULT_NOTIFY_COOLDOWN_SEC,
    tts_cooldown_sec: int = DEFAULT_TTS_COOLDOWN_SEC,
    now_ts: float | None = None,
) -> NotificationActionPlan:
    now_ts = _now_ts(now_ts)
    audience_mode = _occupancy_mode(snapshot)
    state = decision_result.next_state
    notify_allowed = _notify_allowed(
        state=state,
        controller_context=controller_context,
        incident_state=incident_state,
        cooldown_sec=notify_cooldown_sec,
        now_ts=now_ts,
    )
    tts_allowed = _tts_allowed(
        state=state,
        controller_context=controller_context,
        incident_state=incident_state,
        cooldown_sec=tts_cooldown_sec,
        now_ts=now_ts,
    )

    actions: list[NotificationAction] = []
    _plan_stove_warning(
        actions=actions,
        decision_result=decision_result,
        snapshot=snapshot,
        audience_mode=audience_mode,
        notify_allowed=notify_allowed,
        tts_allowed=tts_allowed,
    )
    _plan_environment_fire(
        actions=actions,
        decision_result=decision_result,
        snapshot=snapshot,
        audience_mode=audience_mode,
        notify_allowed=notify_allowed,
        tts_allowed=tts_allowed,
    )
    _plan_close_failure(
        actions=actions,
        decision_result=decision_result,
        audience_mode=audience_mode,
        notify_allowed=notify_allowed,
        tts_allowed=tts_allowed,
    )
    _plan_prohibited_start(
        actions=actions,
        decision_result=decision_result,
        incident_state=incident_state,
        audience_mode=audience_mode,
        notify_allowed=notify_allowed,
        tts_allowed=tts_allowed,
    )

    mark_updates = _build_mark_updates(state=state, actions=actions, now_ts=now_ts)
    return NotificationActionPlan(
        state=decision_result.next_state,
        phase=decision_result.next_phase,
        notification_actions=actions,
        mark_updates=mark_updates,
    )
