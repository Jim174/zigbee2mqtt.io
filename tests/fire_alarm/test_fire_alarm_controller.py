from __future__ import annotations

from typing import Any

from projects.fire_alarm import fire_alarm_constants as c
from projects.fire_alarm.fire_alarm import FireAlarm


class Recorder:
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
    recorder = Recorder()
    recorder.state_store.update(state_store or {})

    controller.args = args or {}
    controller.log = recorder.log
    controller.get_state = recorder.get_state
    controller.call_service = recorder.call_service
    controller.listen_state = recorder.listen_state
    controller.listen_event = recorder.listen_event
    return controller, recorder


def test_initialize_registers_sensor_and_control_listeners():
    controller, recorder = build_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "gas_sensors": ["binary_sensor.gas_1"],
            "temperature_sensors": ["sensor.temp_1"],
        },
        state_store={
            "binary_sensor.smoke_1": "off",
            "binary_sensor.gas_1": "off",
            "sensor.temp_1": "23",
        },
    )

    controller.initialize()

    assert controller._state == c.STATE_NORMAL
    assert controller._escalation_phase == c.PHASE_OBSERVE
    assert controller._sensor_cache["smoke"]["binary_sensor.smoke_1"] == "off"
    assert len(recorder.listen_state_calls) == 3
    assert recorder.listen_event_calls == [("_handle_control_event", "fire_alarm_control")]
    assert any("fire_alarm initialized" in message for _, message in recorder.logs)


def test_initialize_invalid_initial_state_falls_back_to_normal():
    controller, recorder = build_controller(args={"initial_state": "bad_state"})

    controller.initialize()

    assert controller._state == c.STATE_NORMAL
    assert any(
        level == "WARNING" and "invalid initial_state=bad_state, fallback to normal" in message
        for level, message in recorder.logs
    )


def test_handle_sensor_update_short_circuits_when_state_is_disabled():
    controller, recorder = build_controller(
        args={
            "initial_state": c.STATE_DISABLED,
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "notify_target": "notify/mobile",
        },
        state_store={"binary_sensor.smoke_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1",
        "state",
        "off",
        "on",
        {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE},
    )

    assert controller._state == c.STATE_DISABLED
    assert recorder.call_service_calls == []
    assert any(
        level == "DEBUG" and "state is disabled, ignore sensor update" in message
        for level, message in recorder.logs
    )


def test_handle_sensor_update_triggers_alarm_transition_and_entry_actions():
    controller, recorder = build_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "beacon_target": "beacon/turn_on",
            "buzzer_target": "buzzer/turn_on",
            "tts_target": "tts/speak",
            "notify_target": "notify/mobile",
        },
        state_store={"binary_sensor.smoke_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1",
        "state",
        "off",
        "on",
        {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE},
    )

    assert controller._state == c.STATE_CRITICAL
    assert controller._escalation_phase == c.PHASE_EMERGENCY
    service_names = [name for name, _ in recorder.call_service_calls]
    assert service_names == [
        "beacon/turn_on",
        "buzzer/turn_on",
        "notify/mobile",
        "tts/speak",
        "notify/mobile",
        "tts/speak",
    ]
    assert recorder.call_service_calls[0][1]["action"] == "effect"
    assert recorder.call_service_calls[2][1]["message"] == "Fire alarm triggered"
    assert recorder.call_service_calls[4][1]["message"] == "Hazard lockout active"
    assert any(
        level == "INFO" and "state transition: normal -> critical" in message
        for level, message in recorder.logs
    )


def test_handle_control_event_missing_action_is_ignored():
    controller, recorder = build_controller()
    controller.initialize()

    controller._handle_control_event("fire_alarm_control", {}, {})

    assert any(
        level == "WARNING" and message == "control event ignored: missing action"
        for level, message in recorder.logs
    )
    assert recorder.call_service_calls == []


def test_handle_control_event_reset_not_allowed_logs_and_skips_sync():
    controller, recorder = build_controller(args={"initial_state": c.STATE_ALARM})
    controller.initialize()

    controller._handle_control_event("fire_alarm_control", {"action": "reset"}, {})

    assert any(
        level == "WARNING" and "reset ignored: normal conditions not met (state=alarm)" == message
        for level, message in recorder.logs
    )
    assert recorder.call_service_calls == []


def test_handle_control_event_reset_allowed_resets_context_and_syncs_outputs():
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
    controller._ctx["active_faults"] = {"smoke:s1": {"source": "smoke"}}

    controller._handle_control_event("fire_alarm_control", {"action": "reset"}, {})

    assert controller._ctx["acked"] is False
    assert controller._ctx["silenced"] is False
    assert controller._ctx["manual_override"] is False
    assert controller._ctx["active_faults"] == {}
    assert [name for name, _ in recorder.call_service_calls] == [
        "light/control",
        "beacon/control",
        "buzzer/control",
    ]
    assert any(
        level == "INFO" and "reset cleared active_faults operationally" in message
        for level, message in recorder.logs
    )


def test_send_fault_notify_if_needed_dispatches_notify_and_marks_notified():
    controller, recorder = build_controller(args={"notify_target": "notify/mobile"})
    controller.initialize()

    controller._send_fault_notify_if_needed(
        {
            "payload": {"message": "Fire alarm sensor fault: source=smoke entity=binary_sensor.s1 category=unavailable value=unknown"},
            "fault_notify_key": "smoke:binary_sensor.s1:unavailable_update",
            "is_clear": False,
        }
    )

    assert recorder.call_service_calls == [
        (
            "notify/mobile",
            {
                "message": "Fire alarm sensor fault: source=smoke entity=binary_sensor.s1 category=unavailable value=unknown",
                "action": "send",
            },
        )
    ]
    assert "smoke:binary_sensor.s1:unavailable_update" in controller._ctx["active_fault_notified_keys"]
    assert "smoke:binary_sensor.s1:unavailable_update" in controller._ctx["last_fault_notify_ts_by_key"]
