"""Temperature policy helpers for fire alarm controller."""

from __future__ import annotations

from time import monotonic
from typing import Any, Callable


def build_temperature_tracker() -> dict[str, dict[str, Any]]:
    return {
        "warning_since_by_entity": {},
        "alarm_since_by_entity": {},
        "warning_active_by_entity": {},
        "alarm_active_by_entity": {},
    }


def apply_temperature_policy(
    *,
    temperature_states: dict[str, Any],
    base_summary: dict[str, Any],
    temp_tracker: dict[str, dict[str, Any]],
    temp_warning_threshold: float,
    temp_alarm_threshold: float,
    temp_warning_hold_sec: int,
    temp_alarm_hold_sec: int,
    temp_warning_clear_threshold: float,
    temp_alarm_clear_threshold: float,
    is_unavailable: Callable[[Any], bool],
    to_float: Callable[[Any], float | None],
    log: Callable[[str], None],
) -> dict[str, Any]:
    """Apply first-pass hold+hysteresis policy on top of raw temperature summary."""
    now_ts = monotonic()
    warning_since_by_entity = temp_tracker.setdefault("warning_since_by_entity", {})
    alarm_since_by_entity = temp_tracker.setdefault("alarm_since_by_entity", {})
    warning_active_by_entity = temp_tracker.setdefault("warning_active_by_entity", {})
    alarm_active_by_entity = temp_tracker.setdefault("alarm_active_by_entity", {})

    for entity_id, raw_value in temperature_states.items():
        if is_unavailable(raw_value):
            continue

        numeric_value = to_float(raw_value)
        if numeric_value is None:
            continue

        alarm_active = bool(alarm_active_by_entity.get(entity_id, False))
        warning_active = bool(warning_active_by_entity.get(entity_id, False))

        if alarm_active and numeric_value < temp_alarm_clear_threshold:
            alarm_active_by_entity[entity_id] = False
            alarm_since_by_entity[entity_id] = None
            log(
                "temperature alarm cleared by hysteresis: entity=%s value=%s clear_threshold=%s"
                % (entity_id, numeric_value, temp_alarm_clear_threshold)
            )
            alarm_active = False

        if not alarm_active and numeric_value >= temp_alarm_threshold:
            alarm_since = alarm_since_by_entity.get(entity_id)
            if alarm_since is None:
                alarm_since_by_entity[entity_id] = now_ts
                log(
                    "temperature alarm hold pending: entity=%s value=%s hold=%ss"
                    % (entity_id, numeric_value, temp_alarm_hold_sec)
                )
            elif now_ts - float(alarm_since) >= temp_alarm_hold_sec:
                alarm_active_by_entity[entity_id] = True
                warning_active_by_entity[entity_id] = True
                alarm_active = True
            else:
                log(
                    "temperature alarm hold pending: entity=%s value=%s hold=%ss"
                    % (entity_id, numeric_value, temp_alarm_hold_sec)
                )
        elif numeric_value < temp_alarm_threshold and not alarm_active:
            alarm_since_by_entity[entity_id] = None

        warning_active = bool(warning_active_by_entity.get(entity_id, False))
        if warning_active and not alarm_active and numeric_value < temp_warning_clear_threshold:
            warning_active_by_entity[entity_id] = False
            warning_since_by_entity[entity_id] = None
            log(
                "temperature warning cleared by hysteresis: entity=%s value=%s clear_threshold=%s"
                % (entity_id, numeric_value, temp_warning_clear_threshold)
            )
            warning_active = False

        if not warning_active and not alarm_active and numeric_value >= temp_warning_threshold:
            warning_since = warning_since_by_entity.get(entity_id)
            if warning_since is None:
                warning_since_by_entity[entity_id] = now_ts
                log(
                    "temperature warning hold pending: entity=%s value=%s hold=%ss"
                    % (entity_id, numeric_value, temp_warning_hold_sec)
                )
            elif now_ts - float(warning_since) >= temp_warning_hold_sec:
                warning_active_by_entity[entity_id] = True
            else:
                log(
                    "temperature warning hold pending: entity=%s value=%s hold=%ss"
                    % (entity_id, numeric_value, temp_warning_hold_sec)
                )
        elif numeric_value < temp_warning_threshold and not warning_active:
            warning_since_by_entity[entity_id] = None

    alarm_active_entities = sorted(
        [entity_id for entity_id, active in alarm_active_by_entity.items() if active]
    )
    warning_active_entities = sorted(
        [entity_id for entity_id, active in warning_active_by_entity.items() if active]
    )

    base_alarm_entities = list(base_summary.get("active_entities", []))
    merged_alarm_entities = sorted(set(base_alarm_entities) | set(alarm_active_entities))
    base_warning_entities = list(base_summary.get("warning_active_entities", []))
    merged_warning_entities = sorted(
        set(base_warning_entities) | set(warning_active_entities) | set(merged_alarm_entities)
    )

    adjusted = dict(base_summary)
    adjusted["active_entities"] = merged_alarm_entities
    adjusted["warning_active_entities"] = merged_warning_entities
    adjusted["any_alarm"] = bool(base_summary.get("any_alarm")) or bool(merged_alarm_entities)
    adjusted["any_warning"] = bool(base_summary.get("any_warning")) or bool(merged_warning_entities)
    return adjusted
