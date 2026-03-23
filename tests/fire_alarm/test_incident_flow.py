from __future__ import annotations

from projects.fire_alarm import fire_alarm_constants as c
import projects.fire_alarm.fire_alarm_temperature as fire_alarm_temperature


def test_escalation_progression_opens_and_refreshes_one_incident(monkeypatch, build_test_controller):
    times = iter([0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0])
    monkeypatch.setattr(fire_alarm_temperature, "monotonic", lambda: next(times))

    controller, recorder = build_test_controller(
        args={
            "temperature_sensors": ["sensor.temp_1"],
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "temperature_warning_threshold": 50,
            "temperature_alarm_threshold": 60,
            "temperature_warning_hold_sec": 1,
            "temperature_alarm_hold_sec": 1,
            "light_target": "light/control",
            "beacon_target": "beacon/control",
            "buzzer_target": "buzzer/control",
            "notify_target": "notify/mobile",
            "tts_target": "tts/speaker",
        },
        state_store={"sensor.temp_1": "20", "binary_sensor.smoke_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "sensor.temp_1", "state", "20", "55", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    controller._handle_sensor_update(
        "sensor.temp_1", "state", "55", "55", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    assert controller._state == c.STATE_ALARM
    assert controller._escalation_phase == c.PHASE_ALERT

    controller._handle_sensor_update(
        "sensor.temp_1", "state", "55", "65", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    controller._handle_sensor_update(
        "sensor.temp_1", "state", "65", "65", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    assert controller._state == c.STATE_CRITICAL
    assert controller._escalation_phase == c.PHASE_EMERGENCY
    incident_id = controller._ctx["current_incident_id"]
    assert incident_id is not None
    assert controller._ctx["incident_severity"] == c.STATE_CRITICAL
    assert controller._ctx["incident_active_sources"] == ["temperature_alarm"]

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )

    assert controller._state == c.STATE_CRITICAL
    assert controller._escalation_phase == c.PHASE_EMERGENCY
    assert controller._ctx["current_incident_id"] == incident_id
    assert controller._ctx["incident_severity"] == c.STATE_CRITICAL
    assert controller._ctx["incident_active_sources"] == ["smoke", "temperature_alarm"]
    assert sum(1 for _, message in recorder.logs if "incident opened" in message) == 1
    assert sum(1 for _, message in recorder.logs if "state transition: normal -> alarm" in message) == 1
    assert sum(1 for _, message in recorder.logs if "state transition: alarm -> critical" in message) == 1

    service_names = [name for name, _ in recorder.call_service_calls]
    assert service_names == [
        "light/control",
        "beacon/control",
        "notify/mobile",
        "tts/speaker",
        "light/control",
        "beacon/control",
        "buzzer/control",
        "notify/mobile",
        "tts/speaker",
        "light/control",
        "beacon/control",
        "buzzer/control",
    ]


def test_escalation_clears_ack_and_silence_bindings_and_recovery_closes_incident(monkeypatch, build_test_controller):
    times = iter([0.0, 2.0, 4.0, 6.0, 8.0, 10.0])
    monkeypatch.setattr(fire_alarm_temperature, "monotonic", lambda: next(times))

    controller, recorder = build_test_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "temperature_sensors": ["sensor.temp_1"],
            "temperature_warning_threshold": 50,
            "temperature_alarm_threshold": 60,
            "temperature_warning_hold_sec": 1,
            "temperature_alarm_hold_sec": 1,
            "beacon_target": "beacon/control",
            "buzzer_target": "buzzer/control",
            "notify_target": "notify/mobile",
            "tts_target": "tts/speaker",
            "light_target": "light/control",
        },
        state_store={"binary_sensor.smoke_1": "off", "sensor.temp_1": "20"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    incident_id = controller._ctx["current_incident_id"]

    controller._handle_control_event("fire_alarm_control", {"action": "ack"}, {})
    controller._handle_control_event("fire_alarm_control", {"action": "silence"}, {})
    assert controller._ctx["acked"] is True
    assert controller._ctx["silenced"] is True
    assert controller._ctx["acked_incident_id"] == incident_id
    assert controller._ctx["silenced_incident_id"] == incident_id

    controller._handle_sensor_update(
        "sensor.temp_1", "state", "20", "65", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    controller._handle_sensor_update(
        "sensor.temp_1", "state", "65", "65", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    assert controller._state == c.STATE_CRITICAL
    assert controller._ctx["acked"] is True
    assert controller._ctx["silenced"] is True
    assert controller._ctx["acked_incident_id"] == incident_id
    assert controller._ctx["silenced_incident_id"] == incident_id

    controller._last_transition_ts = None
    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "on", "off", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    controller._last_transition_ts = None
    controller._handle_sensor_update(
        "sensor.temp_1", "state", "65", "20", {"source_name": "temperature", "event_name": c.EVENT_TEMPERATURE_UPDATE}
    )
    controller._last_transition_ts = None
    controller._handle_sensor_update(
        "binary_sensor.gas_1", "state", "on", "off", {"source_name": "gas", "event_name": c.EVENT_GAS_UPDATE}
    )

    assert controller._state == c.STATE_NORMAL
    assert controller._ctx["current_incident_id"] is None
    assert controller._ctx["incident_severity"] is None
    assert controller._ctx["incident_active_sources"] == []
    assert any(level == "INFO" and "incident closed" in message for level, message in recorder.logs)


def test_same_state_alarm_update_refreshes_incident_without_duplicate_transition_log(build_test_controller):
    controller, recorder = build_test_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "gas_sensors": ["binary_sensor.gas_1"],
            "beacon_target": "beacon/control",
            "buzzer_target": "buzzer/control",
            "notify_target": "notify/mobile",
            "tts_target": "tts/speaker",
        },
        state_store={"binary_sensor.smoke_1": "off", "binary_sensor.gas_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    incident_id = controller._ctx["current_incident_id"]
    first_call_count = len(recorder.call_service_calls)
    first_notify_count = sum(1 for name, _ in recorder.call_service_calls if name == "notify/mobile")
    first_tts_count = sum(1 for name, _ in recorder.call_service_calls if name == "tts/speaker")

    controller._handle_sensor_update(
        "binary_sensor.gas_1", "state", "off", "on", {"source_name": "gas", "event_name": c.EVENT_GAS_UPDATE}
    )

    assert controller._state == c.STATE_CRITICAL
    assert controller._ctx["current_incident_id"] == incident_id
    assert controller._ctx["incident_active_sources"] == ["smoke", "gas"]
    assert len(recorder.call_service_calls) == first_call_count + 2
    assert sum(1 for name, _ in recorder.call_service_calls if name == "notify/mobile") == first_notify_count
    assert sum(1 for name, _ in recorder.call_service_calls if name == "tts/speaker") == first_tts_count
    assert sum(1 for _, message in recorder.logs if "state transition: normal -> critical" in message) == 1
    assert any(level == "INFO" and "incident escalated" in message for level, message in recorder.logs)


def test_active_fault_blocks_alarm_clear_until_fault_is_cleared(build_test_controller):
    controller, recorder = build_test_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "gas_sensors": ["binary_sensor.gas_1"],
            "beacon_target": "beacon/control",
            "buzzer_target": "buzzer/control",
            "notify_target": "notify/mobile",
        },
        state_store={"binary_sensor.smoke_1": "off", "binary_sensor.gas_1": "off"},
    )
    controller.initialize()

    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "on", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    controller._handle_sensor_update(
        "binary_sensor.gas_1", "state", "off", "unknown", {"source_name": "gas", "event_name": c.EVENT_GAS_UPDATE}
    )
    assert "gas:binary_sensor.gas_1" in controller._ctx["active_faults"]

    controller._last_transition_ts = None
    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "on", "off", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )
    assert controller._state == c.STATE_CRITICAL

    controller._handle_sensor_update(
        "binary_sensor.gas_1", "state", "unknown", "off", {"source_name": "gas", "event_name": c.EVENT_GAS_UPDATE}
    )
    controller._last_transition_ts = None
    controller._handle_sensor_update(
        "binary_sensor.smoke_1", "state", "off", "off", {"source_name": "smoke", "event_name": c.EVENT_SMOKE_UPDATE}
    )

    assert controller._state == c.STATE_NORMAL
