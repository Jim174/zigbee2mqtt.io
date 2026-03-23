from __future__ import annotations

from typing import Any, Callable

import pytest

from projects.fire_alarm import fire_alarm_constants as c
from projects.fire_alarm.fire_alarm import FireAlarm


@pytest.fixture(autouse=True)
def patch_primary_state_constants(monkeypatch: pytest.MonkeyPatch):
    values = {
        "STATE_DISABLED": "disabled",
        "STATE_NORMAL": "normal",
        "STATE_OBSERVE": "observe",
        "STATE_PREALARM": "prealarm",
        "STATE_ALARM": "alarm",
        "STATE_CRITICAL": "critical",
        "DEFAULT_ESCALATION_PHASE_MAP": {
            "disabled": c.PHASE_OBSERVE,
            "normal": c.PHASE_OBSERVE,
            "observe": c.PHASE_OBSERVE,
            "prealarm": c.PHASE_VERIFY,
            "alarm": c.PHASE_ALERT,
            "critical": c.PHASE_EMERGENCY,
        },
        "STATE_PRIORITY": {
            "normal": 0,
            "observe": 1,
            "prealarm": 2,
            "alarm": 3,
            "critical": 4,
        },
    }
    for name, value in values.items():
        monkeypatch.setattr(c, name, value, raising=False)
    yield


class TestRecorder:
    def __init__(self) -> None:
        self.logs: list[tuple[str, str]] = []
        self.listen_state_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.listen_event_calls: list[tuple[str, str]] = []
        self.call_service_calls: list[tuple[str, dict[str, Any]]] = []
        self.state_store: dict[str, Any] = {}

    def log(self, message: str, level: str = "INFO") -> None:
        self.logs.append((level, message))

    def get_state(self, entity_id: str) -> Any:
        return self.state_store.get(entity_id)

    def call_service(self, service: str, **data: Any) -> None:
        self.call_service_calls.append((service, data))

    def listen_state(self, callback: Callable[..., Any], entity_id: str, **kwargs: Any) -> None:
        self.listen_state_calls.append((callback.__name__, entity_id, kwargs))

    def listen_event(self, callback: Callable[..., Any], event_name: str) -> None:
        self.listen_event_calls.append((callback.__name__, event_name))


@pytest.fixture
def build_test_controller():
    def _build(
        args: dict[str, Any] | None = None,
        state_store: dict[str, Any] | None = None,
    ) -> tuple[FireAlarm, TestRecorder]:
        controller = FireAlarm()
        recorder = TestRecorder()
        recorder.state_store.update(state_store or {})

        controller.args = args or {}
        controller.log = recorder.log
        controller.get_state = recorder.get_state
        controller.call_service = recorder.call_service
        controller.listen_state = recorder.listen_state
        controller.listen_event = recorder.listen_event
        return controller, recorder

    return _build
