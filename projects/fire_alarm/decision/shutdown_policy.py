from __future__ import annotations

from ..snapshot.models import Snapshot
from .models import FaultState, IncidentState
from .occupancy_policy import normalize_occupancy_mode


def has_explicit_high_risk_policy(
    *,
    snapshot: Snapshot,
    incident_state: IncidentState,
    fault_state: FaultState,
) -> bool:
    del fault_state
    return bool(snapshot.shutdown.hard_lockout_active or incident_state.hard_lockout_active)


def should_request_hard_lockout(
    *,
    snapshot: Snapshot,
    incident_state: IncidentState,
    fault_state: FaultState,
) -> bool:
    if snapshot.summary.smoke_any_alarm:
        return True
    if snapshot.summary.gas_any_alarm:
        return True
    return has_explicit_high_risk_policy(
        snapshot=snapshot,
        incident_state=incident_state,
        fault_state=fault_state,
    )


def should_request_protective_shutdown(
    *,
    snapshot: Snapshot,
    proposed_state: str,
    hard_lockout_requested: bool,
) -> bool:
    occupancy_mode = normalize_occupancy_mode(snapshot.occupancy)
    temperature_driven_alarm = (
        proposed_state == "alarm"
        and not snapshot.summary.smoke_any_alarm
        and not snapshot.summary.gas_any_alarm
    )
    return (
        occupancy_mode == "unoccupied"
        and temperature_driven_alarm
        and not hard_lockout_requested
        and proposed_state != "critical"
    )
