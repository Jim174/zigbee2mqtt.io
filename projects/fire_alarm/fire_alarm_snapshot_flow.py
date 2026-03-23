"""Snapshot build flow helpers for fire alarm controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .fire_alarm_rules import is_gas_alarm_like, is_smoke_alarm_like, to_float
from .fire_alarm_sensor_store import collect_sensor_states
from .fire_alarm_snapshot import summarize_binary_source, summarize_temperature_source
from .fire_alarm_snapshot_builder import iter_non_numeric_temperature_log_lines


@dataclass(frozen=True)
class SnapshotBuildFlowResult:
    smoke_states: dict[str, Any]
    gas_states: dict[str, Any]
    temperature_states: dict[str, Any]
    smoke_summary: dict[str, Any]
    gas_summary: dict[str, Any]
    temperature_summary: dict[str, Any]
    non_numeric_temperature_log_lines: list[str]


def build_snapshot_flow_result(
    *,
    sensor_cache: dict[str, dict[str, Any]],
    sensor_entity_ids: dict[str, list[str]],
    get_state: Callable[[str], Any],
    log_warning: Callable[[str], None],
    is_unavailable: Callable[[Any], bool],
    temp_warning_threshold: float,
    temp_alarm_threshold: float,
) -> SnapshotBuildFlowResult:
    """Collect source states and assemble raw summaries for risk snapshot building."""
    smoke_states = collect_sensor_states(
        sensor_cache=sensor_cache,
        sensor_entity_ids=sensor_entity_ids,
        source_name="smoke",
        get_state=get_state,
        log_warning=log_warning,
    )
    gas_states = collect_sensor_states(
        sensor_cache=sensor_cache,
        sensor_entity_ids=sensor_entity_ids,
        source_name="gas",
        get_state=get_state,
        log_warning=log_warning,
    )
    temperature_states = collect_sensor_states(
        sensor_cache=sensor_cache,
        sensor_entity_ids=sensor_entity_ids,
        source_name="temperature",
        get_state=get_state,
        log_warning=log_warning,
    )

    smoke_summary = summarize_binary_source(
        smoke_states,
        is_alarm_like=is_smoke_alarm_like,
        is_unavailable=is_unavailable,
    )
    gas_summary = summarize_binary_source(
        gas_states,
        is_alarm_like=is_gas_alarm_like,
        is_unavailable=is_unavailable,
    )
    temperature_summary, non_numeric_temperature_entries = summarize_temperature_source(
        temperature_states,
        temp_warning_threshold=temp_warning_threshold,
        temp_alarm_threshold=temp_alarm_threshold,
        to_float=to_float,
        is_unavailable=is_unavailable,
    )

    return SnapshotBuildFlowResult(
        smoke_states=smoke_states,
        gas_states=gas_states,
        temperature_states=temperature_states,
        smoke_summary=smoke_summary,
        gas_summary=gas_summary,
        temperature_summary=temperature_summary,
        non_numeric_temperature_log_lines=iter_non_numeric_temperature_log_lines(
            non_numeric_temperature_entries
        ),
    )
