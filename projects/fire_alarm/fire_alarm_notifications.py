"""Notification/TTS gating and cooldown helpers for fire alarm controller."""

from __future__ import annotations

from time import monotonic
from typing import Any

from .fire_alarm_incident import incident_matches_ack, incident_matches_silence


def is_repeat_sync_event(risk_snapshot: dict[str, Any]) -> bool:
    trigger = risk_snapshot.get("trigger", {})
    return str(trigger.get("source", "")).lower() in {"control", "system"}


def is_true_state_entry_event(state: str, risk_snapshot: dict[str, Any]) -> bool:
    if is_repeat_sync_event(risk_snapshot):
        return False
    return risk_snapshot.get("state") != state


def notify_cooldown_seconds_for_state(state: str, notify_cooldown_sec: int) -> int:
    del state
    return max(0, notify_cooldown_sec)


def tts_cooldown_seconds_for_state(state: str, tts_cooldown_sec: int) -> int:
    del state
    return max(0, tts_cooldown_sec)


def is_notify_cooldown_active(ctx: dict[str, Any], state: str, notify_cooldown_sec: int) -> bool:
    cooldown_sec = notify_cooldown_seconds_for_state(state, notify_cooldown_sec)
    if cooldown_sec <= 0:
        return False

    last_sent = ctx.get("last_notify_ts_by_state", {}).get(state)
    if last_sent is None:
        return False

    return (monotonic() - last_sent) < cooldown_sec


def is_tts_cooldown_active(ctx: dict[str, Any], state: str, tts_cooldown_sec: int) -> bool:
    cooldown_sec = tts_cooldown_seconds_for_state(state, tts_cooldown_sec)
    if cooldown_sec <= 0:
        return False

    last_sent = ctx.get("last_tts_ts_by_state", {}).get(state)
    if last_sent is None:
        return False

    return (monotonic() - last_sent) < cooldown_sec


def mark_notify_sent(ctx: dict[str, Any], state: str) -> None:
    ctx.setdefault("last_notify_ts_by_state", {})[state] = monotonic()


def mark_tts_sent(ctx: dict[str, Any], state: str) -> None:
    ctx.setdefault("last_tts_ts_by_state", {})[state] = monotonic()


def should_send_notify_for_state(
    *,
    ctx: dict[str, Any],
    state: str,
    risk_snapshot: dict[str, Any],
    notify_cooldown_sec: int,
) -> bool:
    if incident_matches_silence(ctx):
        return False
    if incident_matches_ack(ctx) and is_repeat_sync_event(risk_snapshot):
        return False
    if not is_true_state_entry_event(state, risk_snapshot) and is_notify_cooldown_active(
        ctx,
        state,
        notify_cooldown_sec,
    ):
        return False
    return True


def should_send_tts_for_state(
    *,
    ctx: dict[str, Any],
    state: str,
    risk_snapshot: dict[str, Any],
    tts_cooldown_sec: int,
) -> bool:
    if incident_matches_silence(ctx):
        return False
    if incident_matches_ack(ctx) and is_repeat_sync_event(risk_snapshot):
        return False
    if not is_true_state_entry_event(state, risk_snapshot) and is_tts_cooldown_active(
        ctx,
        state,
        tts_cooldown_sec,
    ):
        return False
    return True
