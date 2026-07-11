#!/usr/bin/env python3
"""Run the exact Voxtral Mini ASR candidate and save raw JSON."""

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="mistralai/Voxtral-Mini-3B-2507")
    parser.add_argument("--language", default="en")
    parser.add_argument("--max-new-tokens", type=int, default=384)
    args = parser.parse_args()

    started = time.perf_counter()
    record: dict[str, Any] = {
        "schema_version": "billie-flow.asr-output.v1",
        "id": "voxtral-mini-3b",
        "label": "Voxtral Mini 3B",
        "status": "failed",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model_ref": args.model,
        "runtime": "transformers",
        "chunking_strategy": "long-form",
        "text": "",
        "segments": [],
        "errors": [],
    }

    try:
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

        import torch
        from transformers import VoxtralForConditionalGeneration, VoxtralProcessor

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if device == "mps" else torch.float32
        record["device"] = device
        record["dtype"] = str(dtype).replace("torch.", "")

        processor = VoxtralProcessor.from_pretrained(args.model)
        model = VoxtralForConditionalGeneration.from_pretrained(args.model, dtype=dtype)
        model.eval()
        model.to(device)

        inputs = processor.apply_transcription_request(
            audio=str(args.audio),
            model_id=args.model,
            language=args.language,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = inputs.to(device=device, dtype=dtype)

        with torch.inference_mode():
            output_ids = model.generate(**inputs, max_new_tokens=args.max_new_tokens)
        generated_ids = output_ids[:, inputs.input_ids.shape[1] :]
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

        record.update(
            {
                "status": "complete",
                "runtime_seconds": time.perf_counter() - started,
                "language": args.language,
                "text": text,
                "segments": [{"id": 0, "start": None, "end": None, "text": text}],
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
