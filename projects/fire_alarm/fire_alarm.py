from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any

import appdaemon.plugins.hass.hassapi as hass

from . import fire_alarm_constants as c
from .decision.models import ControllerContext, FaultState as DecisionFaultState
from .decision.policy import build_decision_result
from .entry_action.planner import build_device_action_plan
from .fault.confirmation import expire_pending_confirmations, register_pending_confirmation
from .fault.detector import clear_sensor_fault, is_unavailable_like, open_sensor_fault
from .fault.models import FaultState
from .incident.lifecycle import update_incident_lifecycle
from .incident.models import IncidentState
from .notification_policy.policy import build_notification_action_plan
from .snapshot.builder import build_snapshot
from .snapshot.models import TemperatureTrackerState
from .fire_alarm_control import normalize_control_action, reset_runtime_context, should_allow_reset
from .fire_alarm_controller_adapters import build_controller_adapters
import projects.fire_alarm.fire_alarm_faults as legacy_faults
from .fire_alarm_dispatch_flow import run_dispatch_flow
from .fire_alarm_init import build_output_targets, build_runtime_context, build_sensor_registry


class FireAlarm(hass.Hass):
    """Single-controller orchestration layer for the fire alarm project."""

    @staticmethod
    def _primary_states() -> set[str]:
        return {
            getattr(c, "STATE_DISABLED", "disabled"),
            getattr(c, "STATE_NORMAL", "normal"),
            getattr(c, "STATE_OBSERVE", "observe"),
            getattr(c, "STATE_PREALARM", "prealarm"),
            getattr(c, "STATE_ALARM", "alarm"),
            getattr(c, "STATE_CRITICAL", "critical"),
        }

    def initialize(self) -> None:
        self._lock = Lock()
        self._adapters = build_controller_adapters(
            log=lambda message, level: self.log(message, level=level),
            get_state=self.get_state,
            call_service=self.call_service,
            apply_temperature_policy=lambda temperature_states, base_summary: base_summary,
            is_unavailable=self._is_unavailable,
        )

        self._state = self._initial_state()
        self._escalation_phase = self._phase_for_state(self._state)
        self._last_transition_ts: datetime | None = None

        self._ctx: dict[str, Any] = build_runtime_context()
        self._fault_state = FaultState()
        self._incident_state = IncidentState()
        self._temperature_tracker = TemperatureTrackerState()
        self._shutdown_state: dict[str, Any] = {}

        self._sensor_entity_ids, raw_sensor_cache = build_sensor_registry(self.args)
        self._sensor_cache: dict[str, dict[str, Any]] = {
            "smoke": raw_sensor_cache.get("smoke", {}),
            "gas": raw_sensor_cache.get("gas", {}),
            "temperature_environment": {},
            "temperature_stove": {},
            "temperature_other_room": {},
        }
        for entity_id in self._sensor_entity_ids.get("smoke", []):
            self._sensor_cache["smoke"][entity_id] = self._adapters.get_state(entity_id)
        for entity_id in self._sensor_entity_ids.get("gas", []):
            self._sensor_cache["gas"][entity_id] = self._adapters.get_state(entity_id)
        for entity_id in self._sensor_entity_ids.get("temperature", []):
            self._sensor_cache["temperature_environment"][entity_id] = self._adapters.get_state(entity_id)

        self._outputs = build_output_targets(self.args)
        self._notify_cooldown_sec = int(self.args.get("notify_cooldown_sec", 300))
        self._tts_cooldown_sec = int(self.args.get("tts_cooldown_sec", 300))
        self._fault_notify_enabled = bool(self.args.get("fault_notify_enabled", True))
        self._fault_clear_notify_enabled = bool(self.args.get("fault_clear_notify_enabled", False))
        self._fault_notify_cooldown_sec = int(self.args.get("fault_notify_cooldown_sec", 300))
        self._control_event_name = str(self.args.get("control_event", "fire_alarm_control"))
        self._run_initial_entry_actions = bool(self.args.get("run_initial_entry_actions", False))

        self._register_sensor_listeners()
        self._register_control_listeners()
        self._sync_ctx_from_models()
        self._adapters.info(
            "fire_alarm initialized: state=%s smoke=%d gas=%d temperature=%d run_initial_entry_actions=%s control_event=%s"
            % (
                self._state,
                len(self._sensor_entity_ids.get("smoke", [])),
                len(self._sensor_entity_ids.get("gas", [])),
                len(self._sensor_entity_ids.get("temperature", [])),
                self._run_initial_entry_actions,
                self._control_event_name,
            )
        )

        if self._run_initial_entry_actions:
            snapshot = self._build_snapshot(
                trigger_entity_id="__init__",
                trigger_source="system",
                trigger_event="initialize",
                old_value=None,
                new_value=None,
            )
            self._evaluate_snapshot_and_dispatch(snapshot, allow_transition=False)

    def _initial_state(self) -> str:
        initial_state = str(self.args.get("initial_state", getattr(c, "STATE_NORMAL", "normal"))).strip().lower()
        if initial_state not in self._primary_states():
            self._adapters.warning(
                "invalid initial_state=%s, fallback to %s" % (initial_state, getattr(c, "STATE_NORMAL", "normal"))
            )
            return getattr(c, "STATE_NORMAL", "normal")
        return initial_state

    def _phase_for_state(self, state: str) -> str:
        phase_map = getattr(c, "DEFAULT_ESCALATION_PHASE_MAP", {})
        return str(phase_map.get(state, getattr(c, "PHASE_OBSERVE", "observe")))

    def _register_sensor_listeners(self) -> None:
        for source_name, event_name in (
            ("smoke", c.EVENT_SMOKE_UPDATE),
            ("gas", c.EVENT_GAS_UPDATE),
            ("temperature", c.EVENT_TEMPERATURE_UPDATE),
        ):
            for entity_id in self._sensor_entity_ids.get(source_name, []):
                self.listen_state(
                    self._handle_sensor_update,
                    entity_id,
                    source_name=source_name,
                    event_name=event_name,
                )

    def _register_control_listeners(self) -> None:
        self.listen_event(self._handle_control_event, self._control_event_name)

    def _handle_sensor_update(
        self,
        entity: str,
        attribute: str,
        old: Any,
        new: Any,
        kwargs: dict[str, Any],
    ) -> None:
        del attribute
        source_name = str(kwargs.get("source_name", "unknown"))
        event_name = str(kwargs.get("event_name", c.EVENT_SENSOR_UPDATE))

        pending_fault_notify = None
        with self._lock:
            self._update_sensor_cache(source_name=source_name, entity_id=entity, value=new)
            pending_fault_notify = self._apply_sensor_fault_update(source_name=source_name, entity_id=entity, value=new)

            if self._state == getattr(c, "STATE_DISABLED", "disabled"):
                self._sync_ctx_from_models()
                self._adapters.debug("state is disabled, ignore sensor update")
                return

            snapshot = self._build_snapshot(
                trigger_entity_id=entity,
                trigger_source=source_name,
                trigger_event=event_name,
                old_value=old,
                new_value=new,
            )

        self._send_fault_notify_if_needed(pending_fault_notify)
        self._evaluate_snapshot_and_dispatch(snapshot)

    def _handle_control_event(self, event_name: str, data: dict[str, Any], kwargs: dict[str, Any]) -> None:
        del event_name, kwargs
        action = normalize_control_action(data)
        if not action:
            self._adapters.warning("control event ignored: missing action")
            return

        snapshot = None
        with self._lock:
            if action == "ack":
                self._ctx["acked"] = True
                self._ctx["acked_incident_id"] = self._incident_state.incident_id
            elif action == "silence":
                self._ctx["silenced"] = True
                self._ctx["silenced_incident_id"] = self._incident_state.incident_id
            elif action == "manual_override_on":
                self._ctx["manual_override"] = True
                if self._state == getattr(c, "STATE_CRITICAL", "critical"):
                    self._adapters.warning(
                        "manual_override enabled during critical; primary protection remains active"
                    )
                else:
                    self._adapters.info("manual_override enabled")
                self._sync_ctx_from_models()
                return
            elif action == "manual_override_off":
                self._ctx["manual_override"] = False
                self._adapters.info("manual_override disabled")
                self._sync_ctx_from_models()
                return
            elif action == "reset":
                snapshot = self._build_snapshot(
                    trigger_entity_id="__control__",
                    trigger_source="control",
                    trigger_event="reset_check",
                    old_value=None,
                    new_value=None,
                )
                proposed_state = self._project_state(snapshot)
                if not should_allow_reset(
                    current_state=self._state,
                    proposed_state=proposed_state,
                    normal_state=getattr(c, "STATE_NORMAL", "normal"),
                ):
                    self._adapters.warning(
                        "reset ignored: normal conditions not met (state=%s)" % self._state
                    )
                    return
                had_active_faults = bool(self._ctx.get("active_faults"))
                reset_runtime_context(self._ctx)
                self._fault_state = FaultState()
                self._incident_state = IncidentState()
                self._temperature_tracker = TemperatureTrackerState()
                self._state = getattr(c, "STATE_NORMAL", "normal")
                self._escalation_phase = self._phase_for_state(self._state)
                self._last_transition_ts = datetime.now(timezone.utc)
                if had_active_faults:
                    self._adapters.info(
                        "reset cleared active_faults operationally; unresolved device faults may reappear on next updates"
                    )
                self._sync_ctx_from_models()
                for channel in ("light", "beacon", "buzzer"):
                    self._dispatch_service(channel, "off", {"reason": "reset_sync"})
                self._adapters.info(
                    "control event applied: action=%s acked=%s silenced=%s manual_override=%s state=%s"
                    % (
                        action,
                        self._ctx["acked"],
                        self._ctx["silenced"],
                        self._ctx["manual_override"],
                        self._state,
                    )
                )
                return
            else:
                self._adapters.warning("control event ignored: unsupported action=%s" % action)
                return

            self._sync_ctx_from_models()

        if snapshot is None:
            snapshot = self._build_snapshot(
                trigger_entity_id="__control__",
                trigger_source="control",
                trigger_event=action,
                old_value=None,
                new_value=None,
            )
        self._evaluate_snapshot_and_dispatch(snapshot, allow_transition=False)
        self._adapters.info(
            "control event applied: action=%s acked=%s silenced=%s manual_override=%s state=%s"
            % (
                action,
                self._ctx["acked"],
                self._ctx["silenced"],
                self._ctx["manual_override"],
                self._state,
            )
        )

    def _update_sensor_cache(self, *, source_name: str, entity_id: str, value: Any) -> None:
        cache_key = {
            "smoke": "smoke",
            "gas": "gas",
            "temperature": "temperature_environment",
        }.get(source_name, source_name)
        self._sensor_cache.setdefault(cache_key, {})[entity_id] = value

    def _apply_sensor_fault_update(self, *, source_name: str, entity_id: str, value: Any) -> dict[str, Any] | None:
        if is_unavailable_like(value):
            self._fault_state = open_sensor_fault(
                state=self._fault_state,
                source=source_name,
                entity_id=entity_id,
                value=value,
                severity="warning",
                blocks_clear=True,
            )
            pending_fault_notify = legacy_faults.record_sensor_fault(
                ctx=self._ctx,
                entity_id=entity_id,
                source_name=source_name,
                category="unavailable_update",
                observed_value=value,
                fault_notify_enabled=self._fault_notify_enabled,
                fault_clear_notify_enabled=self._fault_clear_notify_enabled,
                fault_notify_cooldown_sec=self._fault_notify_cooldown_sec,
            )
            self._adapters.warning(
                "sensor fault recorded: source=%s entity=%s value=%s" % (source_name, entity_id, value)
            )
        else:
            pending_fault_notify = legacy_faults.clear_sensor_fault(
                ctx=self._ctx,
                source_name=source_name,
                entity_id=entity_id,
                fault_notify_enabled=self._fault_notify_enabled,
                fault_clear_notify_enabled=self._fault_clear_notify_enabled,
                fault_notify_cooldown_sec=self._fault_notify_cooldown_sec,
            )
            self._fault_state = clear_sensor_fault(
                state=self._fault_state,
                source=source_name,
                entity_id=entity_id,
            )
        self._sync_ctx_from_models()
        return pending_fault_notify

    def _build_snapshot(
        self,
        *,
        trigger_entity_id: str,
        trigger_source: str,
        trigger_event: str,
        old_value: Any,
        new_value: Any,
    ):
        snapshot = build_snapshot(
            sensor_cache=self._sensor_cache,
            trigger_entity_id=trigger_entity_id,
            trigger_source=trigger_source,
            trigger_event=trigger_event,
            old_value=old_value,
            new_value=new_value,
            shutdown_state=self._shutdown_state,
            temperature_tracker_state=self._temperature_tracker,
        )
        self._temperature_tracker = snapshot.temperature.tracker_state
        return snapshot

    def _controller_context(self) -> ControllerContext:
        return ControllerContext(
            current_state=self._decision_state(self._state),
            current_phase=self._escalation_phase,
            last_transition_ts=(self._last_transition_ts.isoformat() if self._last_transition_ts else None),
            acked=bool(self._ctx.get("acked", False)),
            acked_incident_id=self._ctx.get("acked_incident_id"),
            silenced=bool(self._ctx.get("silenced", False)),
            silenced_incident_id=self._ctx.get("silenced_incident_id"),
            manual_override=bool(self._ctx.get("manual_override", False)),
            last_notify_ts_by_state=dict(self._ctx.get("last_notify_ts_by_state", {})),
            last_tts_ts_by_state=dict(self._ctx.get("last_tts_ts_by_state", {})),
        )

    def _decision_state(self, state: str) -> str:
        return "observe" if state == getattr(c, "STATE_NORMAL", "normal") else state

    def _external_state(self, *, decision_state: str, snapshot, decision_result) -> str:
        if decision_result.clear_blocked and decision_state == "observe" and self._state != getattr(c, "STATE_NORMAL", "normal"):
            return self._state
        if decision_state == "observe" and decision_result.primary_hazard_source in {None, "fault_only", "stove_reminder"}:
            if snapshot.summary.fire_monitor_highest_severity is None and not snapshot.summary.smoke_any_alarm and not snapshot.summary.gas_any_alarm:
                return getattr(c, "STATE_NORMAL", "normal")
        return decision_state

    def _decision_fault_state(self) -> DecisionFaultState:
        return DecisionFaultState(
            active_sensor_faults=self._fault_state.active_sensor_faults,
            active_device_faults=self._fault_state.active_device_faults,
            pending_confirmations=self._fault_state.pending_confirmations,
            clear_blockers=self._fault_state.clear_blockers,
            last_fault_notify_ts_by_key=self._fault_state.last_fault_notify_ts_by_key,
            last_fault_clear_notify_ts_by_key=self._fault_state.last_fault_clear_notify_ts_by_key,
            active_fault_notified_keys=self._fault_state.active_fault_notified_keys,
            cleared_fault_notified_keys=self._fault_state.cleared_fault_notified_keys,
        )

    def _project_state(self, snapshot) -> str:
        decision_result = build_decision_result(
            snapshot=snapshot,
            controller_context=self._controller_context(),
            incident_state=self._incident_state,
            fault_state=self._decision_fault_state(),
        )
        return self._external_state(
            decision_state=decision_result.next_state,
            snapshot=snapshot,
            decision_result=decision_result,
        )

    def _evaluate_snapshot_and_dispatch(self, snapshot, *, allow_transition: bool = True) -> None:
        with self._lock:
            self._fault_state = expire_pending_confirmations(state=self._fault_state)
            controller_context = self._controller_context()
            decision_result = build_decision_result(
                snapshot=snapshot,
                controller_context=controller_context,
                incident_state=self._incident_state,
                fault_state=self._decision_fault_state(),
            )
            incident_lifecycle = update_incident_lifecycle(
                decision_result=decision_result,
                snapshot=snapshot,
                controller_context=controller_context,
                previous_incident_state=self._incident_state,
            )
            self._incident_state = incident_lifecycle.incident_state
            self._log_incident_lifecycle(incident_lifecycle)
            next_external_state = self._external_state(
                decision_state=decision_result.next_state,
                snapshot=snapshot,
                decision_result=decision_result,
            )
            if allow_transition and next_external_state != self._state:
                previous_state = self._state
                self._state = next_external_state
                self._escalation_phase = self._phase_for_state(self._state)
                self._last_transition_ts = datetime.now(timezone.utc)
                self._adapters.info(
                    "state transition: %s -> %s trigger=%s source=%s"
                    % (previous_state, self._state, snapshot.trigger_entity_id, snapshot.trigger_source)
                )
            device_plan = build_device_action_plan(
                decision_result=decision_result,
                snapshot=snapshot,
                controller_context=controller_context,
                incident_state=self._incident_state,
                fault_state=self._fault_state,
            )
            notification_plan = build_notification_action_plan(
                decision_result=decision_result,
                snapshot=snapshot,
                controller_context=controller_context,
                incident_state=self._incident_state,
                notify_cooldown_sec=self._notify_cooldown_sec,
                tts_cooldown_sec=self._tts_cooldown_sec,
            )
            self._sync_ctx_from_models()

        dispatched_notification_marks: list[tuple[str, str]] = []
        shutdown_confirmations: list[tuple[str, str, str, int | None, bool]] = []

        should_dispatch_device_plan = decision_result.transition_changed or incident_lifecycle.changed

        if should_dispatch_device_plan:
            for action in device_plan.device_actions:
                self._dispatch_service(action.channel, action.action, dict(action.payload))

        if should_dispatch_device_plan:
            for action in device_plan.shutdown_actions:
                channel, dispatch_action, payload = self._shutdown_dispatch(action)
                self._dispatch_service(channel, dispatch_action, payload)
                if action.confirmation_required and action.confirmation_key:
                    shutdown_confirmations.append(
                        (
                            action.device,
                            dispatch_action,
                            action.confirmation_key,
                            action.confirmation_timeout_sec,
                            action.failure_blocks_clear,
                        )
                    )

        for action in notification_plan.notification_actions:
            if action.suppressed:
                continue
            payload = self._notification_payload(snapshot=snapshot, action=action)
            dispatch_action = "speak" if action.channel == "tts" else "send"
            self._dispatch_service(action.channel, dispatch_action, payload)
            dispatched_notification_marks.append((action.channel, notification_plan.state))

        with self._lock:
            for device, requested_action, confirmation_key, timeout_sec, blocks_clear in shutdown_confirmations:
                self._fault_state = register_pending_confirmation(
                    state=self._fault_state,
                    device=device,
                    requested_action=requested_action,
                    confirmation_key=confirmation_key,
                    timeout_sec=timeout_sec,
                    blocks_clear_on_timeout=blocks_clear,
                )
            for channel, state in dispatched_notification_marks:
                if channel == "notify":
                    self._ctx.setdefault("last_notify_ts_by_state", {})[state] = monotonic()
                elif channel == "tts":
                    self._ctx.setdefault("last_tts_ts_by_state", {})[state] = monotonic()
            self._sync_ctx_from_models()


    def _log_incident_lifecycle(self, incident_lifecycle) -> None:
        action = incident_lifecycle.lifecycle_action
        if action == "open":
            self._adapters.info("incident opened: id=%s" % incident_lifecycle.incident_id)
        elif action == "close":
            self._adapters.info("incident closed: id=%s" % incident_lifecycle.previous_incident_id)
        elif action == "escalate":
            self._adapters.info("incident escalated: id=%s" % incident_lifecycle.incident_id)
        elif action == "recover" and incident_lifecycle.changed:
            self._adapters.info("incident recovered: id=%s" % incident_lifecycle.incident_id)
        elif action == "stabilize" and incident_lifecycle.changed:
            self._adapters.debug("incident refreshed in same state: id=%s" % incident_lifecycle.incident_id)

    def _shutdown_dispatch(self, action) -> tuple[str, str, dict[str, Any]]:
        payload = {
            "device": action.device,
            "requested_state": action.requested_state,
            "confirmation_required": action.confirmation_required,
        }
        if action.confirmation_key:
            payload["confirmation_key"] = action.confirmation_key
        channel = "valve" if action.device.startswith("valve") else action.device
        dispatch_action = {
            "closed": "close",
            "on": "on",
            "disabled": "disable",
            "blocked": "block",
        }.get(action.requested_state, action.requested_state)
        self._shutdown_state = {
            **self._shutdown_state,
            "protective_shutdown_active": True,
            "hard_lockout_active": bool(action.device == "valve_reopen" or self._incident_state.hard_lockout_active),
            "valve_requested_closed": self._shutdown_state.get("valve_requested_closed", False) or action.device == "valve",
            "exhaust_requested_on": self._shutdown_state.get("exhaust_requested_on", False) or action.device == "exhaust",
            "clear_blocked_by_shutdown": self._fault_state.clear_blockers != {},
        }
        return channel, dispatch_action, payload

    def _notification_payload(self, *, snapshot, action) -> dict[str, Any]:
        message_map = {
            "environment_fire_warning": "Fire alarm triggered",
            "stove_warning": "Stove temperature warning",
            "close_failure": "Valve close confirmation failed",
            "prohibited_start": "Hazard lockout active",
        }
        return {
            **dict(action.payload),
            "message": message_map.get(action.message_key, action.message_key.replace("_", " ")),
            "state": self._state,
            "phase": self._escalation_phase,
            "trigger_entity_id": snapshot.trigger_entity_id,
            "trigger_source": snapshot.trigger_source,
        }


    def _send_fault_notify_if_needed(self, fault_decision: dict[str, Any] | None) -> None:
        if not fault_decision:
            return
        payload = fault_decision.get("payload")
        fault_notify_key = fault_decision.get("fault_notify_key")
        is_clear = bool(fault_decision.get("is_clear", False))
        if not payload or not fault_notify_key:
            return
        self._dispatch_service("notify", "send", dict(payload))
        legacy_faults.mark_fault_notified(
            ctx=self._ctx,
            fault_notify_key_value=fault_notify_key,
            is_clear=is_clear,
        )

    def _dispatch_service(self, channel: str, action: str, payload: dict[str, Any] | None = None) -> None:
        run_dispatch_flow(
            outputs=self._outputs,
            channel=channel,
            action=action,
            payload=payload,
            log=self._adapters.log,
            call_service=self._adapters.call_service,
        )

    def _sync_ctx_from_models(self) -> None:
        active_sources: list[str] = []
        for source in self._incident_state.hazard_source_set:
            mapped = "temperature_alarm" if source in {"environment_fire", "other_room_fire"} else source
            if mapped not in active_sources:
                active_sources.append(mapped)
        self._ctx["current_incident_id"] = self._incident_state.incident_id
        self._ctx["incident_start_ts"] = self._incident_state.opened_at
        self._ctx["incident_severity"] = self._incident_state.current_state
        self._ctx["incident_active_sources"] = active_sources
        self._ctx["acked_incident_id"] = self._ctx.get("acked_incident_id")
        self._ctx["silenced_incident_id"] = self._ctx.get("silenced_incident_id")
        self._ctx["active_faults"] = {
            f"{record.source}:{record.entity_id}": {
                "fault_id": record.fault_id,
                "source": record.source,
                "entity_id": record.entity_id,
                "category": record.category,
                "value": record.value,
            }
            for record in self._fault_state.active_sensor_faults.values()
        }
        self._ctx["last_fault_notify_ts_by_key"] = {**self._ctx.get("last_fault_notify_ts_by_key", {}), **self._fault_state.last_fault_notify_ts_by_key}
        self._ctx["last_fault_clear_notify_ts_by_key"] = {**self._ctx.get("last_fault_clear_notify_ts_by_key", {}), **self._fault_state.last_fault_clear_notify_ts_by_key}
        self._ctx["active_fault_notified_keys"] = set(self._ctx.get("active_fault_notified_keys", set())) | set(self._fault_state.active_fault_notified_keys)
        self._ctx["cleared_fault_notified_keys"] = set(self._ctx.get("cleared_fault_notified_keys", set())) | set(self._fault_state.cleared_fault_notified_keys)
        self._ctx["pending_confirmations"] = dict(self._fault_state.pending_confirmations)
        self._ctx["clear_blockers"] = dict(self._fault_state.clear_blockers)

    @staticmethod
    def _is_unavailable(value: Any) -> bool:
        if value is None:
            return True
        return str(value).strip().lower() in getattr(c, "UNAVAILABLE_STATE_SET", set())
