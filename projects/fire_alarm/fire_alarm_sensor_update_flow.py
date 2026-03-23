"""Sensor update lock-flow helpers for fire alarm controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


SensorFlowResult = dict[str, Any]


@dataclass(frozen=True)
class SensorUpdateFlowDeps:
    """Dependency bundle for the sensor update lock-flow."""

    update_sensor_cache_entry: Callable[[str, str, Any], None]
    is_unavailable: Callable[[Any], bool]
    record_sensor_fault: Callable[..., dict[str, Any] | None]
    clear_sensor_fault: Callable[..., dict[str, Any] | None]
    build_risk_snapshot: Callable[..., dict[str, Any]]
    decide_next_state: Callable[[dict[str, Any]], str]
    transition_state: Callable[[str, dict[str, Any]], bool]
    log_warning: Callable[[str], None]
    log_debug: Callable[[str], None]


def run_sensor_update_flow(
    *,
    entity: str,
    source_name: str,
    event_name: str,
    old_value: Any,
    new_value: Any,
    current_state: str,
    state_disabled: str,
    ctx: dict[str, Any],
    fault_notify_enabled: bool,
    fault_clear_notify_enabled: bool,
    fault_notify_cooldown_sec: int,
    deps: SensorUpdateFlowDeps,
) -> SensorFlowResult:
    """Run sensor update decision flow expected to execute inside controller lock."""
    deps.update_sensor_cache_entry(source_name, entity, new_value)

    result: SensorFlowResult = {
        "skip_main_evaluation": False,
        "pending_fault_notify": None,
        "entry_state": None,
        "risk_snapshot": None,
    }

    if deps.is_unavailable(new_value):
        result["pending_fault_notify"] = deps.record_sensor_fault(
            ctx=ctx,
            entity_id=entity,
            source_name=source_name,
            category="unavailable_update",
            observed_value=new_value,
            fault_notify_enabled=fault_notify_enabled,
            fault_clear_notify_enabled=fault_clear_notify_enabled,
            fault_notify_cooldown_sec=fault_notify_cooldown_sec,
        )
        deps.log_warning(
            "skip unavailable update: entity=%s source=%s value=%s"
            % (entity, source_name, new_value)
        )
        result["skip_main_evaluation"] = True
        return result

    result["pending_fault_notify"] = deps.clear_sensor_fault(
        ctx=ctx,
        source_name=source_name,
        entity_id=entity,
        fault_notify_enabled=fault_notify_enabled,
        fault_clear_notify_enabled=fault_clear_notify_enabled,
        fault_notify_cooldown_sec=fault_notify_cooldown_sec,
    )

    if current_state == state_disabled:
        deps.log_debug(
            "state is disabled, ignore sensor update: entity=%s source=%s"
            % (entity, source_name)
        )
        result["skip_main_evaluation"] = True
        return result

    risk_snapshot = deps.build_risk_snapshot(
        trigger_entity=entity,
        source_name=source_name,
        event_name=event_name,
        old_value=old_value,
        new_value=new_value,
    )
    result["risk_snapshot"] = risk_snapshot

    next_state = deps.decide_next_state(risk_snapshot)
    if deps.transition_state(next_state, risk_snapshot):
        result["entry_state"] = next_state

    return result
