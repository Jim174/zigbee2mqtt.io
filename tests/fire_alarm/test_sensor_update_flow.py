from __future__ import annotations

from projects.fire_alarm.fire_alarm_sensor_update_flow import SensorUpdateFlowDeps, run_sensor_update_flow


def _deps(events: list[tuple[str, object]]):
    def update_sensor_cache_entry(source_name: str, entity_id: str, value: object) -> None:
        events.append(("cache", (source_name, entity_id, value)))

    def record_sensor_fault(**kwargs):
        events.append(("record_fault", kwargs))
        return {"kind": "fault", "entity": kwargs["entity_id"]}

    def clear_sensor_fault(**kwargs):
        events.append(("clear_fault", kwargs))
        return {"kind": "clear", "entity": kwargs["entity_id"]}

    def build_risk_snapshot(**kwargs):
        events.append(("snapshot", kwargs))
        return {"summary": {}, "trigger": {"entity_id": kwargs["trigger_entity"]}}

    def decide_next_state(snapshot):
        events.append(("decide", snapshot))
        return "alarm"

    def transition_state(next_state, snapshot):
        events.append(("transition", (next_state, snapshot)))
        return True

    def log_warning(message: str) -> None:
        events.append(("warning", message))

    def log_debug(message: str) -> None:
        events.append(("debug", message))

    return SensorUpdateFlowDeps(
        update_sensor_cache_entry=update_sensor_cache_entry,
        is_unavailable=lambda value: value in {"unknown", "unavailable"},
        record_sensor_fault=record_sensor_fault,
        clear_sensor_fault=clear_sensor_fault,
        build_risk_snapshot=build_risk_snapshot,
        decide_next_state=decide_next_state,
        transition_state=transition_state,
        log_warning=log_warning,
        log_debug=log_debug,
    )


def test_run_sensor_update_flow_records_fault_and_skips_on_unavailable():
    events = []
    result = run_sensor_update_flow(
        entity="sensor.smoke_1",
        source_name="smoke",
        event_name="smoke_update",
        old_value="off",
        new_value="unknown",
        current_state="normal",
        state_disabled="disabled",
        ctx={},
        fault_notify_enabled=True,
        fault_clear_notify_enabled=False,
        fault_notify_cooldown_sec=60,
        deps=_deps(events),
    )

    assert result["skip_main_evaluation"] is True
    assert result["pending_fault_notify"] == {"kind": "fault", "entity": "sensor.smoke_1"}
    assert result["risk_snapshot"] is None
    assert [event[0] for event in events] == ["cache", "record_fault", "warning"]


def test_run_sensor_update_flow_skips_evaluation_when_state_disabled():
    events = []
    result = run_sensor_update_flow(
        entity="sensor.gas_1",
        source_name="gas",
        event_name="gas_update",
        old_value="off",
        new_value="on",
        current_state="disabled",
        state_disabled="disabled",
        ctx={},
        fault_notify_enabled=True,
        fault_clear_notify_enabled=False,
        fault_notify_cooldown_sec=60,
        deps=_deps(events),
    )

    assert result["skip_main_evaluation"] is True
    assert result["pending_fault_notify"] == {"kind": "clear", "entity": "sensor.gas_1"}
    assert result["risk_snapshot"] is None
    assert [event[0] for event in events] == ["cache", "clear_fault", "debug"]


def test_run_sensor_update_flow_sets_entry_state_when_transition_changes():
    events = []
    result = run_sensor_update_flow(
        entity="sensor.temp_1",
        source_name="temperature",
        event_name="temperature_update",
        old_value="50",
        new_value="70",
        current_state="normal",
        state_disabled="disabled",
        ctx={},
        fault_notify_enabled=True,
        fault_clear_notify_enabled=False,
        fault_notify_cooldown_sec=60,
        deps=_deps(events),
    )

    assert result["skip_main_evaluation"] is False
    assert result["entry_state"] == "alarm"
    assert result["risk_snapshot"] == {"summary": {}, "trigger": {"entity_id": "sensor.temp_1"}}
    assert [event[0] for event in events] == ["cache", "clear_fault", "snapshot", "decide", "transition"]


def test_run_sensor_update_flow_keeps_entry_state_none_when_transition_unchanged():
    events = []
    deps = _deps(events)
    deps = SensorUpdateFlowDeps(
        update_sensor_cache_entry=deps.update_sensor_cache_entry,
        is_unavailable=deps.is_unavailable,
        record_sensor_fault=deps.record_sensor_fault,
        clear_sensor_fault=deps.clear_sensor_fault,
        build_risk_snapshot=deps.build_risk_snapshot,
        decide_next_state=deps.decide_next_state,
        transition_state=lambda next_state, snapshot: False,
        log_warning=deps.log_warning,
        log_debug=deps.log_debug,
    )

    result = run_sensor_update_flow(
        entity="sensor.temp_2",
        source_name="temperature",
        event_name="temperature_update",
        old_value="50",
        new_value="55",
        current_state="normal",
        state_disabled="disabled",
        ctx={},
        fault_notify_enabled=True,
        fault_clear_notify_enabled=False,
        fault_notify_cooldown_sec=60,
        deps=deps,
    )

    assert result["skip_main_evaluation"] is False
    assert result["entry_state"] is None
    assert result["risk_snapshot"] is not None
