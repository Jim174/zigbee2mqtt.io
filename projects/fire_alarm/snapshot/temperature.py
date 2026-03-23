from __future__ import annotations

from dataclasses import asdict
from time import monotonic
from typing import Any, Mapping

from ..fire_alarm_rules import to_float
from .models import TemperatureSnapshot, TemperatureTrackerState


OBSERVE_THRESHOLD_C = 40.0
PREALARM_THRESHOLD_C = 45.0
ALARM_THRESHOLD_C = 50.0
CRITICAL_THRESHOLD_C = 60.0
STOVE_REMINDER_THRESHOLD_C = 60.0
RATE_OF_RISE_DELTA_C = 10.0
RATE_OF_RISE_WINDOW_SEC = 180.0
SEVERITY_ORDER = ("observe", "prealarm", "alarm", "critical")


def _is_unavailable(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in {"unavailable", "unknown", "none", "null", ""}


def _copy_tracker(tracker_state: TemperatureTrackerState | None) -> dict[str, Any]:
    if tracker_state is None:
        tracker_state = TemperatureTrackerState()
    return asdict(tracker_state)


def _max_numeric(states: Mapping[str, Any]) -> float | None:
    values = [to_float(raw_value) for raw_value in states.values()]
    numeric_values = [value for value in values if value is not None]
    if not numeric_values:
        return None
    return max(numeric_values)


def _severity_rank(severity: str | None) -> int:
    if severity is None:
        return -1
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return -1


def _max_severity(severities: list[str | None]) -> str | None:
    ordered = [severity for severity in severities if severity is not None]
    if not ordered:
        return None
    return max(ordered, key=_severity_rank)


def _classify_fire_monitor_temperature(
    *,
    entity_id: str,
    numeric_value: float,
    domain: str,
    tracker: dict[str, Any],
    now_ts: float,
) -> str:
    last_value_key = f"{domain}_last_value_by_entity"
    last_ts_key = f"{domain}_last_ts_by_entity"
    last_value = tracker.setdefault(last_value_key, {}).get(entity_id)
    last_ts = tracker.setdefault(last_ts_key, {}).get(entity_id)

    severity = None
    if numeric_value > CRITICAL_THRESHOLD_C:
        severity = "critical"
    elif numeric_value > ALARM_THRESHOLD_C:
        severity = "alarm"
    elif numeric_value > PREALARM_THRESHOLD_C:
        severity = "prealarm"
    elif numeric_value > OBSERVE_THRESHOLD_C:
        severity = "observe"

    if (
        last_value is not None
        and last_ts is not None
        and now_ts >= float(last_ts)
        and (now_ts - float(last_ts)) <= RATE_OF_RISE_WINDOW_SEC
        and (numeric_value - float(last_value)) >= RATE_OF_RISE_DELTA_C
    ):
        severity = "critical"

    tracker[last_value_key][entity_id] = numeric_value
    tracker[last_ts_key][entity_id] = now_ts
    return severity or ""


def _record_severity_state(
    *,
    domain: str,
    entity_id: str,
    severity: str,
    tracker: dict[str, Any],
) -> None:
    for level in SEVERITY_ORDER:
        active_key = f"{domain}_{level}_active_by_entity"
        since_key = f"{domain}_{level}_since_by_entity"
        is_active = level == severity
        tracker.setdefault(active_key, {})[entity_id] = is_active
        tracker.setdefault(since_key, {})[entity_id] = monotonic() if is_active else None


def build_temperature_snapshot(
    *,
    stove_states: Mapping[str, Any] | None = None,
    environment_states: Mapping[str, Any] | None = None,
    other_room_states: Mapping[str, Any] | None = None,
    tracker_state: TemperatureTrackerState | None = None,
    now_ts: float | None = None,
) -> TemperatureSnapshot:
    now_ts = monotonic() if now_ts is None else now_ts
    stove_states = dict(stove_states or {})
    environment_states = dict(environment_states or {})
    other_room_states = dict(other_room_states or {})
    tracker = _copy_tracker(tracker_state)

    stove_reminder_entities: list[str] = []
    environment_entities_by_severity: dict[str, list[str]] = {level: [] for level in SEVERITY_ORDER}
    other_room_entities_by_severity: dict[str, list[str]] = {level: [] for level in SEVERITY_ORDER}
    non_numeric_entities: list[str] = []

    for entity_id, raw_value in stove_states.items():
        if _is_unavailable(raw_value):
            tracker.setdefault("stove_reminder_active_by_entity", {})[entity_id] = False
            tracker.setdefault("stove_reminder_since_by_entity", {})[entity_id] = None
            continue
        numeric_value = to_float(raw_value)
        if numeric_value is None:
            non_numeric_entities.append(entity_id)
            tracker.setdefault("stove_reminder_active_by_entity", {})[entity_id] = False
            tracker.setdefault("stove_reminder_since_by_entity", {})[entity_id] = None
            continue
        if numeric_value >= STOVE_REMINDER_THRESHOLD_C:
            stove_reminder_entities.append(entity_id)
            tracker.setdefault("stove_reminder_active_by_entity", {})[entity_id] = True
            tracker.setdefault("stove_reminder_since_by_entity", {})[entity_id] = now_ts
        else:
            tracker.setdefault("stove_reminder_active_by_entity", {})[entity_id] = False
            tracker.setdefault("stove_reminder_since_by_entity", {})[entity_id] = None

    for domain, states, entities_by_severity in (
        ("environment", environment_states, environment_entities_by_severity),
        ("other_room", other_room_states, other_room_entities_by_severity),
    ):
        for entity_id, raw_value in states.items():
            if _is_unavailable(raw_value):
                for level in SEVERITY_ORDER:
                    tracker.setdefault(f"{domain}_{level}_active_by_entity", {})[entity_id] = False
                    tracker.setdefault(f"{domain}_{level}_since_by_entity", {})[entity_id] = None
                continue
            numeric_value = to_float(raw_value)
            if numeric_value is None:
                non_numeric_entities.append(entity_id)
                for level in SEVERITY_ORDER:
                    tracker.setdefault(f"{domain}_{level}_active_by_entity", {})[entity_id] = False
                    tracker.setdefault(f"{domain}_{level}_since_by_entity", {})[entity_id] = None
                continue
            severity = _classify_fire_monitor_temperature(
                entity_id=entity_id,
                numeric_value=numeric_value,
                domain=domain,
                tracker=tracker,
                now_ts=now_ts,
            )
            if severity:
                entities_by_severity[severity].append(entity_id)
                _record_severity_state(
                    domain=domain,
                    entity_id=entity_id,
                    severity=severity,
                    tracker=tracker,
                )
            else:
                for level in SEVERITY_ORDER:
                    tracker.setdefault(f"{domain}_{level}_active_by_entity", {})[entity_id] = False
                    tracker.setdefault(f"{domain}_{level}_since_by_entity", {})[entity_id] = None

    environment_highest = _max_severity(
        [level for level in SEVERITY_ORDER if environment_entities_by_severity[level]]
    )
    other_room_highest = _max_severity(
        [level for level in SEVERITY_ORDER if other_room_entities_by_severity[level]]
    )

    return TemperatureSnapshot(
        stove_entities=stove_states,
        environment_entities=environment_states,
        other_room_entities=other_room_states,
        stove_max=_max_numeric(stove_states),
        environment_max=_max_numeric(environment_states),
        other_room_max=_max_numeric(other_room_states),
        stove_reminder_active=bool(stove_reminder_entities),
        stove_reminder_entities=sorted(stove_reminder_entities),
        environment_highest_severity=environment_highest,
        other_room_highest_severity=other_room_highest,
        environment_observe_entities=sorted(environment_entities_by_severity["observe"]),
        environment_prealarm_entities=sorted(environment_entities_by_severity["prealarm"]),
        environment_alarm_entities=sorted(environment_entities_by_severity["alarm"]),
        environment_critical_entities=sorted(environment_entities_by_severity["critical"]),
        other_room_observe_entities=sorted(other_room_entities_by_severity["observe"]),
        other_room_prealarm_entities=sorted(other_room_entities_by_severity["prealarm"]),
        other_room_alarm_entities=sorted(other_room_entities_by_severity["alarm"]),
        other_room_critical_entities=sorted(other_room_entities_by_severity["critical"]),
        non_numeric_entities=sorted(set(non_numeric_entities)),
        tracker_state=TemperatureTrackerState(**tracker),
    )
