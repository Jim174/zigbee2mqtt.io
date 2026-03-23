from __future__ import annotations

from ..decision.models import ControllerContext, DecisionResult
from ..fault.blocking import clear_block_reason_codes, is_clear_blocked
from ..fault.models import FaultState
from ..incident.models import IncidentState
from ..snapshot.models import Snapshot
from .device_actions import DeviceActionPlan, build_device_actions
from .shutdown_actions import build_shutdown_actions


def build_device_action_plan(
    *,
    decision_result: DecisionResult,
    snapshot: Snapshot,
    controller_context: ControllerContext,
    incident_state: IncidentState,
    fault_state: FaultState,
) -> DeviceActionPlan:
    clear_block_active = decision_result.clear_blocked or is_clear_blocked(fault_state)
    clear_block_reason_code = decision_result.clear_block_reason_code
    if clear_block_reason_code is None and clear_block_active:
        reason_codes = clear_block_reason_codes(fault_state)
        clear_block_reason_code = reason_codes[0] if reason_codes else None

    device_actions = build_device_actions(
        decision_result=decision_result,
        snapshot=snapshot,
        controller_context=controller_context,
        incident_state=incident_state,
        fault_state=fault_state,
    )
    shutdown_actions = build_shutdown_actions(
        decision_result=decision_result,
        snapshot=snapshot,
        incident_state=incident_state,
        fault_state=fault_state,
    )

    return DeviceActionPlan(
        state=decision_result.next_state,
        phase=decision_result.next_phase,
        device_actions=device_actions,
        shutdown_actions=shutdown_actions,
        clear_block_active=clear_block_active,
        clear_block_reason_code=clear_block_reason_code,
    )
