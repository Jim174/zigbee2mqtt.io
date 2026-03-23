from __future__ import annotations

from projects.fire_alarm.decision.models import ControllerContext, DecisionResult
from projects.fire_alarm.entry_action.planner import build_device_action_plan
from projects.fire_alarm.fault.models import FaultState
from projects.fire_alarm.incident.models import IncidentState
from projects.fire_alarm.snapshot.models import (
    OccupancySnapshot,
    ShutdownSnapshot,
    Snapshot,
    SnapshotSummary,
    TemperatureSnapshot,
    TemperatureTrackerState,
)


def _decision_result(*, next_state: str, primary_hazard_source: str | None) -> DecisionResult:
    return DecisionResult(
        current_state="normal",
        next_state=next_state,
        current_phase="observe",
        next_phase=next_state,
        transition_changed=True,
        primary_hazard_source=primary_hazard_source,
        reason_codes=[],
        clear_blocked=False,
        clear_block_reason_code=None,
        incident_should_open=False,
        incident_should_close=False,
        incident_should_escalate=False,
        protective_shutdown_requested=False,
        hard_lockout_requested=False,
        notify_severity=None,
        tts_severity=None,
        log_message=None,
        log_level=None,
    )


def _snapshot(*, valve_confirmed_closed: bool = False, trigger_source: str = "smoke", trigger_event: str = "smoke_update") -> Snapshot:
    return Snapshot(
        trigger_entity_id="binary_sensor.test",
        trigger_source=trigger_source,
        trigger_event=trigger_event,
        old_value="off",
        new_value="on",
        smoke_active_entities=[],
        gas_active_entities=[],
        smoke_unavailable_entities=[],
        gas_unavailable_entities=[],
        temperature=TemperatureSnapshot(
            stove_entities={},
            environment_entities={},
            other_room_entities={},
            stove_max=None,
            environment_max=None,
            other_room_max=None,
            stove_reminder_active=False,
            stove_reminder_entities=[],
            environment_highest_severity=None,
            other_room_highest_severity=None,
            environment_observe_entities=[],
            environment_prealarm_entities=[],
            environment_alarm_entities=[],
            environment_critical_entities=[],
            other_room_observe_entities=[],
            other_room_prealarm_entities=[],
            other_room_alarm_entities=[],
            other_room_critical_entities=[],
            non_numeric_entities=[],
            tracker_state=TemperatureTrackerState(),
        ),
        occupancy=OccupancySnapshot(
            mode=None,
            is_home=None,
            is_sleeping=None,
            occupied_rooms=[],
            primary_zone=None,
            presence_entities={},
        ),
        shutdown=ShutdownSnapshot(
            protective_shutdown_active=False,
            hard_lockout_active=False,
            valve_requested_closed=False,
            valve_confirmed_closed=valve_confirmed_closed,
            exhaust_requested_on=False,
            exhaust_confirmed_on=False,
            clear_blocked_by_shutdown=False,
        ),
        summary=SnapshotSummary(
            smoke_any_alarm=False,
            gas_any_alarm=False,
            environment_highest_severity=None,
            other_room_highest_severity=None,
            stove_reminder_active=False,
            any_unavailable=False,
            fire_monitor_highest_severity=None,
            occupancy_mode=None,
            proposed_clear_is_safe=True,
        ),
    )


def _plan(
    *,
    next_state: str,
    primary_hazard_source: str | None,
    valve_confirmed_closed: bool = False,
    trigger_source: str = "smoke",
    trigger_event: str = "smoke_update",
):
    return build_device_action_plan(
        decision_result=_decision_result(next_state=next_state, primary_hazard_source=primary_hazard_source),
        snapshot=_snapshot(
            valve_confirmed_closed=valve_confirmed_closed,
            trigger_source=trigger_source,
            trigger_event=trigger_event,
        ),
        controller_context=ControllerContext(current_state="normal", current_phase="observe"),
        incident_state=IncidentState(),
        fault_state=FaultState(),
    )


def test_valve_open_feedback_emits_indicator_only():
    plan = _plan(
        next_state="observe",
        primary_hazard_source=None,
        valve_confirmed_closed=False,
        trigger_source="valve",
        trigger_event="valve_open",
    )

    assert [(action.device_role, action.channel, action.effect_key) for action in plan.device_actions] == [
        ("indicator", "light", "valve_open_feedback")
    ]


def test_valve_close_feedback_emits_indicator_only():
    plan = _plan(
        next_state="observe",
        primary_hazard_source=None,
        valve_confirmed_closed=True,
        trigger_source="valve",
        trigger_event="valve_close",
    )

    assert [(action.device_role, action.channel, action.effect_key) for action in plan.device_actions] == [
        ("indicator", "light", "valve_close_feedback")
    ]


def test_observe_emits_indicator_only():
    plan = _plan(next_state="observe", primary_hazard_source="smoke")

    assert [(action.device_role, action.channel, action.effect_key) for action in plan.device_actions] == [
        ("indicator", "light", "observe")
    ]


def test_prealarm_emits_indicator_only():
    plan = _plan(next_state="prealarm", primary_hazard_source="smoke")

    assert [(action.device_role, action.channel, action.effect_key) for action in plan.device_actions] == [
        ("indicator", "light", "prealarm")
    ]


def test_alarm_emits_beacon_only():
    plan = _plan(next_state="alarm", primary_hazard_source="smoke")

    assert [(action.device_role, action.channel, action.effect_key) for action in plan.device_actions] == [
        ("beacon", "beacon", "alarm")
    ]


def test_critical_emits_beacon_and_buzzer_only():
    plan = _plan(next_state="critical", primary_hazard_source="smoke")

    assert [(action.device_role, action.channel, action.effect_key) for action in plan.device_actions] == [
        ("beacon", "beacon", "critical"),
        ("buzzer", "buzzer", None),
    ]
