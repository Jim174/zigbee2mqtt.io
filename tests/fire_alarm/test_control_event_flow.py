from __future__ import annotations

from projects.fire_alarm.fire_alarm_control import apply_control_action
from projects.fire_alarm.fire_alarm_control_event_flow import ControlEventFlowDeps, run_control_event_flow


def _base_ctx() -> dict:
    return {
        "acked": False,
        "silenced": False,
        "manual_override": False,
        "current_incident_id": "inc-1",
        "acked_incident_id": None,
        "silenced_incident_id": None,
    }


def test_run_control_event_flow_ack_sets_incident_binding_and_syncs_output():
    ctx = _base_ctx()
    deps = ControlEventFlowDeps(
        can_reset_context=lambda: False,
        apply_control_action=apply_control_action,
        reset_runtime_context=lambda: False,
    )

    result = run_control_event_flow(
        ctx=ctx,
        action="ack",
        current_state="alarm",
        critical_state="critical",
        deps=deps,
    )

    assert result["applied"] is True
    assert result["should_sync_outputs"] is True
    assert ctx["acked"] is True
    assert ctx["acked_incident_id"] == "inc-1"


def test_run_control_event_flow_reset_not_allowed_returns_warning_log():
    ctx = _base_ctx()
    reset_called = False

    def reset_runtime_context() -> bool:
        nonlocal reset_called
        reset_called = True
        return False

    deps = ControlEventFlowDeps(
        can_reset_context=lambda: False,
        apply_control_action=apply_control_action,
        reset_runtime_context=reset_runtime_context,
    )

    result = run_control_event_flow(
        ctx=ctx,
        action="reset",
        current_state="alarm",
        critical_state="critical",
        deps=deps,
    )

    assert result["applied"] is False
    assert result["ignored_log"]["level"] == "WARNING"
    assert "reset ignored" in result["ignored_log"]["message"]
    assert reset_called is False


def test_run_control_event_flow_reset_allowed_runs_runtime_reset_and_reports_faults():
    ctx = _base_ctx()
    reset_called = False

    def reset_runtime_context() -> bool:
        nonlocal reset_called
        reset_called = True
        return True

    deps = ControlEventFlowDeps(
        can_reset_context=lambda: True,
        apply_control_action=apply_control_action,
        reset_runtime_context=reset_runtime_context,
    )

    result = run_control_event_flow(
        ctx=ctx,
        action="reset",
        current_state="normal",
        critical_state="critical",
        deps=deps,
    )

    assert result["applied"] is True
    assert result["had_active_faults"] is True
    assert result["should_sync_outputs"] is True
    assert reset_called is True


def test_run_control_event_flow_manual_override_on_critical_preserves_warning_log():
    ctx = _base_ctx()
    deps = ControlEventFlowDeps(
        can_reset_context=lambda: False,
        apply_control_action=apply_control_action,
        reset_runtime_context=lambda: False,
    )

    result = run_control_event_flow(
        ctx=ctx,
        action="manual_override_on",
        current_state="critical",
        critical_state="critical",
        deps=deps,
    )

    assert result["applied"] is True
    assert result["manual_override_log"] == {
        "level": "WARNING",
        "message": "manual_override enabled during critical; primary protection remains active",
    }
    assert ctx["manual_override"] is True
