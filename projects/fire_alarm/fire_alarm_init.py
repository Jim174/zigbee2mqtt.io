"""Initialization data builders for fire alarm controller."""

from __future__ import annotations

from typing import Any


def _default_light_effects() -> dict[str, dict[str, Any]]:
    return {
        "valve_open_feedback": {
            "mode": "pulse",
            "color": "yellow",
            "repeat": 2,
            "high_brightness": 255,
            "low_brightness": 32,
            "fade_in_ms": 120,
            "fade_out_ms": 180,
            "hold_ms": 180,
            "gap_ms": 220,
        },
        "valve_close_feedback": {
            "mode": "pulse",
            "color": "green",
            "repeat": 2,
            "high_brightness": 255,
            "low_brightness": 24,
            "fade_in_ms": 120,
            "fade_out_ms": 180,
            "hold_ms": 180,
            "gap_ms": 220,
        },
        "observe": {
            "mode": "pulse",
            "color": "white",
            "repeat": 0,
            "high_brightness": 160,
            "low_brightness": 24,
            "fade_in_ms": 300,
            "fade_out_ms": 300,
            "hold_ms": 250,
            "gap_ms": 500,
        },
        "prealarm": {
            "mode": "pulse",
            "color": "red",
            "repeat": 0,
            "high_brightness": 200,
            "low_brightness": 24,
            "fade_in_ms": 220,
            "fade_out_ms": 220,
            "hold_ms": 220,
            "gap_ms": 320,
        },
        "alarm": {
            "mode": "pulse",
            "colors": ["red", "blue"],
            "repeat": 0,
            "high_brightness": 255,
            "low_brightness": 32,
            "fade_in_ms": 160,
            "fade_out_ms": 160,
            "hold_ms": 180,
            "gap_ms": 180,
        },
        "critical": {
            "mode": "pulse",
            "colors": ["red", "blue"],
            "repeat": 0,
            "high_brightness": 255,
            "low_brightness": 16,
            "fade_in_ms": 120,
            "fade_out_ms": 120,
            "hold_ms": 200,
            "gap_ms": 120,
        },
    }


def build_runtime_context() -> dict[str, Any]:
    """Build default mutable runtime context."""
    return {
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
        "last_notify_ts_by_state": {},
        "last_tts_ts_by_state": {},
        "last_fault_notify_ts_by_key": {},
        "last_fault_clear_notify_ts_by_key": {},
        "active_fault_notified_keys": set(),
        "cleared_fault_notified_keys": set(),
    }


def build_sensor_registry(args: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    """Build sensor entity registry and empty cache layout."""
    sensor_entity_ids: dict[str, list[str]] = {
        "smoke": list(args.get("smoke_sensors", [])),
        "gas": list(args.get("gas_sensors", [])),
        "temperature": list(args.get("temperature_sensors", [])),
    }
    sensor_cache: dict[str, dict[str, Any]] = {
        "smoke": {},
        "gas": {},
        "temperature": {},
    }
    return sensor_entity_ids, sensor_cache


def build_temperature_config(args: dict[str, Any]) -> dict[str, Any]:
    """Build temperature thresholds/holds with same calibration rules."""
    temp_warning_threshold = float(args.get("temperature_warning_threshold", 55.0))
    temp_alarm_threshold = float(args.get("temperature_alarm_threshold", 65.0))
    temp_warning_hold_sec = max(1, int(args.get("temperature_warning_hold_sec", 15)))
    temp_alarm_hold_sec = max(1, int(args.get("temperature_alarm_hold_sec", 10)))
    temp_warning_clear_threshold = float(
        args.get("temperature_warning_clear_threshold", temp_warning_threshold - 2.0)
    )
    temp_alarm_clear_threshold = float(
        args.get("temperature_alarm_clear_threshold", temp_alarm_threshold - 2.0)
    )

    warning_messages: list[str] = []

    if temp_warning_clear_threshold >= temp_warning_threshold:
        warning_messages.append(
            "temperature_warning_clear_threshold=%s must be lower than warning_threshold=%s; auto-adjust"
            % (temp_warning_clear_threshold, temp_warning_threshold)
        )
        temp_warning_clear_threshold = temp_warning_threshold - 0.5

    if temp_alarm_clear_threshold >= temp_alarm_threshold:
        warning_messages.append(
            "temperature_alarm_clear_threshold=%s must be lower than alarm_threshold=%s; auto-adjust"
            % (temp_alarm_clear_threshold, temp_alarm_threshold)
        )
        temp_alarm_clear_threshold = temp_alarm_threshold - 0.5

    return {
        "temp_warning_threshold": temp_warning_threshold,
        "temp_alarm_threshold": temp_alarm_threshold,
        "temp_warning_hold_sec": temp_warning_hold_sec,
        "temp_alarm_hold_sec": temp_alarm_hold_sec,
        "temp_warning_clear_threshold": temp_warning_clear_threshold,
        "temp_alarm_clear_threshold": temp_alarm_clear_threshold,
        "warning_messages": warning_messages,
    }


def build_output_targets(args: dict[str, Any]) -> dict[str, Any]:
    """Build output target channel mapping."""
    return {
        "notify": args.get("notify_target"),
        "tts": args.get("tts_target"),
        "light": args.get("light_target", args.get("message_light_target")),
        "light_effects": args.get("light_effects", _default_light_effects()),
        "beacon": args.get("beacon_target"),
        "buzzer": args.get("buzzer_target"),
        "valve": args.get("valve_target"),
        "exhaust": args.get("exhaust_target"),
    }
