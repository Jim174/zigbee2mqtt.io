"""Transition/state mutation helpers for fire alarm controller."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def clear_context_on_escalation(ctx: dict[str, Any]) -> bool:
    """Clear escalation-sensitive context fields.

    Returns True when any field was actually changed.
    """
    changed = False

    if ctx.get("acked"):
        ctx["acked"] = False
        changed = True
    if ctx.get("silenced"):
        ctx["silenced"] = False
        changed = True
    if ctx.get("acked_incident_id") is not None:
        ctx["acked_incident_id"] = None
        changed = True
    if ctx.get("silenced_incident_id") is not None:
        ctx["silenced_incident_id"] = None
        changed = True

    return changed


def apply_transition_mutation(
    *,
    current_state: str,
    next_state: str,
    default_escalation_phase_map: dict[str, str],
    fallback_phase: str,
    risk_priority_fn: Callable[[str], int],
) -> dict[str, Any]:
    """Build normalized transition mutation payload (without side effects)."""
    if next_state == current_state:
        return {
            "changed": False,
            "previous_state": current_state,
            "next_state": next_state,
            "escalation_phase": default_escalation_phase_map.get(current_state, fallback_phase),
            "should_clear_on_escalation": False,
            "last_transition_ts": None,
        }

    is_escalation = risk_priority_fn(next_state) > risk_priority_fn(current_state)

    return {
        "changed": True,
        "previous_state": current_state,
        "next_state": next_state,
        "escalation_phase": default_escalation_phase_map.get(next_state, fallback_phase),
        "should_clear_on_escalation": is_escalation,
        "last_transition_ts": datetime.now(timezone.utc),
    }
