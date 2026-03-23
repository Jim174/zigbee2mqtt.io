from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ..decision.models import ControllerContext, DecisionResult
from ..snapshot.models import Snapshot
from .escalation import did_escalate, hazard_source_set, is_recovery
from .models import IncidentLifecycleResult, IncidentState


def _new_incident_id() -> str:
    return f"inc-{uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _highest_state(previous: IncidentState, next_state: str) -> str:
    previous_state = previous.highest_state or previous.current_state or next_state
    ranking = {"observe": 1, "prealarm": 2, "alarm": 3, "critical": 4}
    return next_state if ranking.get(next_state, 0) >= ranking.get(previous_state, 0) else previous_state


def _bind_ack(incident_id: str, controller_context: ControllerContext) -> tuple[bool, str | None]:
    if controller_context.acked and controller_context.acked_incident_id == incident_id:
        return True, incident_id
    return False, None


def _bind_silence(incident_id: str, controller_context: ControllerContext) -> tuple[bool, str | None]:
    if controller_context.silenced and controller_context.silenced_incident_id == incident_id:
        return True, incident_id
    return False, None


def _build_state(
    *,
    incident_id: str,
    opened_at: str,
    decision_result: DecisionResult,
    snapshot: Snapshot,
    controller_context: ControllerContext,
    previous_incident_state: IncidentState,
) -> IncidentState:
    sources = hazard_source_set(snapshot)
    acked, acked_incident_id = _bind_ack(incident_id, controller_context)
    silenced, silenced_incident_id = _bind_silence(incident_id, controller_context)
    return IncidentState(
        incident_id=incident_id,
        opened_at=opened_at,
        current_state=decision_result.next_state,
        current_phase=decision_result.next_phase,
        highest_state=_highest_state(previous_incident_state, decision_result.next_state),
        primary_hazard_source=decision_result.primary_hazard_source,
        hazard_source_set=sources,
        smoke_involved="smoke" in sources,
        gas_involved="gas" in sources,
        environment_fire_involved="environment_fire" in sources,
        other_room_fire_involved="other_room_fire" in sources,
        protective_shutdown_active=(
            previous_incident_state.protective_shutdown_active or decision_result.protective_shutdown_requested
        ),
        hard_lockout_active=(
            previous_incident_state.hard_lockout_active or decision_result.hard_lockout_requested
        ),
        acked=acked,
        acked_incident_id=acked_incident_id,
        silenced=silenced,
        silenced_incident_id=silenced_incident_id,
        clear_block_active=decision_result.clear_blocked,
        clear_block_reason_code=decision_result.clear_block_reason_code,
    )


def update_incident_lifecycle(
    *,
    decision_result: DecisionResult,
    snapshot: Snapshot,
    controller_context: ControllerContext,
    previous_incident_state: IncidentState,
) -> IncidentLifecycleResult:
    previous_id = previous_incident_state.incident_id
    if previous_id is None and not decision_result.incident_should_open:
        return IncidentLifecycleResult(
            incident_state=previous_incident_state,
            lifecycle_action="stabilize",
            changed=False,
            previous_incident_id=None,
            incident_id=None,
        )

    if previous_id is None and decision_result.incident_should_open:
        incident_id = _new_incident_id()
        state = _build_state(
            incident_id=incident_id,
            opened_at=_now_iso(),
            decision_result=decision_result,
            snapshot=snapshot,
            controller_context=controller_context,
            previous_incident_state=IncidentState(),
        )
        return IncidentLifecycleResult(
            incident_state=state,
            lifecycle_action="open",
            changed=True,
            previous_incident_id=None,
            incident_id=incident_id,
        )

    if previous_id is not None and decision_result.incident_should_close and not decision_result.clear_blocked:
        return IncidentLifecycleResult(
            incident_state=IncidentState(),
            lifecycle_action="close",
            changed=True,
            previous_incident_id=previous_id,
            incident_id=None,
        )

    incident_id = previous_id or _new_incident_id()
    opened_at = previous_incident_state.opened_at or _now_iso()
    updated_state = _build_state(
        incident_id=incident_id,
        opened_at=opened_at,
        decision_result=decision_result,
        snapshot=snapshot,
        controller_context=controller_context,
        previous_incident_state=previous_incident_state,
    )

    next_sources = updated_state.hazard_source_set
    previous_sources = previous_incident_state.hazard_source_set
    if did_escalate(
        previous_state=previous_incident_state.current_state,
        next_state=updated_state.current_state,
        previous_sources=previous_sources,
        next_sources=next_sources,
    ):
        action = "escalate"
    elif is_recovery(
        previous_state=previous_incident_state.current_state,
        next_state=updated_state.current_state,
    ):
        action = "recover"
    else:
        action = "stabilize"

    changed = updated_state != previous_incident_state
    return IncidentLifecycleResult(
        incident_state=updated_state if changed else previous_incident_state,
        lifecycle_action=action,
        changed=changed,
        previous_incident_id=previous_id,
        incident_id=incident_id,
    )
