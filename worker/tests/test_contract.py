from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from billie_flow_worker.service import WorkerService

from helpers import StubRuntime, command, write_wav

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/billie-flow.worker.v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def assert_valid(message: dict):
    errors = list(VALIDATOR.iter_errors(message))
    assert errors == [], "\n".join(error.message for error in errors)


def test_every_worker_event_validates_against_frozen_contract(tmp_path: Path):
    audio = write_wav(tmp_path / "recording.wav")
    service = WorkerService(StubRuntime())
    lines = [
        command("prehello", "warmup", {}),
        command("hello", "hello", {"client_name": "Billie Flow", "client_version": "0.1.0"}),
        command("warm", "warmup", {}),
        command("process", "process", {"audio_path": str(audio), "style": "light-cleanup", "debug": False}),
        command("shutdown", "shutdown", {}),
    ]
    for line in lines:
        for message in service.handle_line(line):
            assert_valid(message)


def test_cleanup_fallback_validates_against_frozen_contract(tmp_path: Path):
    audio = write_wav(tmp_path / "recording.wav")
    service = WorkerService(StubRuntime(fail_cleanup=True))
    list(service.handle_line(command("hello", "hello", {"client_name": "x", "client_version": "x"})))
    messages = list(service.handle_line(command("process", "process", {"audio_path": str(audio), "style": "message", "debug": False})))
    for message in messages:
        assert_valid(message)


def test_all_checked_in_contract_fixtures_have_expected_validity():
    valid_lines = (ROOT / "contracts/fixtures/valid.ndjson").read_text().splitlines()
    for line in valid_lines:
        assert_valid(json.loads(line))

    invalid_lines = (ROOT / "contracts/fixtures/invalid.ndjson").read_text().splitlines()
    for line in invalid_lines:
        assert list(VALIDATOR.iter_errors(json.loads(line)))
