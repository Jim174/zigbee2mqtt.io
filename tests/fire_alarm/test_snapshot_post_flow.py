from __future__ import annotations

from projects.fire_alarm.fire_alarm_snapshot_flow import SnapshotBuildFlowResult
from projects.fire_alarm.fire_alarm_snapshot_post_flow import build_snapshot_post_flow_result


def test_build_snapshot_post_flow_result_applies_temperature_policy_and_preserves_payload_shape():
    snapshot_flow = SnapshotBuildFlowResult(
        smoke_states={"binary_sensor.smoke": "off"},
        gas_states={"binary_sensor.gas": "off"},
        temperature_states={"sensor.temp": "72"},
        smoke_summary={"any_alarm": False},
        gas_summary={"any_alarm": False},
        temperature_summary={"any_alarm": False, "any_warning": False, "active_entities": []},
        non_numeric_temperature_log_lines=[],
    )

    result = build_snapshot_post_flow_result(
        snapshot_flow=snapshot_flow,
        state="alarm",
        phase="alert",
        ctx={
            "acked": False,
            "silenced": False,
            "manual_override": False,
            "active_faults": {},
            "current_incident_id": "inc-1",
            "incident_start_ts": "2026-03-18T00:00:00+00:00",
            "incident_severity": "alarm",
            "incident_active_sources": ["smoke"],
            "acked_incident_id": None,
            "silenced_incident_id": None,
        },
        trigger_entity="sensor.temp",
        source_name="temperature",
        event_name="temperature_update",
        old_value="71",
        new_value="72",
        apply_temperature_policy=lambda temperature_states, base_summary: {
            **base_summary,
            "any_alarm": True,
            "active_entities": list(temperature_states),
        },
    )

    assert result.risk_snapshot["state"] == "alarm"
    assert result.risk_snapshot["phase"] == "alert"
    assert result.risk_snapshot["trigger"]["entity_id"] == "sensor.temp"
    assert result.risk_snapshot["summary"]["temperature"]["any_alarm"] is True
    assert result.risk_snapshot["summary"]["temperature"]["active_entities"] == ["sensor.temp"]
    assert result.log_items == []


def test_build_snapshot_post_flow_result_emits_debug_log_items_for_non_numeric_temperature_lines():
    snapshot_flow = SnapshotBuildFlowResult(
        smoke_states={},
        gas_states={},
        temperature_states={},
        smoke_summary={},
        gas_summary={},
        temperature_summary={"any_alarm": False, "any_warning": False},
        non_numeric_temperature_log_lines=[
            "temperature non-numeric value ignored: entity=sensor.temp value=hot"
        ],
    )

    result = build_snapshot_post_flow_result(
        snapshot_flow=snapshot_flow,
        state="normal",
        phase="observe",
        ctx={
            "acked": False,
            "silenced": False,
            "manual_override": False,
            "active_faults": {},
            "current_incident_id": None,
            "incident_start_ts": None,
            "incident_severity": None,
            "incident_active_sources": [],
            "acked_incident_id": None,
            "silenced_incident_id": None,
        },
        trigger_entity="sensor.temp",
        source_name="temperature",
        event_name="temperature_update",
        old_value="warm",
        new_value="hot",
        apply_temperature_policy=lambda temperature_states, base_summary: base_summary,
    )

    assert result.log_items == [
        ("DEBUG", "temperature non-numeric value ignored: entity=sensor.temp value=hot")
    ]
