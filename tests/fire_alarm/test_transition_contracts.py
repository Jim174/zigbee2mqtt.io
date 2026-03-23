from __future__ import annotations

from datetime import datetime, timedelta, timezone

from projects.fire_alarm import fire_alarm_constants as c
from projects.fire_alarm.fire_alarm_decision_flow import run_decision_flow
from projects.fire_alarm.fire_alarm_rules import risk_priority
from projects.fire_alarm.fire_alarm_transition import apply_transition_mutation


def _summary(*, smoke: bool = False, gas: bool = False, temp_warning: bool = False, temp_alarm: bool = False) -> dict:
    return {
        "smoke": {"any_alarm": smoke},
        "gas": {"any_alarm": gas},
        "temperature": {"any_warning": temp_warning, "any_alarm": temp_alarm},
    }


def test_apply_transition_mutation_contracts_cover_primary_edges():
    cases = [
        (c.STATE_NORMAL, c.STATE_OBSERVE, c.PHASE_OBSERVE, True),
        (c.STATE_OBSERVE, c.STATE_PREALARM, c.PHASE_VERIFY, True),
        (c.STATE_PREALARM, c.STATE_ALARM, c.PHASE_ALERT, True),
        (c.STATE_ALARM, c.STATE_CRITICAL, c.PHASE_EMERGENCY, True),
    ]

    for current_state, next_state, phase, should_clear in cases:
        result = apply_transition_mutation(
            current_state=current_state,
            next_state=next_state,
            default_escalation_phase_map=c.DEFAULT_ESCALATION_PHASE_MAP,
            fallback_phase=c.PHASE_OBSERVE,
            risk_priority_fn=risk_priority,
        )

        assert result["changed"] is True
        assert result["next_state"] == next_state
        assert result["escalation_phase"] == phase
        assert result["should_clear_on_escalation"] is should_clear
        assert result["last_transition_ts"] is not None


def test_apply_transition_mutation_same_state_is_noop():
    result = apply_transition_mutation(
        current_state=c.STATE_ALARM,
        next_state=c.STATE_ALARM,
        default_escalation_phase_map=c.DEFAULT_ESCALATION_PHASE_MAP,
        fallback_phase=c.PHASE_OBSERVE,
        risk_priority_fn=risk_priority,
    )

    assert result == {
        "changed": False,
        "previous_state": c.STATE_ALARM,
        "next_state": c.STATE_ALARM,
        "escalation_phase": c.PHASE_ALERT,
        "should_clear_on_escalation": False,
        "last_transition_ts": None,
    }


def test_run_decision_flow_downgrade_hold_keeps_current_state():
    risk_snapshot = {"summary": _summary()}

    result = run_decision_flow(
        current_state=c.STATE_ALARM,
        risk_snapshot=risk_snapshot,
        active_faults={},
        last_transition_ts=datetime.now(timezone.utc) - timedelta(seconds=5),
        clear_hold_seconds=30,
        risk_priority_fn=risk_priority,
    )

    assert result.next_state == c.STATE_ALARM
    assert result.log_level == "DEBUG"
    assert "anti-flap downgrade hold" in str(result.log_message)
