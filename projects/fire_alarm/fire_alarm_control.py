"""Control-plane context mutation helpers for fire alarm controller."""

from __future__ import annotations

from typing import Any


def normalize_control_action(data: dict[str, Any] | None) -> str:
    """Return normalized action string from control event payload."""
    return str((data or {}).get("action", "")).strip().lower()


def should_allow_reset(*, current_state: str, proposed_state: str, normal_state: str) -> bool:
    """Pure reset gating check based on state and risk proposal."""
    return current_state == normal_state and proposed_state == normal_state


def reset_runtime_context(ctx: dict[str, Any]) -> bool:
    """Reset mutable runtime context fields; return True when active faults were present."""
    ctx["acked"] = False
    ctx["silenced"] = False
    ctx["manual_override"] = False

    had_active_faults = bool(ctx.get("active_faults"))
    ctx["active_faults"] = {}

    ctx["current_incident_id"] = None
    ctx["incident_start_ts"] = None
    ctx["incident_severity"] = None
    ctx["incident_active_sources"] = []
    ctx["acked_incident_id"] = None
    ctx["silenced_incident_id"] = None

    ctx["last_notify_ts_by_state"] = {}
    ctx["last_tts_ts_by_state"] = {}
    ctx["last_fault_notify_ts_by_key"] = {}
    ctx["last_fault_clear_notify_ts_by_key"] = {}
    ctx["active_fault_notified_keys"] = set()
    ctx["cleared_fault_notified_keys"] = set()

    return had_active_faults


def apply_control_action(
    *,
    ctx: dict[str, Any],
    action: str,
    current_state: str,
    can_reset: bool,
    critical_state: str,
) -> dict[str, Any]:
    """Apply one control action mutation and return orchestration hints."""
    result: dict[str, Any] = {
        "applied": True,
        "should_sync_outputs": False,
        "manual_override_log": None,
        "needs_runtime_reset": False,
    }

    if action == "ack":
        ctx["acked"] = True
        ctx["acked_incident_id"] = ctx.get("current_incident_id")
        result["should_sync_outputs"] = True
        return result

    if action == "silence":
        ctx["silenced"] = True
        ctx["silenced_incident_id"] = ctx.get("current_incident_id")
        result["should_sync_outputs"] = True
        return result

    if action == "manual_override_on":
        ctx["manual_override"] = True
        if current_state == critical_state:
            result["manual_override_log"] = {
                "level": "WARNING",
                "message": "manual_override enabled during critical; primary protection remains active",
            }
        else:
            result["manual_override_log"] = {
                "level": "INFO",
                "message": "manual_override enabled",
            }
        return result

    if action == "manual_override_off":
        ctx["manual_override"] = False
        result["manual_override_log"] = {
            "level": "INFO",
            "message": "manual_override disabled",
        }
        return result

    if action == "reset":
        if not can_reset:
            return {
                "applied": False,
                "reason": "reset_not_allowed",
                "should_sync_outputs": False,
                "manual_override_log": None,
                "needs_runtime_reset": False,
            }
        result["needs_runtime_reset"] = True
        result["should_sync_outputs"] = True
        return result

    return {
        "applied": False,
        "reason": "unsupported_action",
        "should_sync_outputs": False,
        "manual_override_log": None,
        "needs_runtime_reset": False,
    }
