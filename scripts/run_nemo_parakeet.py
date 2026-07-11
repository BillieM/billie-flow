#!/usr/bin/env python3
"""Run the exact NVIDIA Parakeet ASR candidate and save raw JSON."""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def normalize_hypothesis(value: Any) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    raw_meta: dict[str, Any] = {}
    if isinstance(value, str):
        return value, [], raw_meta
    if isinstance(value, (list, tuple)) and value:
        return normalize_hypothesis(value[0])
    text = getattr(value, "text", "") or str(value)
    raw_meta["type"] = type(value).__name__
    timestamps = getattr(value, "timestamp", None) or {}
    segments = []
    if isinstance(timestamps, dict):
        for index, item in enumerate(timestamps.get("segment", []) or []):
            if isinstance(item, dict):
                segments.append(
                    {
                        "id": index,
                        "start": item.get("start"),
                        "end": item.get("end"),
                        "text": item.get("segment") or item.get("text") or "",
                    }
                )
    return text, segments, raw_meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="nvidia/parakeet-tdt-0.6b-v3")
    args = parser.parse_args()

    started = time.perf_counter()
    record: dict[str, Any] = {
        "schema_version": "billie-flow.asr-output.v1",
        "id": "parakeet-tdt-0.6b-v3",
        "label": "Parakeet TDT 0.6B v3",
        "status": "failed",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model_ref": args.model,
        "runtime": "nemo",
        "chunking_strategy": "whole-file",
        "text": "",
        "segments": [],
        "errors": [],
    }

    try:
        os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/billie-flow-mpl")
        os.environ.setdefault("XDG_CACHE_HOME", "/private/tmp/billie-flow-cache")
        os.environ.setdefault("LHOTSE_TOOLS", "/private/tmp/billie-flow-lhotse")

        import torch
        from nemo.collections.asr.models import EncDecRNNTBPEModel

        model = EncDecRNNTBPEModel.from_pretrained(model_name=args.model)
        model.eval()
        if torch.backends.mps.is_available():
            model = model.to("mps")
            record["device"] = "mps"
        else:
            record["device"] = "cpu"
        with torch.no_grad():
            result = model.transcribe(
                [str(args.audio)],
                batch_size=1,
                return_hypotheses=True,
                timestamps=True,
            )
        text, segments, raw_meta = normalize_hypothesis(result)
        record.update(
            {
                "status": "complete",
                "runtime_seconds": time.perf_counter() - started,
                "text": text.strip(),
                "segments": segments
                or [{"id": 0, "start": None, "end": None, "text": text.strip()}],
                "raw_meta": raw_meta,
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
