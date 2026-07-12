#!/usr/bin/env python3
import json
import sys

ASR = "mlx-community/whisper-large-v3-turbo"
CLEANUP = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"

for line in sys.stdin:
    command = json.loads(line)
    request_id = command["id"]
    name = command["command"]
    if name == "hello":
        payload = {
            "worker_version": "0.1.0",
            "asr_model": ASR,
            "cleanup_model": CLEANUP,
            "language": "en",
            "corrections_version": "1",
        }
        event = "ready"
    elif name == "warmup":
        for phase in ("loading_asr", "loading_cleanup"):
            print(json.dumps({"protocol_version": 1, "request_id": request_id, "event": "phase", "payload": {"phase": phase}}), flush=True)
        event, payload = "result", {"kind": "warmup", "warmed": True}
    elif name == "process":
        for phase in ("transcribing", "cleaning", "correcting"):
            print(json.dumps({"protocol_version": 1, "request_id": request_id, "event": "phase", "payload": {"phase": phase}}), flush=True)
        event = "result"
        payload = {
            "kind": "process",
            "raw_asr": "Billy Flow fake result.",
            "raw_cleanup": "Billy Flow fake result.",
            "final_text": "Billie Flow fake result.",
            "corrections": [{"from": "Billy Flow", "to": "Billie Flow", "count": 1}],
            "timings": {"loading_asr_seconds": 0, "asr_seconds": 0.01, "loading_cleanup_seconds": 0, "cleanup_seconds": 0.01, "correction_seconds": 0.001, "total_seconds": 0.021},
            "asr_model": ASR,
            "cleanup_model": CLEANUP,
            "style": command["payload"]["style"],
            "warning": None,
        }
    elif name == "shutdown":
        event, payload = "result", {"kind": "shutdown"}
    else:
        event, payload = "error", {"code": "invalid_request", "message": "Invalid request.", "recoverable": False}
    print(json.dumps({"protocol_version": 1, "request_id": request_id, "event": event, "payload": payload}), flush=True)
    if name == "shutdown":
        break
