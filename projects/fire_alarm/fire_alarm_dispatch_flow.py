"""Dispatch execution flow helpers for fire alarm controller."""

from __future__ import annotations

from typing import Any, Callable

from .fire_alarm_dispatch import (
    build_dispatch_service_call,
    parse_dispatch_target,
    resolve_light_effect_payload,
)


def run_dispatch_flow(
    *,
    outputs: dict[str, Any],
    channel: str,
    action: str,
    payload: dict[str, Any] | None,
    log: Callable[[str, str], None],
    call_service: Callable[..., Any],
) -> None:
    """Resolve one configured dispatch target and execute the service call."""
    target = outputs.get(channel)
    if not target:
        log(
            "dispatch skipped: missing target channel=%s action=%s" % (channel, action),
            "DEBUG",
        )
        return

    payload = payload or {}
    if channel == "light":
        payload = resolve_light_effect_payload(outputs=outputs, payload=payload)
        effect_error = payload.pop("__effect_resolution_error__", None)
        if effect_error is not None:
            log(
                "dispatch light effect missing config channel=%s effect_key=%s" % (channel, effect_error),
                "ERROR",
            )
            return

    parsed_target = parse_dispatch_target(target)
    if not parsed_target.get("ok", False):
        if parsed_target.get("error") == "invalid_config":
            log("dispatch config invalid for channel=%s" % channel, "ERROR")
        else:
            log(
                "dispatch target parse failed channel=%s target=%s" % (channel, target),
                "ERROR",
            )
        return

    service_name, service_data = build_dispatch_service_call(
        parsed_target=parsed_target,
        payload=payload,
        action=action,
    )
    call_service(service_name, **service_data)
