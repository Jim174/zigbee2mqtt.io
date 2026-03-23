from __future__ import annotations

from projects.fire_alarm import fire_alarm_constants as c
from projects.fire_alarm.fire_alarm_entry_actions import build_entry_action_plan
import projects.fire_alarm.fire_alarm_faults as fire_alarm_faults
import projects.fire_alarm.fire_alarm_notifications as fire_alarm_notifications


def _entry_snapshot(*, source: str = "smoke", state: str | None = None) -> dict:
    trigger = {"entity_id": "binary_sensor.test", "source": source, "event": f"{source}_update"}
    snapshot = {"trigger": trigger}
    if state is not None:
        snapshot["state"] = state
    return snapshot


def test_notify_and_tts_cooldowns_gate_same_state_repeat_updates(monkeypatch):
    times = iter([10.0, 20.0, 25.0, 30.0, 35.0, 50.0, 60.0, 80.0])
    monkeypatch.setattr(fire_alarm_notifications, "monotonic", lambda: next(times))

    ctx = {
        "last_notify_ts_by_state": {},
        "last_tts_ts_by_state": {},
        "acked": False,
        "silenced": False,
        "acked_incident_id": None,
        "silenced_incident_id": None,
        "current_incident_id": None,
    }

    first_plan = build_entry_action_plan(
        state=c.STATE_ALARM,
        risk_snapshot=_entry_snapshot(),
        ctx=ctx,
        notify_cooldown_sec=30,
        tts_cooldown_sec=30,
    )
    assert [cmd["channel"] for cmd in first_plan["commands"]] == ["beacon", "buzzer", "tts", "notify"]

    fire_alarm_notifications.mark_tts_sent(ctx, c.STATE_ALARM)
    fire_alarm_notifications.mark_notify_sent(ctx, c.STATE_ALARM)

    second_plan = build_entry_action_plan(
        state=c.STATE_ALARM,
        risk_snapshot=_entry_snapshot(state=c.STATE_ALARM),
        ctx=ctx,
        notify_cooldown_sec=30,
        tts_cooldown_sec=30,
    )
    assert [cmd["channel"] for cmd in second_plan["commands"]] == ["beacon", "buzzer"]

    third_plan = build_entry_action_plan(
        state=c.STATE_ALARM,
        risk_snapshot=_entry_snapshot(state=c.STATE_ALARM),
        ctx=ctx,
        notify_cooldown_sec=30,
        tts_cooldown_sec=30,
    )
    assert [cmd["channel"] for cmd in third_plan["commands"]] == ["beacon", "buzzer", "notify"]

    fourth_plan = build_entry_action_plan(
        state=c.STATE_ALARM,
        risk_snapshot=_entry_snapshot(state=c.STATE_ALARM),
        ctx=ctx,
        notify_cooldown_sec=30,
        tts_cooldown_sec=30,
    )
    assert [cmd["channel"] for cmd in fourth_plan["commands"]] == ["beacon", "buzzer", "tts", "notify"]


def test_higher_severity_escalation_can_emit_fresh_notify_and_tts_inside_alarm_cooldown(monkeypatch):
    times = iter([100.0, 110.0, 115.0, 120.0])
    monkeypatch.setattr(fire_alarm_notifications, "monotonic", lambda: next(times))

    ctx = {
        "last_notify_ts_by_state": {},
        "last_tts_ts_by_state": {},
        "acked": False,
        "silenced": False,
        "acked_incident_id": None,
        "silenced_incident_id": None,
        "current_incident_id": "inc-1",
    }

    alarm_plan = build_entry_action_plan(
        state=c.STATE_ALARM,
        risk_snapshot=_entry_snapshot(),
        ctx=ctx,
        notify_cooldown_sec=60,
        tts_cooldown_sec=60,
    )
    fire_alarm_notifications.mark_tts_sent(ctx, c.STATE_ALARM)
    fire_alarm_notifications.mark_notify_sent(ctx, c.STATE_ALARM)

    critical_plan = build_entry_action_plan(
        state=c.STATE_CRITICAL,
        risk_snapshot=_entry_snapshot(source="gas"),
        ctx=ctx,
        notify_cooldown_sec=60,
        tts_cooldown_sec=60,
    )

    assert [cmd["channel"] for cmd in alarm_plan["commands"]] == ["beacon", "buzzer", "tts", "notify"]
    assert [cmd["channel"] for cmd in critical_plan["commands"]] == ["beacon", "buzzer", "tts", "notify"]
    assert critical_plan["commands"][2]["payload"]["message"] == "Critical fire emergency"
    assert critical_plan["commands"][3]["payload"]["message"] == "Critical fire emergency"


def test_ack_and_silence_control_sync_snapshots_suppress_notifications():
    silenced_ctx = {
        "last_notify_ts_by_state": {},
        "last_tts_ts_by_state": {},
        "acked": False,
        "silenced": True,
        "acked_incident_id": None,
        "silenced_incident_id": "inc-1",
        "current_incident_id": "inc-1",
    }
    silenced_plan = build_entry_action_plan(
        state=c.STATE_ALARM,
        risk_snapshot=_entry_snapshot(source="control"),
        ctx=silenced_ctx,
        notify_cooldown_sec=0,
        tts_cooldown_sec=0,
    )
    assert [cmd["channel"] for cmd in silenced_plan["commands"]] == ["beacon", "buzzer"]

    acked_ctx = {
        "last_notify_ts_by_state": {},
        "last_tts_ts_by_state": {},
        "acked": True,
        "silenced": False,
        "acked_incident_id": "inc-2",
        "silenced_incident_id": None,
        "current_incident_id": "inc-2",
    }
    acked_sync_plan = build_entry_action_plan(
        state=c.STATE_PREALARM,
        risk_snapshot={"trigger": {"entity_id": "__control__", "source": "control", "event": "ack"}},
        ctx=acked_ctx,
        notify_cooldown_sec=0,
        tts_cooldown_sec=0,
    )
    assert [cmd["channel"] for cmd in acked_sync_plan["commands"]] == ["light"]


def test_controller_noop_same_state_update_preserves_notify_and_tts_marks(build_test_controller):
    controller, recorder = build_test_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "beacon_target": "beacon/control",
            "buzzer_target": "buzzer/control",
            "notify_target": "notify/mobile",
            "tts_target": "tts/speaker",
        },
        state_store={"binary_sensor.smoke_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    first_notify_mark = controller._ctx["last_notify_ts_by_state"][c.STATE_CRITICAL]
    first_tts_mark = controller._ctx["last_tts_ts_by_state"][c.STATE_CRITICAL]
    first_dispatches = list(recorder.call_service_calls)

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "on", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )

    assert controller._ctx["last_notify_ts_by_state"][c.STATE_CRITICAL] == first_notify_mark
    assert controller._ctx["last_tts_ts_by_state"][c.STATE_CRITICAL] == first_tts_mark
    assert recorder.call_service_calls == first_dispatches


def test_fault_clear_notification_dispatches_when_enabled(monkeypatch, build_test_controller):
    times = iter([1.0, 2.0])
    monkeypatch.setattr(fire_alarm_faults, "monotonic", lambda: next(times))

    controller, recorder = build_test_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "notify_target": "notify/mobile",
            "fault_clear_notify_enabled": True,
            "fault_notify_cooldown_sec": 0,
        },
        state_store={"binary_sensor.smoke_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "unknown", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "unknown", "off", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )

    assert [name for name, _ in recorder.call_service_calls] == ["notify/mobile", "notify/mobile"]
    assert "fault cleared" in recorder.call_service_calls[1][1]["message"]
    assert controller._ctx["last_fault_clear_notify_ts_by_key"]
    assert any("binary_sensor.smoke_1" in key for key in controller._ctx["last_fault_clear_notify_ts_by_key"])
