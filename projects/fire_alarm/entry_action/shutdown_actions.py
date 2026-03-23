from __future__ import annotations

from dataclasses import dataclass

from ..decision.models import DecisionResult
from ..fault.models import FaultState
from ..incident.models import IncidentState
from ..snapshot.models import Snapshot


@dataclass(frozen=True)
class ShutdownAction:
    device: str
    requested_state: str
    confirmation_required: bool = False
    confirmation_key: str | None = None
    confirmation_timeout_sec: int | None = None
    failure_blocks_clear: bool = False


def _confirmation_key(*, incident_id: str | None, device: str, requested_state: str) -> str:
    incident_fragment = incident_id or "no_incident"
    return f"{device}:{requested_state}:{incident_fragment}"


def build_shutdown_actions(
    *,
    decision_result: DecisionResult,
    snapshot: Snapshot,
    incident_state: IncidentState,
    fault_state: FaultState,
) -> list[ShutdownAction]:
    del fault_state
    actions: list[ShutdownAction] = []

    protective_active = (
        decision_result.protective_shutdown_requested or incident_state.protective_shutdown_active
    )
    hard_lockout_active = decision_result.hard_lockout_requested or incident_state.hard_lockout_active

    if not protective_active and not hard_lockout_active:
        return actions

    confirmation_key = _confirmation_key(
        incident_id=incident_state.incident_id,
        device="valve",
        requested_state="closed",
    )
    actions.append(
        ShutdownAction(
            device="valve",
            requested_state="closed",
            confirmation_required=True,
            confirmation_key=confirmation_key,
            confirmation_timeout_sec=30,
            failure_blocks_clear=True,
        )
    )
    actions.append(
        ShutdownAction(
            device="exhaust",
            requested_state="on",
            confirmation_required=False,
            confirmation_key=None,
            confirmation_timeout_sec=None,
            failure_blocks_clear=False,
        )
    )
    actions.append(
        ShutdownAction(
            device="hazardous_equipment",
            requested_state="disabled",
            confirmation_required=False,
            confirmation_key=None,
            confirmation_timeout_sec=None,
            failure_blocks_clear=False,
        )
    )

    if hard_lockout_active and snapshot.shutdown.valve_confirmed_closed:
        actions.append(
            ShutdownAction(
                device="valve_reopen",
                requested_state="blocked",
                confirmation_required=False,
                confirmation_key=None,
                confirmation_timeout_sec=None,
                failure_blocks_clear=False,
            )
        )

    return actions
