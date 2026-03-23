from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from projects.fire_alarm import fire_alarm_constants as c


Hook = Callable[[Any, Any], None]


@dataclass
class ScenarioStep:
    name: str
    kind: str
    entity: str | None = None
    old: Any = None
    new: Any = None
    source_name: str | None = None
    event_name: str | None = None
    data: dict[str, Any] | None = None
    expected_state: str | None = None
    expected_phase: str | None = None
    expected_ctx: dict[str, Any] | None = None
    expected_new_calls: Sequence[str | tuple[str, dict[str, Any]]] | None = None
    notify_mark_updated: bool | None = None
    notify_mark_state: str | None = None
    tts_mark_updated: bool | None = None
    tts_mark_state: str | None = None
    expect_noop: bool = False
    expect_log_contains: Sequence[str] = field(default_factory=list)
    pre_hook: Hook | None = None
    post_hook: Hook | None = None


class ScenarioRunner:
    def __init__(self, controller: Any, recorder: Any, *, scenario_name: str) -> None:
        self.controller = controller
        self.recorder = recorder
        self.scenario_name = scenario_name
        self.trace: list[dict[str, Any]] = []

    def run(self, steps: Sequence[ScenarioStep]) -> None:
        for index, step in enumerate(steps, start=1):
            self._run_one(index, step)

    def _run_one(self, index: int, step: ScenarioStep) -> None:
        if step.pre_hook is not None:
            step.pre_hook(self.controller, self.recorder)

        prev_state = self.controller._state
        prev_phase = self.controller._escalation_phase
        prev_call_count = len(self.recorder.call_service_calls)
        prev_log_count = len(self.recorder.logs)
        prev_notify = dict(self.controller._ctx.get("last_notify_ts_by_state", {}))
        prev_tts = dict(self.controller._ctx.get("last_tts_ts_by_state", {}))

        try:
            if step.kind == "sensor":
                self.controller._handle_sensor_update(
                    str(step.entity),
                    "state",
                    step.old,
                    step.new,
                    {
                        "source_name": step.source_name or "unknown",
                        "event_name": step.event_name or c.EVENT_SENSOR_UPDATE,
                    },
                )
            elif step.kind == "control":
                self.controller._handle_control_event(
                    step.event_name or "fire_alarm_control",
                    step.data or {},
                    {},
                )
            else:
                raise AssertionError(f"unsupported step kind: {step.kind}")

            if step.post_hook is not None:
                step.post_hook(self.controller, self.recorder)

            new_calls = self.recorder.call_service_calls[prev_call_count:]
            new_logs = self.recorder.logs[prev_log_count:]
            self.trace.append(
                {
                    "index": index,
                    "name": step.name,
                    "kind": step.kind,
                    "state": self.controller._state,
                    "phase": self.controller._escalation_phase,
                    "new_calls": list(new_calls),
                    "new_logs": list(new_logs),
                }
            )

            self._assert_step(step, prev_state, prev_phase, prev_notify, prev_tts, new_calls, new_logs)
        except AssertionError as exc:
            raise AssertionError(f"{exc}\n\n{self.format_trace()}") from exc

    def _assert_step(
        self,
        step: ScenarioStep,
        prev_state: str,
        prev_phase: str,
        prev_notify: dict[str, Any],
        prev_tts: dict[str, Any],
        new_calls: list[tuple[str, dict[str, Any]]],
        new_logs: list[tuple[str, str]],
    ) -> None:
        if step.expected_state is not None:
            assert self.controller._state == step.expected_state, (
                f"step '{step.name}' expected state={step.expected_state} actual={self.controller._state}"
            )
        if step.expected_phase is not None:
            assert self.controller._escalation_phase == step.expected_phase, (
                f"step '{step.name}' expected phase={step.expected_phase} actual={self.controller._escalation_phase}"
            )
        if step.expected_ctx:
            for key, expected_value in step.expected_ctx.items():
                assert self.controller._ctx.get(key) == expected_value, (
                    f"step '{step.name}' expected ctx[{key}]={expected_value!r} actual={self.controller._ctx.get(key)!r}"
                )
        if step.expected_new_calls is not None:
            actual_normalized = []
            expects_tuples = bool(step.expected_new_calls) and isinstance(step.expected_new_calls[0], tuple)
            for call in new_calls:
                actual_normalized.append(call if expects_tuples else call[0])
            assert list(actual_normalized) == list(step.expected_new_calls), (
                f"step '{step.name}' expected new calls={list(step.expected_new_calls)!r} actual={actual_normalized!r}"
            )
        if step.expect_noop:
            assert self.controller._state == prev_state, (
                f"step '{step.name}' expected noop state={prev_state} actual={self.controller._state}"
            )
            assert self.controller._escalation_phase == prev_phase, (
                f"step '{step.name}' expected noop phase={prev_phase} actual={self.controller._escalation_phase}"
            )
        self._assert_mark_update(
            step=step,
            mark_name="notify",
            previous=prev_notify,
            current=self.controller._ctx.get("last_notify_ts_by_state", {}),
            updated=step.notify_mark_updated,
            state_key=step.notify_mark_state or step.expected_state,
        )
        self._assert_mark_update(
            step=step,
            mark_name="tts",
            previous=prev_tts,
            current=self.controller._ctx.get("last_tts_ts_by_state", {}),
            updated=step.tts_mark_updated,
            state_key=step.tts_mark_state or step.expected_state,
        )
        for expected_snippet in step.expect_log_contains:
            assert any(expected_snippet in message for _, message in new_logs), (
                f"step '{step.name}' expected log containing {expected_snippet!r}"
            )

    @staticmethod
    def _assert_mark_update(
        *,
        step: ScenarioStep,
        mark_name: str,
        previous: dict[str, Any],
        current: dict[str, Any],
        updated: bool | None,
        state_key: str | None,
    ) -> None:
        if updated is None or state_key is None:
            return
        before = previous.get(state_key)
        after = current.get(state_key)
        if updated:
            assert after is not None and after != before, (
                f"step '{step.name}' expected {mark_name} mark update for state={state_key} before={before!r} after={after!r}"
            )
        else:
            assert after == before, (
                f"step '{step.name}' expected no {mark_name} mark update for state={state_key} before={before!r} after={after!r}"
            )

    def format_trace(self) -> str:
        lines = [f"Scenario trace: {self.scenario_name}"]
        if not self.trace:
            lines.append("  <no completed steps>")
            return "\n".join(lines)
        for item in self.trace:
            lines.append(
                "  Step {index}: {name} [{kind}] -> state={state} phase={phase}".format(**item)
            )
            lines.append(f"    new_calls={item['new_calls']!r}")
            lines.append(f"    new_logs={item['new_logs']!r}")
        return "\n".join(lines)
