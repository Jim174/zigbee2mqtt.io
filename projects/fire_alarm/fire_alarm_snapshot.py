"""Pure snapshot summarization helpers for fire alarm controller."""

from __future__ import annotations

from typing import Any, Callable


def summarize_binary_source(
    states: dict[str, Any],
    is_alarm_like: Callable[[Any], bool],
    is_unavailable: Callable[[Any], bool],
) -> dict[str, Any]:
    active_entities = [
        entity_id
        for entity_id, value in states.items()
        if is_alarm_like(value)
    ]
    return {
        "any_alarm": bool(active_entities),
        "any_unavailable": any(is_unavailable(value) for value in states.values()),
        "active_entities": active_entities,
    }


def summarize_temperature_source(
    states: dict[str, Any],
    *,
    temp_warning_threshold: float,
    temp_alarm_threshold: float,
    to_float: Callable[[Any], float | None],
    is_unavailable: Callable[[Any], bool],
) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    max_value: float | None = None
    any_unavailable = False
    active_entities: list[str] = []
    non_numeric_entries: list[tuple[str, Any]] = []

    for entity_id, raw_value in states.items():
        if is_unavailable(raw_value):
            any_unavailable = True
            continue

        numeric_value = to_float(raw_value)
        if numeric_value is not None:
            if max_value is None or numeric_value > max_value:
                max_value = numeric_value

            if numeric_value >= temp_alarm_threshold:
                active_entities.append(entity_id)
            continue

        non_numeric_entries.append((entity_id, raw_value))

    any_alarm = bool(active_entities)
    any_warning = bool(
        max_value is not None
        and temp_warning_threshold <= max_value < temp_alarm_threshold
    )

    return {
        "max_value": max_value,
        "any_warning": any_warning,
        "any_alarm": any_alarm,
        "any_unavailable": any_unavailable,
        "active_entities": active_entities,
    }, non_numeric_entries
