"""Incident orchestration helpers for fire alarm controller."""

from __future__ import annotations

from typing import Any, Callable


def handle_incident_refresh(
    *,
    ctx: dict[str, Any],
    current_state: str,
    next_state: str,
    risk_snapshot: dict[str, Any],
    refresh_incident_if_needed_fn: Callable[..., dict[str, Any] | None],
    is_alarm_state_fn: Callable[[str], bool],
) -> dict[str, Any]:
    """Run same-state incident refresh flow and return log-ready payload."""
    result = refresh_incident_if_needed_fn(
        ctx=ctx,
        current_state=current_state,
        next_state=next_state,
        risk_snapshot=risk_snapshot,
        is_alarm_state=is_alarm_state_fn,
    )
    if not result:
        return {
            "changed": False,
            "incident_action": None,
            "log_message": None,
            "log_level": None,
            "incident_id": None,
            "severity": None,
            "sources": None,
        }

    if result.get("changed", False):
        return {
            "changed": True,
            "incident_action": "refreshed",
            "log_message": "incident refreshed in same state: id=%s severity=%s sources=%s"
            % (result.get("incident_id"), result.get("severity"), result.get("sources")),
            "log_level": "DEBUG",
            "incident_id": result.get("incident_id"),
            "severity": result.get("severity"),
            "sources": result.get("sources"),
        }

    return {
        "changed": False,
        "incident_action": None,
        "log_message": None,
        "log_level": None,
        "incident_id": result.get("incident_id"),
        "severity": result.get("severity"),
        "sources": result.get("sources"),
    }


def handle_incident_transition(
    *,
    ctx: dict[str, Any],
    current_state: str,
    next_state: str,
    risk_snapshot: dict[str, Any],
    update_incident_on_transition_fn: Callable[..., dict[str, Any] | None],
    is_alarm_state_fn: Callable[[str], bool],
) -> dict[str, Any]:
    """Run transition incident flow and return log-ready payload."""
    action = update_incident_on_transition_fn(
        ctx=ctx,
        current_state=current_state,
        next_state=next_state,
        risk_snapshot=risk_snapshot,
        is_alarm_state=is_alarm_state_fn,
    )

    if action and action.get("action") == "opened":
        return {
            "changed": True,
            "incident_action": "opened",
            "log_message": "incident opened: id=%s severity=%s sources=%s"
            % (action.get("incident_id"), next_state, ctx.get("incident_active_sources", [])),
            "log_level": "INFO",
            "incident_id": action.get("incident_id"),
            "severity": next_state,
            "sources": list(ctx.get("incident_active_sources", [])),
        }

    if action and action.get("action") == "closed":
        return {
            "changed": True,
            "incident_action": "closed",
            "log_message": "incident closed: id=%s" % action.get("incident_id"),
            "log_level": "INFO",
            "incident_id": action.get("incident_id"),
            "severity": None,
            "sources": None,
        }

    return {
        "changed": False,
        "incident_action": None,
        "log_message": None,
        "log_level": None,
        "incident_id": None,
        "severity": None,
        "sources": None,
    }
