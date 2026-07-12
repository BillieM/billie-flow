from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from helpers import command, write_wav

WORKER = Path(__file__).resolve().parents[1]


def test_fake_worker_end_to_end_ndjson(tmp_path: Path):
    audio = write_wav(tmp_path / "recording.wav")
    lines = [
        command("hello", "hello", {"client_name": "Billie Flow", "client_version": "0.1.0"}),
        command("warm", "warmup", {}),
        command("process", "process", {"audio_path": str(audio), "style": "light-cleanup", "debug": False}),
        command("bye", "shutdown", {}),
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(WORKER / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "billie_flow_worker.fake"],
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
        env=environment,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stderr == ""
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    assert all(isinstance(message, dict) for message in messages)
    assert messages[0]["event"] == "ready"
    process_result = next(
        message for message in messages if message["request_id"] == "process" and message["event"] == "result"
    )
    assert process_result["payload"]["final_text"] == "Billie Flow uses SwiftUI and MLX."
    assert messages[-1]["payload"] == {"kind": "shutdown"}


def test_fake_worker_error_mode_does_not_leak_content(tmp_path: Path):
    audio = write_wav(tmp_path / "private-name.wav")
    lines = [
        command("hello", "hello", {"client_name": "x", "client_version": "x"}),
        command("process", "process", {"audio_path": str(audio), "style": "message", "debug": True}),
        command("bye", "shutdown", {}),
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(WORKER / "src")
    environment["BILLIE_FLOW_FAKE_MODE"] = "asr_failure"
    completed = subprocess.run(
        [sys.executable, "-m", "billie_flow_worker.fake"],
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
        env=environment,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stderr == "worker_error code=asr_failed cause=RuntimeError\n"
    assert str(audio) not in completed.stderr
    assert "Billy Flow" not in completed.stderr
