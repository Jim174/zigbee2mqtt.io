"""Dependency bundle assembly helpers for fire alarm controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .fire_alarm_control import apply_control_action
from .fire_alarm_control_event_flow import ControlEventFlowDeps
from .fire_alarm_faults import clear_sensor_fault, record_sensor_fault
from .fire_alarm_sensor_store import update_sensor_cache_entry
from .fire_alarm_sensor_update_flow import SensorUpdateFlowDeps


@dataclass(frozen=True)
class ControllerFlowDepsResult:
    sensor_update_flow_deps: SensorUpdateFlowDeps
    control_event_flow_deps: ControlEventFlowDeps


def build_sensor_update_flow_deps(
    *,
    sensor_cache: dict[str, dict[str, Any]],
    is_unavailable: Callable[[Any], bool],
    build_risk_snapshot: Callable[..., dict[str, Any]],
    decide_next_state: Callable[[dict[str, Any]], str],
    transition_state: Callable[[str, dict[str, Any]], bool],
    log: Callable[[str, str], None],
) -> SensorUpdateFlowDeps:
    """Build the sensor update lock-flow dependency bundle."""

    def log_warning(message: str) -> None:
        log(message, "WARNING")

    def log_debug(message: str) -> None:
        log(message, "DEBUG")

    def update_cached_sensor(source_name: str, entity_id: str, value: Any) -> None:
        update_sensor_cache_entry(
            sensor_cache=sensor_cache,
            source_name=source_name,
            entity_id=entity_id,
            value=value,
            log_warning=log_warning,
        )

    return SensorUpdateFlowDeps(
        update_sensor_cache_entry=update_cached_sensor,
        is_unavailable=is_unavailable,
        record_sensor_fault=record_sensor_fault,
        clear_sensor_fault=clear_sensor_fault,
        build_risk_snapshot=build_risk_snapshot,
        decide_next_state=decide_next_state,
        transition_state=transition_state,
        log_warning=log_warning,
        log_debug=log_debug,
    )


def build_control_event_flow_deps(
    *,
    can_reset_context: Callable[[], bool],
    reset_runtime_context: Callable[[], bool],
) -> ControlEventFlowDeps:
    """Build the control event lock-flow dependency bundle."""
    return ControlEventFlowDeps(
        can_reset_context=can_reset_context,
        apply_control_action=apply_control_action,
        reset_runtime_context=reset_runtime_context,
    )


def build_controller_flow_deps(
    *,
    sensor_cache: dict[str, dict[str, Any]],
    is_unavailable: Callable[[Any], bool],
    build_risk_snapshot: Callable[..., dict[str, Any]],
    decide_next_state: Callable[[dict[str, Any]], str],
    transition_state: Callable[[str, dict[str, Any]], bool],
    can_reset_context: Callable[[], bool],
    reset_runtime_context: Callable[[], bool],
    log: Callable[[str, str], None],
) -> ControllerFlowDepsResult:
    """Build both controller-owned flow dependency bundles in one place."""
    return ControllerFlowDepsResult(
        sensor_update_flow_deps=build_sensor_update_flow_deps(
            sensor_cache=sensor_cache,
            is_unavailable=is_unavailable,
            build_risk_snapshot=build_risk_snapshot,
            decide_next_state=decide_next_state,
            transition_state=transition_state,
            log=log,
        ),
        control_event_flow_deps=build_control_event_flow_deps(
            can_reset_context=can_reset_context,
            reset_runtime_context=reset_runtime_context,
        ),
    )
