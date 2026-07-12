#!/usr/bin/env python3
"""Dependency-free structural checks for the frozen worker v1 fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
STYLES = {"verbatim-context-corrected", "light-cleanup", "message"}
PHASES = {
    "loading_asr",
    "transcribing",
    "loading_cleanup",
    "cleaning",
    "correcting",
}
MODELS = (
    "mlx-community/whisper-large-v3-turbo",
    "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
)
TIMINGS = {
    "loading_asr_seconds",
    "asr_seconds",
    "loading_cleanup_seconds",
    "cleanup_seconds",
    "correction_seconds",
    "total_seconds",
}
ERRORS = {
    "invalid_request",
    "protocol_mismatch",
    "not_ready",
    "audio_invalid",
    "asr_failed",
    "empty_transcript",
    "internal_error",
}


def exact_keys(value: dict[str, Any], keys: set[str]) -> None:
    if set(value) != keys:
        raise ValueError(f"expected keys {sorted(keys)}, got {sorted(value)}")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def validate(message: Any) -> None:
    if not isinstance(message, dict) or message.get("protocol_version") != 1:
        raise ValueError("message must be a protocol v1 object")

    if "command" in message:
        exact_keys(message, {"protocol_version", "id", "command", "payload"})
        if not nonempty(message["id"]) or len(message["id"]) > 128:
            raise ValueError("invalid command id")
        command, payload = message["command"], message["payload"]
        if not isinstance(payload, dict):
            raise ValueError("command payload must be an object")
        if command == "hello":
            exact_keys(payload, {"client_name", "client_version"})
            if not all(nonempty(payload[key]) for key in payload):
                raise ValueError("invalid hello payload")
        elif command in {"warmup", "shutdown"}:
            exact_keys(payload, set())
        elif command == "process":
            exact_keys(payload, {"audio_path", "style", "debug"})
            if not nonempty(payload["audio_path"]):
                raise ValueError("invalid audio path")
            if payload["style"] not in STYLES or not isinstance(payload["debug"], bool):
                raise ValueError("invalid process options")
        else:
            raise ValueError("unknown command")
        return

    exact_keys(message, {"protocol_version", "request_id", "event", "payload"})
    if not nonempty(message["request_id"]) or len(message["request_id"]) > 128:
        raise ValueError("invalid request id")
    event, payload = message["event"], message["payload"]
    if not isinstance(payload, dict):
        raise ValueError("event payload must be an object")
    if event == "ready":
        exact_keys(
            payload,
            {"worker_version", "asr_model", "cleanup_model", "language", "corrections_version"},
        )
        if (
            not nonempty(payload["worker_version"])
            or (payload["asr_model"], payload["cleanup_model"]) != MODELS
            or payload["language"] != "en"
            or payload["corrections_version"] != "1"
        ):
            raise ValueError("invalid ready event")
    elif event == "phase":
        exact_keys(payload, {"phase"})
        if payload["phase"] not in PHASES:
            raise ValueError("invalid phase")
    elif event == "error":
        exact_keys(payload, {"code", "message", "recoverable"})
        if payload["code"] not in ERRORS or not nonempty(payload["message"]):
            raise ValueError("invalid error")
        if not isinstance(payload["recoverable"], bool):
            raise ValueError("invalid recoverable flag")
    elif event == "result":
        validate_result(payload)
    else:
        raise ValueError("unknown event")


def validate_result(payload: dict[str, Any]) -> None:
    kind = payload.get("kind")
    if kind == "warmup":
        exact_keys(payload, {"kind", "warmed"})
        if payload["warmed"] is not True:
            raise ValueError("invalid warmup result")
        return
    if kind == "shutdown":
        exact_keys(payload, {"kind"})
        return
    if kind != "process":
        raise ValueError("invalid result kind")
    exact_keys(
        payload,
        {
            "kind", "raw_asr", "raw_cleanup", "final_text", "corrections",
            "timings", "asr_model", "cleanup_model", "style", "warning",
        },
    )
    if not nonempty(payload["raw_asr"]) or not nonempty(payload["final_text"]):
        raise ValueError("process text must be non-empty")
    if payload["raw_cleanup"] is not None and not isinstance(payload["raw_cleanup"], str):
        raise ValueError("invalid raw cleanup")
    if (payload["asr_model"], payload["cleanup_model"]) != MODELS:
        raise ValueError("invalid model id")
    if payload["style"] not in STYLES:
        raise ValueError("invalid style")
    if payload["warning"] not in {None, "cleanup_failed_raw_asr"}:
        raise ValueError("invalid warning")
    if not isinstance(payload["corrections"], list):
        raise ValueError("corrections must be an array")
    for correction in payload["corrections"]:
        exact_keys(correction, {"from", "to", "count"})
        if not nonempty(correction["from"]) or not nonempty(correction["to"]):
            raise ValueError("invalid correction text")
        if isinstance(correction["count"], bool) or not isinstance(correction["count"], int) or correction["count"] < 1:
            raise ValueError("invalid correction count")
    exact_keys(payload["timings"], TIMINGS)
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
        for value in payload["timings"].values()
    ):
        raise ValueError("invalid timing")
    if payload["warning"] == "cleanup_failed_raw_asr" and not (
        payload["raw_cleanup"] is None
        and payload["final_text"] == payload["raw_asr"]
        and payload["corrections"] == []
    ):
        raise ValueError("invalid raw-ASR fallback")


def load_lines(path: Path) -> list[Any]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main() -> int:
    schema = json.loads((CONTRACTS / "billie-flow.worker.v1.schema.json").read_text())
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("contract schema is not draft 2020-12")
    valid = load_lines(CONTRACTS / "fixtures" / "valid.ndjson")
    invalid = load_lines(CONTRACTS / "fixtures" / "invalid.ndjson")
    for message in valid:
        validate(message)
    wrongly_valid = []
    for index, message in enumerate(invalid, start=1):
        try:
            validate(message)
        except (KeyError, TypeError, ValueError):
            continue
        wrongly_valid.append(index)
    if wrongly_valid:
        raise ValueError(f"invalid fixtures accepted at lines {wrongly_valid}")
    print(f"worker contract v1: {len(valid)} valid and {len(invalid)} invalid fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
