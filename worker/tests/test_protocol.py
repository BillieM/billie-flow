import json

import pytest

from billie_flow_worker.protocol import RequestError, parse_command

from helpers import command


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("hello", {"client_name": "Billie Flow", "client_version": "0.1.0"}),
        ("warmup", {}),
        ("process", {"audio_path": "/tmp/a.wav", "style": "light-cleanup", "debug": False}),
        ("shutdown", {}),
    ],
)
def test_accepts_each_exact_command(name, payload):
    parsed = parse_command(command("id-1", name, payload))
    assert parsed.request_id == "id-1"
    assert parsed.name == name
    assert parsed.payload == payload


@pytest.mark.parametrize(
    "value",
    [
        "not json",
        "[]",
        json.dumps({"protocol_version": 1, "id": "x", "command": "wat", "payload": {}}),
        json.dumps({"protocol_version": 1, "id": "x", "command": "warmup", "payload": {"extra": 1}}),
        json.dumps({"protocol_version": 1, "id": "x", "command": "process", "payload": {"audio_path": "x", "style": "light-cleanup"}}),
        json.dumps({"protocol_version": 1, "id": "x", "command": "process", "payload": {"audio_path": "x", "style": "unknown", "debug": False}}),
        json.dumps({"protocol_version": 1, "id": "x", "command": "process", "payload": {"audio_path": "x", "style": "message", "debug": 1}}),
        json.dumps({"protocol_version": 1, "id": "x", "command": "shutdown", "payload": {}, "extra": True}),
    ],
)
def test_rejects_malformed_and_unknown_requests(value):
    with pytest.raises(RequestError) as caught:
        parse_command(value)
    assert caught.value.code == "invalid_request"


def test_protocol_mismatch_has_stable_terminal_error():
    value = command("mismatch", "warmup", {}).replace('"protocol_version": 1', '"protocol_version": 2')
    with pytest.raises(RequestError) as caught:
        parse_command(value)
    assert caught.value.request_id == "mismatch"
    assert caught.value.code == "protocol_mismatch"
    assert caught.value.recoverable is False
