from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NotificationAction:
    channel: str
    severity: str
    message_key: str
    audience_mode: str | None
    payload: dict[str, Any]
    suppressed: bool = False


@dataclass(frozen=True)
class MarkUpdateSet:
    notify_state_marks: dict[str, float | None] = field(default_factory=dict)
    tts_state_marks: dict[str, float | None] = field(default_factory=dict)
    fault_marks: dict[str, float | None] = field(default_factory=dict)
    fault_clear_marks: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class NotificationActionPlan:
    state: str
    phase: str
    notification_actions: list[NotificationAction] = field(default_factory=list)
    mark_updates: MarkUpdateSet = field(default_factory=MarkUpdateSet)


__all__ = [
    "MarkUpdateSet",
    "NotificationAction",
    "NotificationActionPlan",
]
