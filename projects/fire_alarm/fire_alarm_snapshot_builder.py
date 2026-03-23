"""Snapshot payload assembly helpers for fire alarm controller."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_snapshot_context_block(ctx: dict[str, Any]) -> dict[str, Any]:
    """Build context block for risk snapshot payload."""
    return {
        "acked": ctx["acked"],
        "silenced": ctx["silenced"],
        "manual_override": ctx["manual_override"],
        "active_faults": list(ctx["active_faults"].values()),
        "current_incident_id": ctx["current_incident_id"],
        "incident_start_ts": ctx["incident_start_ts"],
        "incident_severity": ctx["incident_severity"],
        "incident_active_sources": list(ctx["incident_active_sources"]),
        "acked_incident_id": ctx["acked_incident_id"],
        "silenced_incident_id": ctx["silenced_incident_id"],
    }


def build_snapshot_trigger_block(
    *,
    trigger_entity: str,
    source_name: str,
    event_name: str,
    old_value: Any,
    new_value: Any,
) -> dict[str, Any]:
    """Build trigger block for risk snapshot payload."""
    return {
        "entity_id": trigger_entity,
        "source": source_name,
        "event": event_name,
        "old": old_value,
        "new": new_value,
    }


def build_risk_snapshot_payload(
    *,
    state: str,
    phase: str,
    ctx: dict[str, Any],
    trigger_entity: str,
    source_name: str,
    event_name: str,
    old_value: Any,
    new_value: Any,
    smoke_states: dict[str, Any],
    gas_states: dict[str, Any],
    temperature_states: dict[str, Any],
    smoke_summary: dict[str, Any],
    gas_summary: dict[str, Any],
    temperature_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build complete risk snapshot payload dictionary."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "phase": phase,
        "context": build_snapshot_context_block(ctx),
        "trigger": build_snapshot_trigger_block(
            trigger_entity=trigger_entity,
            source_name=source_name,
            event_name=event_name,
            old_value=old_value,
            new_value=new_value,
        ),
        "sensors": {
            "smoke": smoke_states,
            "gas": gas_states,
            "temperature": temperature_states,
        },
        "summary": {
            "smoke": smoke_summary,
            "gas": gas_summary,
            "temperature": temperature_summary,
        },
    }


def iter_non_numeric_temperature_log_lines(
    entries: list[tuple[str, Any]],
) -> list[str]:
    """Build debug log lines for non-numeric temperature entries."""
    return [
        "temperature non-numeric value ignored: entity=%s value=%s" % (entity_id, raw_value)
        for entity_id, raw_value in entries
    ]
