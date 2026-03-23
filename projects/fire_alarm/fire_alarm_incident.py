"""Incident lifecycle helpers for fire alarm controller."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def incident_active_sources(risk_snapshot: dict[str, Any]) -> list[str]:
    summary = risk_snapshot.get("summary", {})
    active_sources: list[str] = []
    if summary.get("smoke", {}).get("any_alarm"):
        active_sources.append("smoke")
    if summary.get("gas", {}).get("any_alarm"):
        active_sources.append("gas")
    temp_summary = summary.get("temperature", {})
    if temp_summary.get("any_alarm"):
        active_sources.append("temperature_alarm")
    elif temp_summary.get("any_warning"):
        active_sources.append("temperature_warning")
    return active_sources


def open_new_incident(ctx: dict[str, Any], state: str, risk_snapshot: dict[str, Any]) -> str:
    incident_id = "inc-%d" % int(datetime.now(timezone.utc).timestamp() * 1000)
    ctx["current_incident_id"] = incident_id
    ctx["incident_start_ts"] = datetime.now(timezone.utc).isoformat()
    ctx["incident_severity"] = state
    ctx["incident_active_sources"] = incident_active_sources(risk_snapshot)
    ctx["acked_incident_id"] = None
    ctx["silenced_incident_id"] = None
    return incident_id


def update_incident_on_transition(
    *,
    ctx: dict[str, Any],
    current_state: str,
    next_state: str,
    risk_snapshot: dict[str, Any],
    is_alarm_state: Callable[[str], bool],
) -> dict[str, Any] | None:
    if is_alarm_state(next_state) and not is_alarm_state(current_state):
        opened_id = open_new_incident(ctx, next_state, risk_snapshot)
        return {"action": "opened", "incident_id": opened_id}

    if is_alarm_state(next_state) and is_alarm_state(current_state):
        ctx["incident_severity"] = next_state
        ctx["incident_active_sources"] = incident_active_sources(risk_snapshot)
        return {"action": "updated"}

    if next_state == "normal" and ctx.get("current_incident_id"):
        closed_id = ctx.get("current_incident_id")
        ctx["current_incident_id"] = None
        ctx["incident_start_ts"] = None
        ctx["incident_severity"] = None
        ctx["incident_active_sources"] = []
        ctx["acked_incident_id"] = None
        ctx["silenced_incident_id"] = None
        return {"action": "closed", "incident_id": closed_id}

    return None


def refresh_incident_if_needed(
    *,
    ctx: dict[str, Any],
    current_state: str,
    next_state: str,
    risk_snapshot: dict[str, Any],
    is_alarm_state: Callable[[str], bool],
) -> dict[str, Any] | None:
    if current_state != next_state:
        return None
    if not is_alarm_state(current_state):
        return None

    incident_id = ctx.get("current_incident_id")
    if not incident_id:
        return None

    active_sources = incident_active_sources(risk_snapshot)
    previous_severity = ctx.get("incident_severity")
    previous_sources = ctx.get("incident_active_sources", [])

    ctx["incident_severity"] = next_state
    ctx["incident_active_sources"] = active_sources

    return {
        "incident_id": incident_id,
        "severity": next_state,
        "sources": active_sources,
        "changed": previous_severity != next_state or previous_sources != active_sources,
    }


def incident_matches_silence(ctx: dict[str, Any]) -> bool:
    return (
        ctx.get("silenced", False)
        and ctx.get("silenced_incident_id")
        and ctx.get("silenced_incident_id") == ctx.get("current_incident_id")
    )


def incident_matches_ack(ctx: dict[str, Any]) -> bool:
    return (
        ctx.get("acked", False)
        and ctx.get("acked_incident_id")
        and ctx.get("acked_incident_id") == ctx.get("current_incident_id")
    )
