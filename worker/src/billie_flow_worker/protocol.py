"""Strict parsing and event constructors for billie-flow.worker.v1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import PROTOCOL_VERSION, STYLES

MAX_ID_LENGTH = 128
UNKNOWN_REQUEST_ID = "unknown"


@dataclass(frozen=True, slots=True)
class Command:
    request_id: str
    name: str
    payload: dict[str, Any]


class RequestError(Exception):
    def __init__(self, request_id: str, code: str, message: str, recoverable: bool):
        super().__init__(message)
        self.request_id = request_id
        self.code = code
        self.message = message
        self.recoverable = recoverable


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= MAX_ID_LENGTH


def _request_id(value: Any) -> str:
    if isinstance(value, dict) and _valid_id(value.get("id")):
        return value["id"]
    return UNKNOWN_REQUEST_ID


def _invalid(request_id: str) -> RequestError:
    return RequestError(
        request_id,
        "invalid_request",
        "The worker request was invalid.",
        True,
    )


def parse_command(line: str) -> Command:
    try:
        value = json.loads(line)
    except (json.JSONDecodeError, UnicodeError):
        raise _invalid(UNKNOWN_REQUEST_ID) from None

    request_id = _request_id(value)
    if not isinstance(value, dict):
        raise _invalid(request_id)

    version = value.get("protocol_version")
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise RequestError(
            request_id,
            "protocol_mismatch",
            "The worker protocol version is unsupported.",
            False,
        )

    if set(value) != {"protocol_version", "id", "command", "payload"}:
        raise _invalid(request_id)
    if not _valid_id(value["id"]):
        raise _invalid(request_id)
    if not isinstance(value["command"], str) or not isinstance(value["payload"], dict):
        raise _invalid(request_id)

    command = value["command"]
    payload = value["payload"]
    if command == "hello":
        if set(payload) != {"client_name", "client_version"}:
            raise _invalid(request_id)
        if not all(isinstance(payload[key], str) and payload[key] for key in payload):
            raise _invalid(request_id)
    elif command in {"warmup", "shutdown"}:
        if payload:
            raise _invalid(request_id)
    elif command == "process":
        if set(payload) != {"audio_path", "style", "debug"}:
            raise _invalid(request_id)
        if not isinstance(payload["audio_path"], str) or not payload["audio_path"]:
            raise _invalid(request_id)
        if payload["style"] not in STYLES:
            raise _invalid(request_id)
        if type(payload["debug"]) is not bool:
            raise _invalid(request_id)
    else:
        raise _invalid(request_id)

    return Command(value["id"], command, payload)


def event(request_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "event": name,
        "payload": payload,
    }


def error_event(
    request_id: str, code: str, message: str, recoverable: bool = True
) -> dict[str, Any]:
    return event(
        request_id,
        "error",
        {"code": code, "message": message, "recoverable": recoverable},
    )
