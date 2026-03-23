from __future__ import annotations

from typing import Any

from projects.fire_alarm.fire_alarm_dispatch_flow import run_dispatch_flow


class DispatchRecorder:
    def __init__(self) -> None:
        self.logs: list[tuple[str, str]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def log(self, message: str, level: str) -> None:
        self.logs.append((level, message))

    def call_service(self, service: str, **data: Any) -> None:
        self.calls.append((service, data))



def test_run_dispatch_flow_skips_missing_output_channel_with_debug_log():
    recorder = DispatchRecorder()

    run_dispatch_flow(
        outputs={},
        channel="notify",
        action="send",
        payload={"message": "hello"},
        log=recorder.log,
        call_service=recorder.call_service,
    )

    assert recorder.calls == []
    assert recorder.logs == [
        ("DEBUG", "dispatch skipped: missing target channel=notify action=send")
    ]



def test_run_dispatch_flow_logs_error_for_invalid_target_config():
    recorder = DispatchRecorder()

    run_dispatch_flow(
        outputs={"notify": {"domain": "notify"}},
        channel="notify",
        action="send",
        payload={"message": "hello"},
        log=recorder.log,
        call_service=recorder.call_service,
    )

    assert recorder.calls == []
    assert recorder.logs == [
        ("ERROR", "dispatch config invalid for channel=notify")
    ]



def test_run_dispatch_flow_logs_error_for_parse_failed_target():
    recorder = DispatchRecorder()

    run_dispatch_flow(
        outputs={"notify": "badtarget"},
        channel="notify",
        action="send",
        payload={"message": "hello"},
        log=recorder.log,
        call_service=recorder.call_service,
    )

    assert recorder.calls == []
    assert recorder.logs == [
        ("ERROR", "dispatch target parse failed channel=notify target=badtarget")
    ]



def test_run_dispatch_flow_executes_domain_service_target_with_none_payload():
    recorder = DispatchRecorder()

    run_dispatch_flow(
        outputs={"notify": "notify/mobile_app"},
        channel="notify",
        action="send",
        payload=None,
        log=recorder.log,
        call_service=recorder.call_service,
    )

    assert recorder.logs == []
    assert recorder.calls == [
        ("notify/mobile_app", {"action": "send"})
    ]



def test_run_dispatch_flow_merges_dict_target_base_data_and_payload():
    recorder = DispatchRecorder()

    run_dispatch_flow(
        outputs={
            "notify": {
                "domain": "notify",
                "service": "mobile_app",
                "data": {"base": 1, "message": "base-msg"},
            }
        },
        channel="notify",
        action="send",
        payload={"message": "override-msg", "priority": "high"},
        log=recorder.log,
        call_service=recorder.call_service,
    )

    assert recorder.logs == []
    assert recorder.calls == [
        (
            "notify/mobile_app",
            {"base": 1, "message": "override-msg", "priority": "high", "action": "send"},
        )
    ]



def test_run_dispatch_flow_preserves_notify_and_tts_payload_shapes():
    recorder = DispatchRecorder()

    run_dispatch_flow(
        outputs={"notify": "notify/mobile_app", "tts": "tts/speaker"},
        channel="notify",
        action="send",
        payload={"message": "Fire alarm triggered"},
        log=recorder.log,
        call_service=recorder.call_service,
    )
    run_dispatch_flow(
        outputs={"notify": "notify/mobile_app", "tts": "tts/speaker"},
        channel="tts",
        action="speak",
        payload={"message": "Critical fire emergency"},
        log=recorder.log,
        call_service=recorder.call_service,
    )

    assert recorder.calls == [
        (
            "notify/mobile_app",
            {"message": "Fire alarm triggered", "action": "send"},
        ),
        (
            "tts/speaker",
            {"message": "Critical fire emergency", "action": "speak"},
        ),
    ]
