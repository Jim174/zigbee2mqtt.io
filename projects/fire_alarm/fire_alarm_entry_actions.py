"""Entry-action policy builder for fire alarm controller."""

from __future__ import annotations

from typing import Any

from . import fire_alarm_constants as c
from .fire_alarm_notifications import (
    should_send_notify_for_state,
    should_send_tts_for_state,
)


def _cmd(
    channel: str,
    action: str,
    payload: dict[str, Any] | None = None,
    *,
    mark: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "channel": channel,
        "action": action,
        "payload": payload or {},
    }
    if mark:
        data["mark"] = mark
    return data


def build_entry_action_plan(
    *,
    state: str,
    risk_snapshot: dict[str, Any],
    ctx: dict[str, Any],
    notify_cooldown_sec: int,
    tts_cooldown_sec: int,
) -> dict[str, Any]:
    commands: list[dict[str, Any]] = []

    if state == c.STATE_DISABLED:
        commands.append(_cmd("light", "set_disabled", {"reason": "state_disabled"}))
        commands.append(_cmd("beacon", "off", {"reason": "state_disabled"}))
        commands.append(_cmd("buzzer", "off", {"reason": "state_disabled"}))
        return {"known_state": True, "commands": commands}

    if state == c.STATE_NORMAL:
        commands.append(_cmd("light", "clear", {"reason": "state_normal"}))
        commands.append(_cmd("beacon", "off", {"reason": "state_normal"}))
        commands.append(_cmd("buzzer", "off", {"reason": "state_normal"}))
        return {"known_state": True, "commands": commands}

    if state == c.STATE_OBSERVE:
        commands.append(_cmd("light", "set_info", {"message": "observe"}))
        return {"known_state": True, "commands": commands}

    if state == c.STATE_PREALARM:
        commands.append(_cmd("light", "set_warning", {"message": "prealarm"}))
        if should_send_notify_for_state(
            ctx=ctx,
            state=state,
            risk_snapshot=risk_snapshot,
            notify_cooldown_sec=notify_cooldown_sec,
        ):
            commands.append(
                _cmd("notify", "send", {"message": "Fire risk elevated"}, mark="notify")
            )
        return {"known_state": True, "commands": commands}

    if state == c.STATE_ALARM:
        commands.append(_cmd("beacon", "on", {"pattern": "alarm"}))
        commands.append(_cmd("buzzer", "on", {"pattern": "alarm"}))
        if should_send_tts_for_state(
            ctx=ctx,
            state=state,
            risk_snapshot=risk_snapshot,
            tts_cooldown_sec=tts_cooldown_sec,
        ):
            commands.append(
                _cmd("tts", "speak", {"message": "Fire alarm triggered"}, mark="tts")
            )
        if should_send_notify_for_state(
            ctx=ctx,
            state=state,
            risk_snapshot=risk_snapshot,
            notify_cooldown_sec=notify_cooldown_sec,
        ):
            commands.append(
                _cmd("notify", "send", {"message": "Fire alarm triggered"}, mark="notify")
            )
        return {"known_state": True, "commands": commands}

    if state == c.STATE_CRITICAL:
        commands.append(_cmd("beacon", "on", {"pattern": "critical"}))
        commands.append(_cmd("buzzer", "on", {"pattern": "critical"}))
        if should_send_tts_for_state(
            ctx=ctx,
            state=state,
            risk_snapshot=risk_snapshot,
            tts_cooldown_sec=tts_cooldown_sec,
        ):
            commands.append(
                _cmd("tts", "speak", {"message": "Critical fire emergency"}, mark="tts")
            )
        if should_send_notify_for_state(
            ctx=ctx,
            state=state,
            risk_snapshot=risk_snapshot,
            notify_cooldown_sec=notify_cooldown_sec,
        ):
            commands.append(
                _cmd("notify", "send", {"message": "Critical fire emergency"}, mark="notify")
            )
        return {"known_state": True, "commands": commands}

    return {"known_state": False, "commands": commands}
