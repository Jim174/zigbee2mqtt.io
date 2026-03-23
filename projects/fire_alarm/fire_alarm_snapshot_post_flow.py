"""Snapshot post-processing flow helpers for fire alarm controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .fire_alarm_snapshot_builder import build_risk_snapshot_payload
from .fire_alarm_snapshot_flow import SnapshotBuildFlowResult


@dataclass(frozen=True)
class SnapshotPostFlowResult:
    risk_snapshot: dict[str, Any]
    log_items: list[tuple[str, str]]


def build_snapshot_post_flow_result(
    *,
    snapshot_flow: SnapshotBuildFlowResult,
    state: str,
    phase: str,
    ctx: dict[str, Any],
    trigger_entity: str,
    source_name: str,
    event_name: str,
    old_value: Any,
    new_value: Any,
    apply_temperature_policy: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
) -> SnapshotPostFlowResult:
    """Apply snapshot post-processing and assemble final risk snapshot payload."""
    temperature_summary = apply_temperature_policy(
        snapshot_flow.temperature_states,
        snapshot_flow.temperature_summary,
    )

    return SnapshotPostFlowResult(
        risk_snapshot=build_risk_snapshot_payload(
            state=state,
            phase=phase,
            ctx=ctx,
            trigger_entity=trigger_entity,
            source_name=source_name,
            event_name=event_name,
            old_value=old_value,
            new_value=new_value,
            smoke_states=snapshot_flow.smoke_states,
            gas_states=snapshot_flow.gas_states,
            temperature_states=snapshot_flow.temperature_states,
            smoke_summary=snapshot_flow.smoke_summary,
            gas_summary=snapshot_flow.gas_summary,
            temperature_summary=temperature_summary,
        ),
        log_items=[
            ("DEBUG", message)
            for message in snapshot_flow.non_numeric_temperature_log_lines
        ],
    )
