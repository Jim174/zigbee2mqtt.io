"""Fault policy helpers for fire alarm controller."""

from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from typing import Any


def fault_key(source_name: str, entity_id: str) -> str:
    return f"{source_name}:{entity_id}"


def fault_notify_key(source_name: str, entity_id: str, category: str) -> str:
    return f"{source_name}:{entity_id}:{category}"


def build_fault_record_notify_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "message": (
            "Fire alarm sensor fault: source=%s entity=%s category=%s value=%s"
            % (
                entry.get("source"),
                entry.get("entity_id"),
                entry.get("category"),
                entry.get("value"),
            )
        )
    }


def build_fault_clear_notify_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "message": (
            "Fire alarm sensor fault cleared: source=%s entity=%s category=%s last_value=%s"
            % (
                entry.get("source"),
                entry.get("entity_id"),
                entry.get("category"),
                entry.get("value"),
            )
        )
    }


def should_notify_fault(
    *,
    ctx: dict[str, Any],
    fault_notify_key_value: str,
    is_clear: bool,
    fault_clear_notify_enabled: bool,
    fault_notify_enabled: bool,
    fault_notify_cooldown_sec: int,
) -> bool:
    if is_clear and not fault_clear_notify_enabled:
        return False
    if not is_clear and not fault_notify_enabled:
        return False

    active_set_key = "cleared_fault_notified_keys" if is_clear else "active_fault_notified_keys"
    if fault_notify_key_value in ctx.get(active_set_key, set()):
        return False

    ts_key = "last_fault_clear_notify_ts_by_key" if is_clear else "last_fault_notify_ts_by_key"
    cooldown = max(0, fault_notify_cooldown_sec)
    if cooldown <= 0:
        return True

    last_ts = ctx.get(ts_key, {}).get(fault_notify_key_value)
    if last_ts is None:
        return True

    return (monotonic() - last_ts) >= cooldown


def mark_fault_notified(*, ctx: dict[str, Any], fault_notify_key_value: str, is_clear: bool) -> None:
    ts_key = "last_fault_clear_notify_ts_by_key" if is_clear else "last_fault_notify_ts_by_key"
    active_set_key = "cleared_fault_notified_keys" if is_clear else "active_fault_notified_keys"

    ctx.setdefault(ts_key, {})[fault_notify_key_value] = monotonic()
    ctx.setdefault(active_set_key, set()).add(fault_notify_key_value)


def record_sensor_fault(
    *,
    ctx: dict[str, Any],
    entity_id: str,
    source_name: str,
    category: str,
    observed_value: Any,
    fault_notify_enabled: bool,
    fault_clear_notify_enabled: bool,
    fault_notify_cooldown_sec: int,
) -> dict[str, Any] | None:
    entry = {
        "entity_id": entity_id,
        "source": source_name,
        "category": category,
        "value": observed_value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    f_key = fault_key(source_name=source_name, entity_id=entity_id)
    active_faults = ctx.setdefault("active_faults", {})
    existing = active_faults.get(f_key)
    active_faults[f_key] = entry

    notify_key = fault_notify_key(source_name, entity_id, category)
    if existing is None:
        ctx.setdefault("active_fault_notified_keys", set()).discard(notify_key)
        ctx.setdefault("cleared_fault_notified_keys", set()).discard(notify_key)

    if not should_notify_fault(
        ctx=ctx,
        fault_notify_key_value=notify_key,
        is_clear=False,
        fault_clear_notify_enabled=fault_clear_notify_enabled,
        fault_notify_enabled=fault_notify_enabled,
        fault_notify_cooldown_sec=fault_notify_cooldown_sec,
    ):
        return None

    return {
        "fault_notify_key": notify_key,
        "payload": build_fault_record_notify_payload(entry),
        "is_clear": False,
    }


def clear_sensor_fault(
    *,
    ctx: dict[str, Any],
    source_name: str,
    entity_id: str,
    fault_notify_enabled: bool,
    fault_clear_notify_enabled: bool,
    fault_notify_cooldown_sec: int,
) -> dict[str, Any] | None:
    f_key = fault_key(source_name=source_name, entity_id=entity_id)
    active_faults = ctx.setdefault("active_faults", {})
    existing = active_faults.pop(f_key, None)
    if not existing:
        return None

    notify_key = fault_notify_key(
        source_name=source_name,
        entity_id=entity_id,
        category=str(existing.get("category", "unknown")),
    )
    ctx.setdefault("active_fault_notified_keys", set()).discard(notify_key)

    if not should_notify_fault(
        ctx=ctx,
        fault_notify_key_value=notify_key,
        is_clear=True,
        fault_clear_notify_enabled=fault_clear_notify_enabled,
        fault_notify_enabled=fault_notify_enabled,
        fault_notify_cooldown_sec=fault_notify_cooldown_sec,
    ):
        return None

    return {
        "fault_notify_key": notify_key,
        "payload": build_fault_clear_notify_payload(existing),
        "is_clear": True,
    }
