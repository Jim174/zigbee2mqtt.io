"""Controller adapter binding helpers for fire alarm controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ControllerAdapters:
    log: Callable[[str, str], None]
    info: Callable[[str], None]
    warning: Callable[[str], None]
    debug: Callable[[str], None]
    get_state: Callable[[str], Any]
    call_service: Callable[..., Any]
    apply_temperature_policy: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    is_unavailable: Callable[[Any], bool]


def build_controller_adapters(
    *,
    log: Callable[[str, str], None],
    get_state: Callable[[str], Any],
    call_service: Callable[..., Any],
    apply_temperature_policy: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    is_unavailable: Callable[[Any], bool],
) -> ControllerAdapters:
    """Build bound controller adapters in one place."""

    def log_info(message: str) -> None:
        log(message, "INFO")

    def log_warning(message: str) -> None:
        log(message, "WARNING")

    def log_debug(message: str) -> None:
        log(message, "DEBUG")

    return ControllerAdapters(
        log=log,
        info=log_info,
        warning=log_warning,
        debug=log_debug,
        get_state=get_state,
        call_service=call_service,
        apply_temperature_policy=apply_temperature_policy,
        is_unavailable=is_unavailable,
    )
