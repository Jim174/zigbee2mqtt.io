"""Dispatch target parsing and service call payload builders."""

from __future__ import annotations

from typing import Any


def resolve_light_effect_payload(
    *,
    outputs: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    effect_key = payload.get("effect_key")
    if not effect_key:
        return payload

    light_effects = outputs.get("light_effects", {})
    effect_payload = light_effects.get(str(effect_key))
    if not isinstance(effect_payload, dict):
        return {"__effect_resolution_error__": str(effect_key)}

    resolved_payload = dict(effect_payload)
    for key, value in payload.items():
        if key != "effect_key":
            resolved_payload[key] = value
    resolved_payload["effect_key"] = str(effect_key)
    return resolved_payload


def parse_dispatch_target(target: Any) -> dict[str, Any]:
    """Parse a dispatch target into domain/service and base data or an error reason."""
    if isinstance(target, dict):
        domain = target.get("domain")
        service = target.get("service")
        if not domain or not service:
            return {"ok": False, "error": "invalid_config"}

        return {
            "ok": True,
            "domain": domain,
            "service": service,
            "base_data": target.get("data", {}),
            "is_dict_target": True,
        }

    try:
        domain, service = str(target).split("/", 1)
    except ValueError:
        return {"ok": False, "error": "parse_failed"}

    return {
        "ok": True,
        "domain": domain,
        "service": service,
        "base_data": {},
        "is_dict_target": False,
    }


def build_dispatch_service_call(
    *,
    parsed_target: dict[str, Any],
    payload: dict[str, Any],
    action: str,
) -> tuple[str, dict[str, Any]]:
    """Build service name and service_data with stable merge rules."""
    domain = str(parsed_target["domain"])
    service = str(parsed_target["service"])

    if parsed_target.get("is_dict_target", False):
        base_data = parsed_target.get("base_data", {})
        service_data = {**base_data, **payload}
    else:
        service_data = payload

    service_data["action"] = action
    return f"{domain}/{service}", service_data
