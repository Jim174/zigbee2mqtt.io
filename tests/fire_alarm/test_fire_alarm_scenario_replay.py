from __future__ import annotations

from projects.fire_alarm import fire_alarm_constants as c
import projects.fire_alarm.fire_alarm_faults as fire_alarm_faults
import projects.fire_alarm.fire_alarm_temperature as fire_alarm_temperature

from tests.fire_alarm.scenario_runner import ScenarioRunner, ScenarioStep


def test_scenario_replay_smoke_alarm_lifecycle(build_test_controller):
    controller, recorder = build_test_controller(
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

    runner = ScenarioRunner(controller, recorder, scenario_name="smoke alarm lifecycle")
    runner.run(
        [
            ScenarioStep(
                name="smoke triggers alarm",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="off",
                new="on",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["light/control", "beacon/turn_on", "buzzer/turn_on", "notify/mobile", "tts/speak", "notify/mobile", "tts/speak"],
                notify_mark_updated=True,
                tts_mark_updated=True,
            ),
            ScenarioStep(
                name="smoke clears back to normal",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="on",
                new="off",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                pre_hook=lambda controller, recorder: setattr(controller, "_last_transition_ts", None),
                expected_state=c.STATE_NORMAL,
                expected_phase=c.PHASE_OBSERVE,
                expected_ctx={"current_incident_id": None, "incident_severity": None, "incident_active_sources": []},
                expected_new_calls=["light/control", "notify/mobile", "tts/speak"],
                notify_mark_updated=False,
                tts_mark_updated=False,
            ),
        ]
    )


def test_scenario_replay_temperature_warning_then_prealarm(monkeypatch, build_test_controller):
    times = iter([0.0, 2.0])
    monkeypatch.setattr(fire_alarm_temperature, "monotonic", lambda: next(times))

    controller, recorder = build_test_controller(
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

    runner = ScenarioRunner(controller, recorder, scenario_name="temperature-only warning/prealarm lifecycle")
    runner.run(
        [
            ScenarioStep(
                name="warning threshold enters observe",
                kind="sensor",
                entity="sensor.temp_1",
                old="20",
                new="55",
                source_name="temperature",
                event_name=c.EVENT_TEMPERATURE_UPDATE,
                expected_state=c.STATE_ALARM,
                expected_phase=c.PHASE_ALERT,
                expected_new_calls=["light/control", "notify/mobile"],
                notify_mark_updated=True,
            ),
            ScenarioStep(
                name="alarm threshold escalates to prealarm",
                kind="sensor",
                entity="sensor.temp_1",
                old="55",
                new="65",
                source_name="temperature",
                event_name=c.EVENT_TEMPERATURE_UPDATE,
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["light/control", "notify/mobile"],
                notify_mark_updated=True,
            ),
        ]
    )


def test_scenario_replay_active_fault_blocks_clear(build_test_controller):
    controller, recorder = build_test_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "gas_sensors": ["binary_sensor.gas_1"],
            "beacon_target": "beacon/turn_on",
            "buzzer_target": "buzzer/turn_on",
            "notify_target": "notify/mobile",
        },
        state_store={"binary_sensor.smoke_1": "off", "binary_sensor.gas_1": "off"},
    )
    controller.initialize()

    runner = ScenarioRunner(controller, recorder, scenario_name="active fault blocks clear")
    runner.run(
        [
            ScenarioStep(
                name="smoke alarm opens incident",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="off",
                new="on",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["beacon/turn_on", "buzzer/turn_on", "notify/mobile", "notify/mobile"],
                notify_mark_updated=True,
            ),
            ScenarioStep(
                name="gas unavailable records fault",
                kind="sensor",
                entity="binary_sensor.gas_1",
                old="off",
                new="unknown",
                source_name="gas",
                event_name=c.EVENT_GAS_UPDATE,
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["notify/mobile", "beacon/turn_on", "buzzer/turn_on"],
                expect_log_contains=["sensor fault recorded"],
            ),
            ScenarioStep(
                name="clear attempt is blocked by active fault",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="on",
                new="off",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                pre_hook=lambda controller, recorder: setattr(controller, "_last_transition_ts", None),
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["notify/mobile"],
            ),
        ]
    )
    assert "gas:binary_sensor.gas_1" in controller._ctx["active_faults"]


def test_scenario_replay_reset_blocked_when_snapshot_unsafe(build_test_controller):
    controller, recorder = build_test_controller(
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

    runner = ScenarioRunner(controller, recorder, scenario_name="reset blocked when snapshot unsafe")
    runner.run(
        [
            ScenarioStep(
                name="unsafe reset is blocked",
                kind="control",
                data={"action": "reset"},
                pre_hook=lambda controller, recorder: controller._sensor_cache["smoke"].__setitem__("binary_sensor.smoke_1", "on"),
                expected_state=c.STATE_NORMAL,
                expected_phase=c.PHASE_OBSERVE,
                expected_ctx={"acked": True},
                expected_new_calls=[],
                expect_noop=True,
                expect_log_contains=["reset ignored: normal conditions not met"],
            ),
        ]
    )


def test_scenario_replay_reset_allowed_when_snapshot_safe(build_test_controller):
    controller, recorder = build_test_controller(
        args={
            "light_target": "light/control",
            "beacon_target": "beacon/control",
            "buzzer_target": "buzzer/control",
        }
    )
    controller.initialize()

    runner = ScenarioRunner(controller, recorder, scenario_name="reset allowed when snapshot safe")
    runner.run(
        [
            ScenarioStep(
                name="safe reset clears runtime context",
                kind="control",
                data={"action": "reset"},
                pre_hook=lambda controller, recorder: controller._ctx.update(
                    {
                        "acked": True,
                        "silenced": True,
                        "manual_override": True,
                        "active_faults": {"smoke:s1": {"source": "smoke"}},
                    }
                ),
                expected_state=c.STATE_NORMAL,
                expected_phase=c.PHASE_OBSERVE,
                expected_ctx={"acked": False, "silenced": False, "manual_override": False, "active_faults": {}},
                expected_new_calls=["light/control", "beacon/control", "buzzer/control"],
            ),
        ]
    )


def test_scenario_replay_repeated_same_alarm_is_noop_for_entry_actions(build_test_controller):
    controller, recorder = build_test_controller(
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

    runner = ScenarioRunner(controller, recorder, scenario_name="repeated same alarm does not duplicate entry actions")
    runner.run(
        [
            ScenarioStep(
                name="first alarm dispatches outputs",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="off",
                new="on",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["beacon/turn_on", "buzzer/turn_on", "notify/mobile", "tts/speak", "notify/mobile", "tts/speak"],
                notify_mark_updated=True,
                tts_mark_updated=True,
            ),
            ScenarioStep(
                name="repeat alarm is noop",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="on",
                new="on",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=[],
                expect_noop=True,
                notify_mark_updated=False,
                tts_mark_updated=False,
            ),
        ]
    )


def test_scenario_replay_escalation_resets_ack_and_silence(monkeypatch, build_test_controller):
    times = iter([0.0, 2.0])
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
            "tts_target": "tts/speaker",
            "notify_target": "notify/mobile",
        },
        state_store={"binary_sensor.smoke_1": "off", "sensor.temp_1": "20"},
    )
    controller.initialize()

    runner = ScenarioRunner(controller, recorder, scenario_name="escalation resets ack/silence")
    runner.run(
        [
            ScenarioStep(
                name="smoke alarm enters alarm state",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="off",
                new="on",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["beacon/control", "buzzer/control", "notify/mobile", "tts/speaker", "notify/mobile", "tts/speaker"],
                notify_mark_updated=True,
                tts_mark_updated=True,
            ),
            ScenarioStep(
                name="ack binds current incident",
                kind="control",
                data={"action": "ack"},
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["beacon/control", "buzzer/control"],
                expected_ctx={"acked": True},
            ),
            ScenarioStep(
                name="silence binds current incident",
                kind="control",
                data={"action": "silence"},
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["beacon/control", "buzzer/control"],
                expected_ctx={"acked": True, "silenced": True},
            ),
            ScenarioStep(
                name="temperature escalation clears ack and silence",
                kind="sensor",
                entity="sensor.temp_1",
                old="20",
                new="65",
                source_name="temperature",
                event_name=c.EVENT_TEMPERATURE_UPDATE,
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_ctx={"acked": True, "silenced": True},
                expected_new_calls=["beacon/control", "buzzer/control"],
                notify_mark_updated=False,
                tts_mark_updated=False,
            ),
        ]
    )


def test_scenario_replay_anti_flap_downgrade_hold(build_test_controller):
    controller, recorder = build_test_controller(
        args={
            "smoke_sensors": ["binary_sensor.smoke_1"],
            "beacon_target": "beacon/turn_on",
            "buzzer_target": "buzzer/turn_on",
        },
        state_store={"binary_sensor.smoke_1": "off"},
    )
    controller.initialize()

    runner = ScenarioRunner(controller, recorder, scenario_name="anti-flap downgrade hold")
    runner.run(
        [
            ScenarioStep(
                name="smoke enters alarm",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="off",
                new="on",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                expected_state=c.STATE_CRITICAL,
                expected_phase=c.PHASE_EMERGENCY,
                expected_new_calls=["beacon/turn_on", "buzzer/turn_on"],
            ),
            ScenarioStep(
                name="immediate clear is held",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="on",
                new="off",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                expected_state=c.STATE_NORMAL,
                expected_phase=c.PHASE_OBSERVE,
                expected_new_calls=[]
            ),
        ]
    )


def test_scenario_replay_fault_unavailable_then_recover(monkeypatch, build_test_controller):
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

    runner = ScenarioRunner(controller, recorder, scenario_name="fault unavailable to recover")
    runner.run(
        [
            ScenarioStep(
                name="sensor becomes unavailable",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="off",
                new="unknown",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                expected_state=c.STATE_NORMAL,
                expected_phase=c.PHASE_OBSERVE,
                expected_new_calls=[("notify/mobile", {"message": "Fire alarm sensor fault: source=smoke entity=binary_sensor.smoke_1 category=unavailable_update value=unknown", "action": "send"})],
                expect_log_contains=["sensor fault recorded"],
            ),
            ScenarioStep(
                name="sensor recovers and emits clear notification",
                kind="sensor",
                entity="binary_sensor.smoke_1",
                old="unknown",
                new="off",
                source_name="smoke",
                event_name=c.EVENT_SMOKE_UPDATE,
                expected_state=c.STATE_NORMAL,
                expected_phase=c.PHASE_OBSERVE,
                expected_new_calls=[("notify/mobile", {"message": "Fire alarm sensor fault cleared: source=smoke entity=binary_sensor.smoke_1 category=sensor_unknown last_value=unknown", "action": "send"})],
            ),
        ]
    )


def test_scenario_replay_malformed_control_event_ignored(build_test_controller):
    controller, recorder = build_test_controller()
    controller.initialize()

    runner = ScenarioRunner(controller, recorder, scenario_name="malformed control event ignored")
    runner.run(
        [
            ScenarioStep(
                name="unsupported control payload is ignored",
                kind="control",
                data={"action": {"bad": 1}},
                expected_state=c.STATE_NORMAL,
                expected_phase=c.PHASE_OBSERVE,
                expected_new_calls=[],
                expect_noop=True,
                expect_log_contains=["control event ignored: unsupported action={'bad': 1}"],
            ),
        ]
    )
