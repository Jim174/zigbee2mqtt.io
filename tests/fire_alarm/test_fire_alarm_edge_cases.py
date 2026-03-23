from __future__ import annotations

from typing import Any

from projects.fire_alarm import fire_alarm_constants as c
from projects.fire_alarm.fire_alarm import FireAlarm


class EdgeRecorder:
    def __init__(self) -> None:
        self.logs: list[tuple[str, str]] = []
        self.listen_state_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.listen_event_calls: list[tuple[str, str]] = []
        self.call_service_calls: list[tuple[str, dict[str, Any]]] = []
        self.state_store: dict[str, Any] = {}

    def log(self, message: str, level: str = "INFO") -> None:
        self.logs.append((level, message))

    def get_state(self, entity_id: str) -> Any:
        return self.state_store.get(entity_id)

    def call_service(self, service: str, **data: Any) -> None:
        self.call_service_calls.append((service, data))

    def listen_state(self, callback, entity_id: str, **kwargs: Any) -> None:
        self.listen_state_calls.append((callback.__name__, entity_id, kwargs))

    def listen_event(self, callback, event_name: str) -> None:
        self.listen_event_calls.append((callback.__name__, event_name))



def build_controller(args: dict[str, Any] | None = None, state_store: dict[str, Any] | None = None):
    controller = FireAlarm()
    recorder = EdgeRecorder()
    recorder.state_store.update(state_store or {})

    controller.args = args or {}
    controller.log = recorder.log
    controller.get_state = recorder.get_state
    controller.call_service = recorder.call_service
    controller.listen_state = recorder.listen_state
    controller.listen_event = recorder.listen_event
    return controller, recorder



def test_unavailable_sensor_update_then_recover_then_unavailable_again_tracks_fault_regression():
    controller, recorder = build_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "notify_target": "notify/mobile",
        },
        state_store={"binary_sensor.smoke_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "unknown", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    assert "smoke:binary_sensor.smoke_1" in controller._ctx["active_faults"]
    first_fault_mark = controller._ctx["last_fault_notify_ts_by_key"].copy()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "unknown", "off", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    assert "smoke:binary_sensor.smoke_1" not in controller._ctx["active_faults"]

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "unknown", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    assert "smoke:binary_sensor.smoke_1" in controller._ctx["active_faults"]
    assert len(recorder.call_service_calls) == 1
    assert set(controller._ctx["last_fault_notify_ts_by_key"]) == set(first_fault_mark)



def test_repeated_same_sensor_update_keeps_notify_and_tts_marks_stable_on_noop_path():
    controller, recorder = build_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "beacon_target": "beacon/on",
            "buzzer_target": "buzzer/on",
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
    first_call_count = len(recorder.call_service_calls)

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "on", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )

    assert controller._ctx["last_notify_ts_by_state"][c.STATE_CRITICAL] == first_notify_mark
    assert controller._ctx["last_tts_ts_by_state"][c.STATE_CRITICAL] == first_tts_mark
    assert len(recorder.call_service_calls) == first_call_count



def test_reset_event_is_blocked_while_snapshot_remains_unsafe():
    controller, recorder = build_controller(
        args={"smoke_sensors": ["binary_sensor.smoke_1"]},
        state_store={"binary_sensor.smoke_1": "off"},
    )
    controller.initialize()
    controller._ctx["acked"] = True
    controller._sensor_cache["smoke"]["binary_sensor.smoke_1"] = "on"

    controller._handle_control_event("fire_alarm_control", {"action": "reset"}, {})

    assert controller._ctx["acked"] is True
    assert any(
        level == "WARNING" and message == "reset ignored: normal conditions not met (state=normal)"
        for level, message in recorder.logs
    )



def test_reset_event_after_safe_snapshot_clears_runtime_context():
    controller, recorder = build_controller(
        args={
            "light_target": "light/control",
            "beacon_target": "beacon/control",
            "buzzer_target": "buzzer/control",
        }
    )
    controller.initialize()
    controller._ctx["acked"] = True
    controller._ctx["silenced"] = True
    controller._ctx["manual_override"] = True

    controller._handle_control_event("fire_alarm_control", {"action": "reset"}, {})

    assert controller._ctx["acked"] is False
    assert controller._ctx["silenced"] is False
    assert controller._ctx["manual_override"] is False
    assert controller._ctx["active_faults"] == {}
    assert controller._temperature_tracker.stove_reminder_since_by_entity == {}
    assert [name for name, _ in recorder.call_service_calls] == [
        "light/control",
        "beacon/control",
        "buzzer/control",
    ]



def test_non_numeric_temperature_update_logs_and_does_not_crash():
    controller, recorder = build_controller(
        args={"temperature_sensors": ["sensor.temp_1"]},
        state_store={"sensor.temp_1": "warm"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "sensor.temp_1", "state", "warm", "hot", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )

    assert controller._state == c.STATE_NORMAL
    assert recorder.logs



def test_empty_sensor_groups_do_not_crash_snapshot_building():
    controller, _ = build_controller(args={})
    controller.initialize()

    snapshot = controller._build_snapshot(
        trigger_entity_id="__test__",
        trigger_source="system",
        trigger_event="manual_check",
        old_value=None,
        new_value=None,
    )

    assert snapshot.smoke_active_entities == []
    assert snapshot.gas_active_entities == []
    assert snapshot.summary.smoke_any_alarm is False
    assert snapshot.summary.gas_any_alarm is False



def test_control_event_with_malformed_payload_is_ignored_safely():
    controller, recorder = build_controller()
    controller.initialize()

    controller._handle_control_event("fire_alarm_control", {"action": {"bad": 1}}, {})

    assert any(
        level == "WARNING" and "control event ignored: unsupported action={'bad': 1}" == message
        for level, message in recorder.logs
    )
    assert recorder.call_service_calls == []
