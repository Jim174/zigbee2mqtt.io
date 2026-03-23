from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IncidentState:
    incident_id: str | None = None
    opened_at: str | None = None
    current_state: str | None = None
    current_phase: str | None = None
    highest_state: str | None = None
    primary_hazard_source: str | None = None
    hazard_source_set: list[str] = field(default_factory=list)
    smoke_involved: bool = False
    gas_involved: bool = False
    environment_fire_involved: bool = False
    other_room_fire_involved: bool = False
    protective_shutdown_active: bool = False
    hard_lockout_active: bool = False
    acked: bool = False
    acked_incident_id: str | None = None
    silenced: bool = False
    silenced_incident_id: str | None = None
    clear_block_active: bool = False
    clear_block_reason_code: str | None = None


@dataclass(frozen=True)
class IncidentLifecycleResult:
    incident_state: IncidentState
    lifecycle_action: str
    changed: bool
    previous_incident_id: str | None = None
    incident_id: str | None = None


__all__ = ["IncidentLifecycleResult", "IncidentState"]
