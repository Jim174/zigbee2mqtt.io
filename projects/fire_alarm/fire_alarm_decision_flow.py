"""Decision orchestration flow helpers for fire alarm controller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from .fire_alarm_decision import (
    active_fault_sources,
    decide_next_state,
    should_block_clear_due_to_fault,
    should_hold_current_state,
)


@dataclass(frozen=True)
class DecisionFlowResult:
    next_state: str
    log_message: str | None
    log_level: str | None


def run_decision_flow(
    *,
    current_state: str,
    risk_snapshot: dict[str, Any],
    active_faults: dict[str, Any],
    last_transition_ts: datetime | None,
    clear_hold_seconds: int,
    risk_priority_fn: Callable[[str], int],
) -> DecisionFlowResult:
    """Resolve proposed state and apply controller-level guard rails."""
    summary = risk_snapshot.get("summary", {})
    proposed_state = decide_next_state(summary)

    if should_block_clear_due_to_fault(
        current_state=current_state,
        proposed_state=proposed_state,
        active_faults=active_faults,
    ):
        return DecisionFlowResult(
            next_state=current_state,
            log_message=(
                "proposed clear blocked by active fault: keep state=%s proposed=%s active_sources=%s"
                % (current_state, proposed_state, sorted(active_fault_sources(active_faults)))
            ),
            log_level="WARNING",
        )

    if should_hold_current_state(
        current_state=current_state,
        proposed_state=proposed_state,
        last_transition_ts=last_transition_ts,
        clear_hold_seconds=clear_hold_seconds,
        risk_priority_fn=risk_priority_fn,
    ):
        return DecisionFlowResult(
            next_state=current_state,
            log_message=(
                "anti-flap downgrade hold: keep state=%s over proposed=%s for %ss"
                % (current_state, proposed_state, clear_hold_seconds)
            ),
            log_level="DEBUG",
        )

    return DecisionFlowResult(
        next_state=proposed_state,
        log_message=None,
        log_level=None,
    )
