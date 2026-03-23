"""Control event flow helpers for fire alarm controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ControlEventFlowDeps:
    """Dependency bundle for control event lock-flow orchestration."""

    can_reset_context: Callable[[], bool]
    apply_control_action: Callable[..., dict[str, Any]]
    reset_runtime_context: Callable[[], bool]


def run_control_event_flow(
    *,
    ctx: dict[str, Any],
    action: str,
    current_state: str,
    critical_state: str,
    deps: ControlEventFlowDeps,
) -> dict[str, Any]:
    """Run control event flow and return orchestration-ready result."""
    can_reset = action != "reset" or deps.can_reset_context()
    control_result = deps.apply_control_action(
        ctx=ctx,
        action=action,
        current_state=current_state,
        can_reset=can_reset,
        critical_state=critical_state,
    )

    if not control_result.get("applied", False):
        reason = control_result.get("reason")
        if reason == "reset_not_allowed":
            return {
                "applied": False,
                "ignored_log": {
                    "message": "reset ignored: normal conditions not met (state=%s)" % current_state,
                    "level": "WARNING",
                },
                "manual_override_log": None,
                "should_sync_outputs": False,
                "had_active_faults": False,
            }

        return {
            "applied": False,
            "ignored_log": {
                "message": "control event ignored: unsupported action=%s" % action,
                "level": "WARNING",
            },
            "manual_override_log": None,
            "should_sync_outputs": False,
            "had_active_faults": False,
        }

    had_active_faults = False
    if control_result.get("needs_runtime_reset", False):
        had_active_faults = deps.reset_runtime_context()

    return {
        "applied": True,
        "ignored_log": None,
        "manual_override_log": control_result.get("manual_override_log"),
        "should_sync_outputs": bool(control_result.get("should_sync_outputs", False)),
        "had_active_faults": had_active_faults,
    }
