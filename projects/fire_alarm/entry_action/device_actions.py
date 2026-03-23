from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..decision.models import ControllerContext, DecisionResult
from ..fault.models import FaultState
from ..incident.models import IncidentState
from ..snapshot.models import Snapshot


@dataclass(frozen=True)
class DeviceAction:
    device_role: str
    channel: str
    action: str
    payload: dict[str, Any]
    effect_key: str | None = None
    requires_confirmation: bool = False
    confirmation_key: str | None = None


@dataclass(frozen=True)
class DeviceActionPlan:
    state: str
    phase: str
    device_actions: list[DeviceAction] = field(default_factory=list)
    shutdown_actions: list[Any] = field(default_factory=list)
    clear_block_active: bool = False
    clear_block_reason_code: str | None = None


def build_device_actions(*, decision_result: DecisionResult, snapshot: Snapshot, controller_context: ControllerContext, incident_state: IncidentState, fault_state: FaultState) -> list[DeviceAction]:
    del controller_context, incident_state, fault_state

    actions: list[DeviceAction] = []
    state = decision_result.next_state
    normal_feedback = decision_result.primary_hazard_source in {None, "fault_only", "stove_reminder"}

    if normal_feedback:
        actions.append(DeviceAction(device_role="indicator", channel="light", action="effect", effect_key="valve_close_feedback" if snapshot.shutdown.valve_confirmed_closed else "valve_open_feedback", payload={"valve_confirmed_closed": snapshot.shutdown.valve_confirmed_closed}))
        return actions

    if state == "observe":
        actions.append(DeviceAction(device_role="indicator", channel="light", action="effect", effect_key="observe", payload={}))
    elif state == "prealarm":
        actions.append(DeviceAction(device_role="indicator", channel="light", action="effect", effect_key="prealarm", payload={}))
    elif state == "alarm":
        actions.append(DeviceAction(device_role="beacon", channel="beacon", action="effect", effect_key="alarm", payload={}))
    elif state == "critical":
        actions.append(DeviceAction(device_role="beacon", channel="beacon", action="effect", effect_key="critical", payload={}))
        actions.append(DeviceAction(device_role="buzzer", channel="buzzer", action="on", payload={"pattern": "critical_buzzer"}))

    return actions
