from __future__ import annotations

from datetime import datetime, timedelta, timezone

from projects.fire_alarm import fire_alarm_constants as c
from projects.fire_alarm.fire_alarm_decision_flow import run_decision_flow
from projects.fire_alarm.fire_alarm_rules import risk_priority


def test_run_decision_flow_returns_normal_when_all_sources_clear():
    result = run_decision_flow(
        current_state=c.STATE_OBSERVE,
        risk_snapshot={"summary": {"smoke": {}, "gas": {}, "temperature": {}}},
        active_faults={},
        last_transition_ts=datetime.now(timezone.utc) - timedelta(seconds=120),
        clear_hold_seconds=30,
        risk_priority_fn=risk_priority,
    )

    assert result.next_state == c.STATE_NORMAL
    assert result.log_message is None
    assert result.log_level is None


def test_run_decision_flow_escalates_to_alarm_on_smoke_alarm():
    result = run_decision_flow(
        current_state=c.STATE_NORMAL,
        risk_snapshot={"summary": {"smoke": {"any_alarm": True}, "gas": {}, "temperature": {}}},
        active_faults={},
        last_transition_ts=None,
        clear_hold_seconds=30,
        risk_priority_fn=risk_priority,
    )

    assert result.next_state == c.STATE_ALARM
    assert result.log_message is None


def test_run_decision_flow_escalates_to_critical_on_smoke_plus_temperature_alarm():
    result = run_decision_flow(
        current_state=c.STATE_ALARM,
        risk_snapshot={
            "summary": {
                "smoke": {"any_alarm": True},
                "gas": {"any_alarm": False},
                "temperature": {"any_alarm": True, "any_warning": True},
            }
        },
        active_faults={},
        last_transition_ts=None,
        clear_hold_seconds=30,
        risk_priority_fn=risk_priority,
    )

    assert result.next_state == c.STATE_CRITICAL
    assert result.log_message is None


def test_run_decision_flow_keeps_prealarm_for_temperature_only_alarm():
    result = run_decision_flow(
        current_state=c.STATE_OBSERVE,
        risk_snapshot={
            "summary": {
                "smoke": {"any_alarm": False},
                "gas": {"any_alarm": False},
                "temperature": {"any_alarm": True, "any_warning": True},
            }
        },
        active_faults={},
        last_transition_ts=None,
        clear_hold_seconds=30,
        risk_priority_fn=risk_priority,
    )

    assert result.next_state == c.STATE_PREALARM
    assert result.log_message is None


def test_run_decision_flow_blocks_clear_to_normal_when_smoke_fault_active():
    result = run_decision_flow(
        current_state=c.STATE_ALARM,
        risk_snapshot={"summary": {"smoke": {}, "gas": {}, "temperature": {}}},
        active_faults={"smoke:s1": {"source": "smoke", "entity_id": "binary_sensor.s1"}},
        last_transition_ts=datetime.now(timezone.utc) - timedelta(seconds=120),
        clear_hold_seconds=30,
        risk_priority_fn=risk_priority,
    )

    assert result.next_state == c.STATE_ALARM
    assert result.log_level == "WARNING"
    assert "proposed clear blocked by active fault" in str(result.log_message)


def test_run_decision_flow_holds_recent_downgrade_with_debug_log():
    result = run_decision_flow(
        current_state=c.STATE_CRITICAL,
        risk_snapshot={"summary": {"smoke": {}, "gas": {}, "temperature": {}}},
        active_faults={},
        last_transition_ts=datetime.now(timezone.utc) - timedelta(seconds=5),
        clear_hold_seconds=30,
        risk_priority_fn=risk_priority,
    )

    assert result.next_state == c.STATE_CRITICAL
    assert result.log_level == "DEBUG"
    assert "anti-flap downgrade hold" in str(result.log_message)
