"""Transition orchestration helpers for fire alarm controller."""

from __future__ import annotations

from typing import Any, Callable

from .fire_alarm_incident import (
    refresh_incident_if_needed,
    update_incident_on_transition,
)
from .fire_alarm_decision import is_alarm_state
from .fire_alarm_incident_flow import (
    handle_incident_refresh,
    handle_incident_transition,
)


def handle_transition_incident_flow(
    *,
    transition_changed: bool,
    ctx: dict[str, Any],
    current_state: str,
    next_state: str,
    risk_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Run incident flow for transition unchanged/changed paths with unified result shape."""
    if not transition_changed:
        incident_refresh = handle_incident_refresh(
            ctx=ctx,
            current_state=current_state,
            next_state=next_state,
            risk_snapshot=risk_snapshot,
            refresh_incident_if_needed_fn=refresh_incident_if_needed,
            is_alarm_state_fn=is_alarm_state,
        )
        return {
            "changed": bool(incident_refresh.get("changed", False)),
            "log_message": incident_refresh.get("log_message"),
            "log_level": incident_refresh.get("log_level") or "DEBUG",
        }

    incident_transition = handle_incident_transition(
        ctx=ctx,
        current_state=current_state,
        next_state=next_state,
        risk_snapshot=risk_snapshot,
        update_incident_on_transition_fn=update_incident_on_transition,
        is_alarm_state_fn=is_alarm_state,
    )
    return {
        "changed": True,
        "log_message": incident_transition.get("log_message"),
        "log_level": incident_transition.get("log_level") or "INFO",
    }


def run_transition_flow(
    *,
    transition_changed: bool,
    ctx: dict[str, Any],
    current_state: str,
    next_state: str,
    risk_snapshot: dict[str, Any],
    log: Callable[[str, str], None],
) -> bool:
    """Run transition incident flow and emit its log message when present."""
    flow_result = handle_transition_incident_flow(
        transition_changed=transition_changed,
        ctx=ctx,
        current_state=current_state,
        next_state=next_state,
        risk_snapshot=risk_snapshot,
    )

    message = flow_result.get("log_message")
    if message:
        log(str(message), str(flow_result.get("log_level") or ("INFO" if transition_changed else "DEBUG")))

    return bool(flow_result.get("changed", False))
