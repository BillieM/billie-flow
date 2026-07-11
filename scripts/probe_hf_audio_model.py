#!/usr/bin/env python3
"""Probe a Hugging Face audio model path and save success/failure JSON."""

from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--task", default="automatic-speech-recognition")
    args = parser.parse_args()

    started = time.perf_counter()
    record: dict[str, Any] = {
        "schema_version": "billie-flow.asr-output.v1",
        "id": args.id,
        "label": args.label,
        "status": "failed",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model_ref": args.model,
        "runtime": "transformers",
        "chunking_strategy": "whole-file",
        "text": "",
        "segments": [],
        "errors": [],
    }
    try:
        import torch
        from transformers import pipeline

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        pipe = pipeline(
            args.task,
            model=args.model,
            device=device,
            trust_remote_code=True,
        )
        result = pipe(str(args.audio))
        if isinstance(result, dict):
            text = result.get("text", "")
            chunks = result.get("chunks") or []
        else:
            text = str(result)
            chunks = []
        record.update(
            {
                "status": "complete",
                "device": device,
                "runtime_seconds": time.perf_counter() - started,
                "text": text.strip(),
                "segments": [
                    {
                        "id": index,
                        "start": (chunk.get("timestamp") or [None, None])[0],
                        "end": (chunk.get("timestamp") or [None, None])[1],
                        "text": chunk.get("text", ""),
                    }
                    for index, chunk in enumerate(chunks)
                    if isinstance(chunk, dict)
                ]
                or [{"id": 0, "start": None, "end": None, "text": text.strip()}],
                "raw_result": result,
                "errors": [],
            }
        )
    except Exception as exc:  # noqa: BLE001 - this is an experiment recorder.
        record.update(
            {
                "status": "failed",
                "runtime_seconds": time.perf_counter() - started,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "traceback": traceback.format_exc(),
            }
        )
    write_json(args.output, record)
    print(f"Wrote {args.output} ({record['status']})")
    if record["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
