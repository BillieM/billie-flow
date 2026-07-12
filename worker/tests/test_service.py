from __future__ import annotations

import json
from pathlib import Path

import pytest

from billie_flow_worker import ASR_MODEL, CLEANUP_MODEL
from billie_flow_worker.service import WorkerService

from helpers import StubRuntime, command, write_wav


def greet(service: WorkerService):
    events = list(
        service.handle_line(
            command(
                "hello-1",
                "hello",
                {"client_name": "Billie Flow", "client_version": "0.1.0"},
            )
        )
    )
    assert events[0]["event"] == "ready"
    return events[0]


def test_requires_hello_and_rejects_duplicate_hello():
    service = WorkerService(StubRuntime())
    event = list(service.handle_line(command("warm", "warmup", {})))[0]
    assert event["payload"]["code"] == "not_ready"
    greet(service)
    duplicate = command(
        "hello-2", "hello", {"client_name": "Billie Flow", "client_version": "0.1.0"}
    )
    event = list(service.handle_line(duplicate))[0]
    assert event["payload"]["code"] == "invalid_request"


def test_ready_advertises_frozen_compatibility():
    event = greet(WorkerService(StubRuntime()))
    assert event["payload"] == {
        "worker_version": "0.1.0",
        "asr_model": ASR_MODEL,
        "cleanup_model": CLEANUP_MODEL,
        "language": "en",
        "corrections_version": "1",
    }


def test_warmup_loads_once_and_retains_models():
    runtime = StubRuntime()
    service = WorkerService(runtime)
    greet(service)
    first = list(service.handle_line(command("warm-1", "warmup", {})))
    second = list(service.handle_line(command("warm-2", "warmup", {})))
    assert [item["payload"].get("phase") for item in first[:-1]] == [
        "loading_asr",
        "loading_cleanup",
    ]
    assert first[-1]["payload"] == {"kind": "warmup", "warmed": True}
    assert second == [
        {
            "protocol_version": 1,
            "request_id": "warm-2",
            "event": "result",
            "payload": {"kind": "warmup", "warmed": True},
        }
    ]
    assert runtime.asr_loads == runtime.cleanup_loads == 1


@pytest.mark.parametrize(
    "style", ["verbatim-context-corrected", "light-cleanup", "message"]
)
def test_cold_process_has_exact_phases_result_fields_and_style(tmp_path: Path, style: str):
    audio = write_wav(tmp_path / "private-recording.wav")
    runtime = StubRuntime(cleanup="Billy Flow uses Swift UI and M L X.")
    service = WorkerService(runtime)
    greet(service)
    events = list(
        service.handle_line(
            command(
                "process-1",
                "process",
                {"audio_path": str(audio), "style": style, "debug": False},
            )
        )
    )
    assert [item["payload"]["phase"] for item in events[:-1]] == [
        "loading_asr",
        "transcribing",
        "loading_cleanup",
        "cleaning",
        "correcting",
    ]
    result = events[-1]
    assert result["event"] == "result"
    assert result["payload"]["raw_asr"] == "Billy Flow uses Swift UI and M L X."
    assert result["payload"]["raw_cleanup"] == "Billy Flow uses Swift UI and M L X."
    assert result["payload"]["final_text"] == "Billie Flow uses SwiftUI and MLX."
    assert result["payload"]["style"] == style
    assert result["payload"]["warning"] is None
    assert result["payload"]["asr_model"] == ASR_MODEL
    assert result["payload"]["cleanup_model"] == CLEANUP_MODEL
    assert set(result["payload"]["timings"]) == {
        "loading_asr_seconds",
        "asr_seconds",
        "loading_cleanup_seconds",
        "cleanup_seconds",
        "correction_seconds",
        "total_seconds",
    }
    assert all(value >= 0 for value in result["payload"]["timings"].values())
    assert runtime.styles == [style]
    assert audio.exists(), "worker must not delete app-owned audio"


def test_warm_process_omits_load_phases(tmp_path: Path):
    audio = write_wav(tmp_path / "recording.wav")
    service = WorkerService(StubRuntime())
    greet(service)
    list(service.handle_line(command("warm", "warmup", {})))
    events = list(
        service.handle_line(
            command(
                "p",
                "process",
                {"audio_path": str(audio), "style": "light-cleanup", "debug": False},
            )
        )
    )
    assert [item["payload"]["phase"] for item in events[:-1]] == [
        "transcribing",
        "cleaning",
        "correcting",
    ]


def test_cleanup_failure_is_only_successful_fallback_and_skips_corrections(tmp_path: Path):
    audio = write_wav(tmp_path / "recording.wav")
    service = WorkerService(StubRuntime(fail_cleanup=True))
    greet(service)
    events = list(
        service.handle_line(
            command(
                "p",
                "process",
                {"audio_path": str(audio), "style": "light-cleanup", "debug": False},
            )
        )
    )
    result = events[-1]
    assert result["event"] == "result"
    assert result["payload"]["raw_cleanup"] is None
    assert result["payload"]["final_text"] == result["payload"]["raw_asr"]
    assert result["payload"]["corrections"] == []
    assert result["payload"]["warning"] == "cleanup_failed_raw_asr"
    assert "correcting" not in [item["payload"].get("phase") for item in events]


@pytest.mark.parametrize(
    ("runtime", "code"),
    [
        (StubRuntime(fail_asr=True), "asr_failed"),
        (StubRuntime(transcript=" \n "), "empty_transcript"),
    ],
)
def test_asr_and_empty_transcripts_are_terminal_errors(tmp_path: Path, runtime, code):
    audio = write_wav(tmp_path / f"{code}.wav")
    service = WorkerService(runtime)
    greet(service)
    events = list(
        service.handle_line(
            command(
                "p",
                "process",
                {"audio_path": str(audio), "style": "message", "debug": False},
            )
        )
    )
    assert events[-1]["event"] == "error"
    assert events[-1]["payload"]["code"] == code
    assert all(item["event"] != "result" for item in events)


def test_invalid_audio_never_reaches_models(tmp_path: Path):
    audio = write_wav(tmp_path / "wrong.wav", rate=8_000)
    runtime = StubRuntime()
    service = WorkerService(runtime)
    greet(service)
    event = list(
        service.handle_line(
            command(
                "p",
                "process",
                {"audio_path": str(audio), "style": "message", "debug": False},
            )
        )
    )[0]
    assert event["payload"]["code"] == "audio_invalid"
    assert runtime.asr_loads == runtime.cleanup_loads == 0
    assert runtime.audio_paths == []


def test_debug_diagnostic_never_discloses_content_or_path(tmp_path: Path, capsys):
    audio = write_wav(tmp_path / "secret-path.wav")
    runtime = StubRuntime(transcript="secret transcript", fail_asr=True)
    service = WorkerService(runtime)
    greet(service)
    list(
        service.handle_line(
            command(
                "p",
                "process",
                {"audio_path": str(audio), "style": "message", "debug": True},
            )
        )
    )
    stderr = capsys.readouterr().err
    assert stderr == "worker_error code=asr_failed cause=RuntimeError\n"
    assert "secret" not in stderr
    assert str(audio) not in stderr


def test_shutdown_is_terminal_and_marks_service_stopped():
    service = WorkerService(StubRuntime())
    greet(service)
    event = list(service.handle_line(command("bye", "shutdown", {})))[0]
    assert event["payload"] == {"kind": "shutdown"}
    assert service.stopped is True
