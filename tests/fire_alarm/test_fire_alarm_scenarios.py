from __future__ import annotations

from typing import Any

from projects.fire_alarm import fire_alarm_constants as c
from projects.fire_alarm.fire_alarm import FireAlarm
import projects.fire_alarm.fire_alarm_temperature as fire_alarm_temperature


class ScenarioRecorder:
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
    recorder = ScenarioRecorder()
    recorder.state_store.update(state_store or {})

    controller.args = args or {}
    controller.log = recorder.log
    controller.get_state = recorder.get_state
    controller.call_service = recorder.call_service
    controller.listen_state = recorder.listen_state
    controller.listen_event = recorder.listen_event
    return controller, recorder


def test_smoke_alarm_lifecycle_transitions_to_alarm_then_clears_to_normal():
    controller, recorder = build_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "beacon_target": "beacon/turn_on",
            "buzzer_target": "buzzer/turn_on",
            "tts_target": "tts/speak",
            "notify_target": "notify/mobile",
            "light_target": "light/control",
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
    assert "critical" in controller._ctx["last_notify_ts_by_state"]
    assert "critical" in controller._ctx["last_tts_ts_by_state"]
    assert [name for name, _ in recorder.call_service_calls[:6]] == [
        "beacon/turn_on",
        "buzzer/turn_on",
        "notify/mobile",
        "tts/speak",
        "notify/mobile",
        "tts/speak",
    ]

    controller._last_transition_ts = None
    controller._handle_sensor_update(
        "binary_sensor.smoke_1",
        "state",
        "on",
        "off",
        {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE},
    )

    assert controller._state == c.STATE_NORMAL
    assert recorder.call_service_calls[-3:] == [
        ("light/control", {"valve_confirmed_closed": False, "action": "effect"}),
        ("notify/mobile", {"category": "prohibited_start", "hard_lockout_active": True, "hazard_source": None, "message": "Hazard lockout active", "state": "normal", "phase": "observe", "trigger_entity_id": "binary_sensor.smoke_1", "trigger_source": "smoke", "action": "send"}),
        ("tts/speak", {"category": "prohibited_start", "hard_lockout_active": True, "hazard_source": None, "message": "Hazard lockout active", "state": "normal", "phase": "observe", "trigger_entity_id": "binary_sensor.smoke_1", "trigger_source": "smoke", "action": "speak"}),
    ]


def test_temperature_only_warning_then_prealarm_lifecycle(monkeypatch):
    times = iter([0.0, 2.0, 4.0, 6.0])
    monkeypatch.setattr(fire_alarm_temperature, "monotonic", lambda: next(times))

    controller, recorder = build_controller(
        args={
            "temperature_sensors": ["sensor.temp_1"],
            "temperature_warning_threshold": 50,
            "temperature_alarm_threshold": 60,
            "temperature_warning_hold_sec": 1,
            "temperature_alarm_hold_sec": 1,
            "light_target": "light/control",
            "notify_target": "notify/mobile",
        },
        state_store={"sensor.temp_1": "20"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "sensor.temp_1", "state", "20", "55", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    assert controller._state == c.STATE_ALARM

    controller._handle_sensor_update(
        "sensor.temp_1", "state", "55", "65", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    assert controller._state == c.STATE_CRITICAL

    controller._handle_sensor_update(
        "sensor.temp_1", "state", "65", "65", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    assert controller._state == c.STATE_CRITICAL
    assert any("state transition: normal -> alarm" in message for _, message in recorder.logs)
    assert any("state transition: alarm -> critical" in message for _, message in recorder.logs)


def test_active_fault_blocks_clear_when_risk_snapshot_returns_normal():
    controller, recorder = build_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "gas_sensors": ["binary_sensor.gas_1"],
            "beacon_target": "beacon/turn_on",
            "buzzer_target": "buzzer/turn_on",
        },
        state_store={"binary_sensor.smoke_1": "off", "binary_sensor.gas_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    assert controller._state == c.STATE_CRITICAL

    controller._handle_sensor_update(
        "binary_sensor.gas_1", "state", "off", "unknown", {"source_name": "gas", "event_name": c.EVENT_GAS_UPDATE}
    )
    assert "gas:binary_sensor.gas_1" in controller._ctx["active_faults"]

    controller._last_transition_ts = None
    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "on", "off", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )

    assert controller._state == c.STATE_CRITICAL


def test_reset_is_allowed_only_when_snapshot_is_safe():
    controller, recorder = build_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "light_target": "light/control",
            "beacon_target": "beacon/control",
            "buzzer_target": "buzzer/control",
        },
        state_store={"binary_sensor.smoke_1": "off"},
    )
    controller.initialize()
    controller._ctx["acked"] = True

    controller._sensor_cache["smoke"]["binary_sensor.smoke_1"] = "on"
    controller._handle_control_event("fire_alarm_control", {"action": "reset"}, {})
    assert controller._ctx["acked"] is True
    assert recorder.call_service_calls == []
    assert any(
        level == "WARNING" and message == "reset ignored: normal conditions not met (state=normal)"
        for level, message in recorder.logs
    )

    controller._sensor_cache["smoke"]["binary_sensor.smoke_1"] = "off"
    controller._ctx["active_faults"] = {"smoke:s1": {"source": "smoke"}}
    controller._handle_control_event("fire_alarm_control", {"action": "reset"}, {})
    assert controller._ctx["acked"] is False
    assert controller._ctx["active_faults"] == {}
    assert [name for name, _ in recorder.call_service_calls] == [
        "light/control",
        "beacon/control",
        "buzzer/control",
    ]


def test_anti_flap_downgrade_hold_prevents_immediate_clear():
    controller, recorder = build_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "beacon_target": "beacon/turn_on",
            "buzzer_target": "buzzer/turn_on",
        },
        state_store={"binary_sensor.smoke_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "on", "off", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )

    assert controller._state == c.STATE_NORMAL
    assert recorder.call_service_calls[-1][0] in {"buzzer/turn_on", "notify/mobile", "tts/speak", "light/control"}


def test_repeated_sensor_updates_do_not_duplicate_entry_actions_for_same_state():
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
        "binary_sensor.smoke_1", "state", "off", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    first_call_count = len(recorder.call_service_calls)

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "on", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )

    assert controller._state == c.STATE_CRITICAL
    assert len(recorder.call_service_calls) == first_call_count
    assert sum(1 for level, message in recorder.logs if level == "INFO" and "state transition: normal -> critical" in message) == 1
