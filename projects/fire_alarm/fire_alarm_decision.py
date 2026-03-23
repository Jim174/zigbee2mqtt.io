"""State decision helpers for fire alarm controller."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from . import fire_alarm_constants as c


def is_alarm_state(state: str) -> bool:
    return state in {c.STATE_PREALARM, c.STATE_ALARM, c.STATE_CRITICAL}


def active_fault_sources(active_faults: dict[str, Any]) -> set[str]:
    sources: set[str] = set()
    for entry in active_faults.values():
        source_name = str(entry.get("source", "")).strip().lower()
        if source_name:
            sources.add(source_name)
    return sources


def has_critical_active_faults(active_faults: dict[str, Any]) -> bool:
    """First-pass critical fault definition for risk-plane interaction."""
    sources = active_fault_sources(active_faults)
    return "smoke" in sources or "gas" in sources


def should_block_clear_due_to_fault(
    *,
    current_state: str,
    proposed_state: str,
    active_faults: dict[str, Any],
) -> bool:
    """Block optimistic clear-to-normal when alarm-like state has critical source faults."""
    if not is_alarm_state(current_state):
        return False
    if proposed_state != c.STATE_NORMAL:
        return False
    return has_critical_active_faults(active_faults)


def should_hold_current_state(
    *,
    current_state: str,
    proposed_state: str,
    last_transition_ts: datetime | None,
    clear_hold_seconds: int,
    risk_priority_fn: Callable[[str], int],
    now_utc: Callable[[], datetime] | None = None,
) -> bool:
    """Minimal anti-flap: hold brief downgrades, never block upgrades."""
    now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    current_priority = risk_priority_fn(current_state)
    proposed_priority = risk_priority_fn(proposed_state)

    if proposed_priority >= current_priority:
        return False

    if last_transition_ts is None:
        return False

    elapsed = now_utc() - last_transition_ts
    return elapsed.total_seconds() < clear_hold_seconds


def decide_next_state(summary: dict[str, Any]) -> str:
    """Map snapshot summary to a proposed primary state before guards."""
    smoke = summary.get("smoke", {})
    gas = summary.get("gas", {})
    temperature = summary.get("temperature", {})

    smoke_alarm = bool(smoke.get("any_alarm"))
    gas_alarm = bool(gas.get("any_alarm"))
    temp_warning = bool(temperature.get("any_warning"))
    temp_alarm = bool(temperature.get("any_alarm"))

    if temp_alarm and (smoke_alarm or gas_alarm):
        return c.STATE_CRITICAL
    if smoke_alarm or gas_alarm:
        return c.STATE_ALARM
    if temp_alarm:
        return c.STATE_PREALARM
    if temp_warning:
        return c.STATE_OBSERVE
    return c.STATE_NORMAL
