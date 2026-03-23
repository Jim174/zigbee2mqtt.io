"""Sensor cache/store helpers for fire alarm controller."""

from __future__ import annotations

from typing import Any, Callable


def initialize_sensor_cache(
    *,
    sensor_entity_ids: dict[str, list[str]],
    sensor_cache: dict[str, dict[str, Any]],
    get_state: Callable[[str], Any],
) -> None:
    """Prime first-pass sensor cache from Home Assistant state."""
    for source_name, entity_ids in sensor_entity_ids.items():
        source_cache = sensor_cache.setdefault(source_name, {})
        for entity_id in entity_ids:
            source_cache[entity_id] = get_state(entity_id)


def update_sensor_cache_entry(
    *,
    sensor_cache: dict[str, dict[str, Any]],
    source_name: str,
    entity_id: str,
    value: Any,
    log_warning: Callable[[str], None],
) -> None:
    """Update one cache entry with latest callback value."""
    source_cache = sensor_cache.get(source_name)
    if source_cache is None:
        log_warning(
            "sensor cache source missing, create dynamically: source=%s entity=%s"
            % (source_name, entity_id)
        )
        source_cache = {}
        sensor_cache[source_name] = source_cache

    source_cache[entity_id] = value


def collect_sensor_states(
    *,
    sensor_cache: dict[str, dict[str, Any]],
    sensor_entity_ids: dict[str, list[str]],
    source_name: str,
    get_state: Callable[[str], Any],
    log_warning: Callable[[str], None],
) -> dict[str, Any]:
    """Collect latest raw states for one sensor source with fallback."""
    source_cache = sensor_cache.get(source_name)
    if source_cache is not None:
        return dict(source_cache)

    log_warning("sensor cache missing source=%s, fallback to direct get_state" % source_name)
    states: dict[str, Any] = {}
    for entity_id in sensor_entity_ids.get(source_name, []):
        states[entity_id] = get_state(entity_id)
    return states
