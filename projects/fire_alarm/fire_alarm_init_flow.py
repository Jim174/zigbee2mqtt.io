"""Initialization flow helpers for fire alarm controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import fire_alarm_constants as c
from .fire_alarm_init import build_temperature_config
from .fire_alarm_rules import to_bool


@dataclass(frozen=True)
class InitializationFlowResult:
    state: str
    escalation_phase: str
    last_transition_ts: None
    temp_warning_threshold: float
    temp_alarm_threshold: float
    temp_warning_hold_sec: int
    temp_alarm_hold_sec: int
    temp_warning_clear_threshold: float
    temp_alarm_clear_threshold: float
    temperature_warning_messages: list[str]
    clear_hold_seconds: int
    notify_cooldown_sec: int
    tts_cooldown_sec: int
    fault_notify_enabled: bool
    fault_notify_cooldown_sec: int
    fault_clear_notify_enabled: bool
    run_initial_entry_actions: bool
    control_event_name: str
    initial_entry_snapshot: dict[str, Any] | None
    initial_state_warning_log: tuple[str, str] | None


def build_initialization_flow_result(
    *,
    args: dict[str, Any],
    primary_states: set[str],
    default_escalation_phase_map: dict[str, str],
    fallback_phase: str,
) -> InitializationFlowResult:
    """Build validated runtime bootstrap/config values for controller initialization."""
    requested_initial_state = args.get("initial_state", c.STATE_NORMAL)
    initial_state_warning_log: tuple[str, str] | None = None
    if requested_initial_state not in primary_states:
        initial_state_warning_log = (
            "WARNING",
            "invalid initial_state=%s, fallback to %s" % (requested_initial_state, c.STATE_NORMAL),
        )
        requested_initial_state = c.STATE_NORMAL

    temperature_config = build_temperature_config(args)
    run_initial_entry_actions = to_bool(args.get("run_initial_entry_actions", False))

    return InitializationFlowResult(
        state=requested_initial_state,
        escalation_phase=default_escalation_phase_map.get(
            requested_initial_state,
            fallback_phase,
        ),
        last_transition_ts=None,
        temp_warning_threshold=float(temperature_config["temp_warning_threshold"]),
        temp_alarm_threshold=float(temperature_config["temp_alarm_threshold"]),
        temp_warning_hold_sec=int(temperature_config["temp_warning_hold_sec"]),
        temp_alarm_hold_sec=int(temperature_config["temp_alarm_hold_sec"]),
        temp_warning_clear_threshold=float(temperature_config["temp_warning_clear_threshold"]),
        temp_alarm_clear_threshold=float(temperature_config["temp_alarm_clear_threshold"]),
        temperature_warning_messages=list(temperature_config["warning_messages"]),
        clear_hold_seconds=int(args.get("clear_hold_seconds", 30)),
        notify_cooldown_sec=int(args.get("notify_cooldown_sec", 60)),
        tts_cooldown_sec=int(args.get("tts_cooldown_sec", 60)),
        fault_notify_enabled=to_bool(args.get("fault_notify_enabled", True)),
        fault_notify_cooldown_sec=int(args.get("fault_notify_cooldown_sec", 300)),
        fault_clear_notify_enabled=to_bool(args.get("fault_clear_notify_enabled", False)),
        run_initial_entry_actions=run_initial_entry_actions,
        control_event_name=args.get("control_event_name", "fire_alarm_control"),
        initial_entry_snapshot=(
            {
                "trigger": {
                    "entity_id": "__init__",
                    "source": "system",
                    "event": "initial_sync",
                }
            }
            if run_initial_entry_actions
            else None
        ),
        initial_state_warning_log=initial_state_warning_log,
    )
