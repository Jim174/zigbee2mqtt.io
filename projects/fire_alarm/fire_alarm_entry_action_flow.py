"""Entry-action flow helpers for fire alarm controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fire_alarm_entry_actions import build_entry_action_plan


@dataclass(frozen=True)
class EntryActionCommand:
    channel: str
    action: str
    payload: dict[str, Any]
    mark: str | None


@dataclass(frozen=True)
class EntryActionFlowResult:
    known_state: bool
    commands: list[EntryActionCommand]


def build_entry_action_flow_result(
    *,
    state: str,
    risk_snapshot: dict[str, Any],
    ctx: dict[str, Any],
    notify_cooldown_sec: int,
    tts_cooldown_sec: int,
) -> EntryActionFlowResult:
    """Build entry action plan and normalize command access for orchestration."""
    plan = build_entry_action_plan(
        state=state,
        risk_snapshot=risk_snapshot,
        ctx=ctx,
        notify_cooldown_sec=notify_cooldown_sec,
        tts_cooldown_sec=tts_cooldown_sec,
    )

    commands = [
        EntryActionCommand(
            channel=str(command.get("channel")),
            action=str(command.get("action")),
            payload=command.get("payload") or {},
            mark=command.get("mark"),
        )
        for command in plan.get("commands", [])
    ]
    return EntryActionFlowResult(
        known_state=bool(plan.get("known_state", False)),
        commands=commands,
    )
