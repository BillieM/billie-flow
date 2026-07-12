#!/usr/bin/env python3
"""Run the production NDJSON worker without printing dictated content or paths."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from typing import Any


DEFAULT_WORKER = os.path.expanduser(
    "~/Library/Application Support/Billie Flow/runtime/.venv/bin/billie-flow-worker"
)
TERMINAL_EVENTS = {"ready", "result", "error"}


def command(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "id": f"acceptance-{name}-{uuid.uuid4()}",
        "command": name,
        "payload": payload,
    }


def exchange(
    child: subprocess.Popen[str], request: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    assert child.stdin is not None and child.stdout is not None
    child.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
    child.stdin.flush()
    phases: list[str] = []
    while True:
        line = child.stdout.readline()
        if not line:
            raise RuntimeError("worker stdout ended before a terminal event")
        message = json.loads(line)
        if message.get("protocol_version") != 1:
            raise RuntimeError("worker returned a mismatched protocol version")
        if message.get("request_id") != request["id"]:
            raise RuntimeError("worker returned an unexpected request id")
        event = message.get("event")
        if event == "phase":
            phases.append(message["payload"]["phase"])
            continue
        if event not in TERMINAL_EVENTS:
            raise RuntimeError("worker returned an unknown event")
        return phases, message


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--worker", default=DEFAULT_WORKER)
    parser.add_argument(
        "--style",
        choices=["verbatim-context-corrected", "light-cleanup", "message"],
        default="light-cleanup",
    )
    args = parser.parse_args()

    child = subprocess.Popen(
        [args.worker],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    summary: dict[str, Any] = {"status": "error"}
    try:
        _, ready = exchange(
            child,
            command(
                "hello",
                {"client_name": "Billie Flow Acceptance", "client_version": "0.1.0"},
            ),
        )
        if ready["event"] != "ready":
            raise RuntimeError("hello failed")
        warmup_started = time.perf_counter()
        warmup_phases, warmup = exchange(child, command("warmup", {}))
        warmup_seconds = time.perf_counter() - warmup_started
        if warmup["event"] != "result" or warmup["payload"].get("kind") != "warmup":
            raise RuntimeError("warmup failed")

        process_started = time.perf_counter()
        process_phases, processed = exchange(
            child,
            command(
                "process",
                {"audio_path": args.audio, "style": args.style, "debug": False},
            ),
        )
        wall_seconds = time.perf_counter() - process_started
        if processed["event"] != "result" or processed["payload"].get("kind") != "process":
            code = processed.get("payload", {}).get("code", "unknown")
            raise RuntimeError(f"process failed with code {code}")
        payload = processed["payload"]
        if not payload["final_text"].strip():
            raise RuntimeError("process returned empty final text")

        _, shutdown = exchange(child, command("shutdown", {}))
        if shutdown["event"] != "result" or shutdown["payload"].get("kind") != "shutdown":
            raise RuntimeError("shutdown failed")
        child.wait(timeout=5)
        stderr = child.stderr.read() if child.stderr is not None else ""
        private_stderr = any(
            value and value in stderr
            for value in (args.audio, payload["raw_asr"], payload["final_text"])
        )
        if private_stderr:
            raise RuntimeError("worker stderr disclosed audio or transcript content")
        summary = {
            "status": "ok",
            "warmup_seconds": warmup_seconds,
            "warmup_phases": warmup_phases,
            "process_wall_seconds": wall_seconds,
            "process_phases": process_phases,
            "timings": payload["timings"],
            "asr_model": payload["asr_model"],
            "cleanup_model": payload["cleanup_model"],
            "style": payload["style"],
            "warning": payload["warning"],
            "raw_asr_characters": len(payload["raw_asr"]),
            "final_characters": len(payload["final_text"]),
            "correction_count": sum(item["count"] for item in payload["corrections"]),
            "stderr_bytes": len(stderr.encode("utf-8")),
            "stderr_private_content": False,
            "worker_exit_code": child.returncode,
        }
    except Exception as exc:
        summary = {"status": "error", "cause": type(exc).__name__, "message": str(exc)}
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
    print(json.dumps(summary, separators=(",", ":")))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
