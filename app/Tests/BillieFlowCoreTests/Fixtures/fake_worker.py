#!/usr/bin/env python3
import json
import os
import sys
import time

ASR = "mlx-community/whisper-large-v3-turbo"
CLEANUP = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"

pid_file = os.environ.get("BILLIE_FLOW_FAKE_PID_FILE")
if pid_file:
    with open(pid_file, "a", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()}\n")
        handle.flush()

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
        delay_marker = os.environ.get("BILLIE_FLOW_FAKE_DELAY_ONCE_FILE")
        if delay_marker and not os.path.exists(delay_marker):
            with open(delay_marker, "w", encoding="utf-8") as handle:
                handle.write("delayed")
            time.sleep(float(os.environ.get("BILLIE_FLOW_FAKE_PROCESS_DELAY", "30")))
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
