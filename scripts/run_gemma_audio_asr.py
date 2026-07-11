#!/usr/bin/env python3
"""Run a Gemma4 audio-capable ASR candidate and save raw JSON."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import soundfile as sf


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def chunk_audio(audio: Any, sample_rate: int, chunk_seconds: float, overlap_seconds: float) -> list[dict[str, Any]]:
    chunk_size = int(chunk_seconds * sample_rate)
    overlap = int(overlap_seconds * sample_rate)
    step = max(1, chunk_size - overlap)
    total = len(audio)
    chunks = []
    start = 0
    index = 0
    while start < total:
        end = min(total, start + chunk_size)
        chunks.append(
            {
                "index": index,
                "start_sample": start,
                "end_sample": end,
                "start": start / sample_rate,
                "end": end / sample_rate,
                "audio": audio[start:end],
            }
        )
        if end >= total:
            break
        start += step
        index += 1
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="google/gemma-4-12b-it")
    parser.add_argument("--id", default="gemma-4-12b-audio")
    parser.add_argument("--label", default="Gemma 4 12B Audio")
    parser.add_argument("--chunk-seconds", type=float, default=25.0)
    parser.add_argument("--overlap-seconds", type=float, default=2.0)
    parser.add_argument("--max-new-tokens", type=int, default=220)
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
        "chunking_strategy": f"fixed-{args.chunk_seconds:g}s-overlap-{args.overlap_seconds:g}s",
        "text": "",
        "segments": [],
        "errors": [],
        "warnings": [],
    }

    try:
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        audio, sample_rate = sf.read(args.audio)
        if getattr(audio, "ndim", 1) > 1:
            audio = audio.mean(axis=1)
        if sample_rate != 16000:
            raise ValueError(f"Expected 16 kHz audio, got {sample_rate} Hz")

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if device == "mps" else torch.float32
        record["device"] = device
        record["dtype"] = str(dtype).replace("torch.", "")

        processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(args.model, dtype=dtype, trust_remote_code=True)
        model.eval()
        model.to(device)

        segments = []
        texts = []
        for chunk in chunk_audio(audio, sample_rate, args.chunk_seconds, args.overlap_seconds):
            prompt = processor.apply_chat_template(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "audio", "audio": chunk["audio"]},
                            {
                                "type": "text",
                                "text": (
                                    "Transcribe this audio exactly. Return only the transcript. "
                                    "Do not summarize or explain."
                                ),
                            },
                        ],
                    }
                ],
                tokenize=False,
                add_generation_prompt=True,
            )
            inputs = processor(
                text=prompt,
                audio=[chunk["audio"]],
                sampling_rate=sample_rate,
                return_tensors="pt",
            )
            inputs = inputs.to(device=device, dtype=dtype)
            with torch.inference_mode():
                output_ids = model.generate(**inputs, max_new_tokens=args.max_new_tokens)
            generated_ids = output_ids[:, inputs.input_ids.shape[1] :]
            text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            texts.append(text)
            segments.append(
                {
                    "id": chunk["index"],
                    "start": chunk["start"],
                    "end": chunk["end"],
                    "text": text,
                }
            )

        record.update(
            {
                "status": "complete",
                "runtime_seconds": time.perf_counter() - started,
                "language": "en",
                "text": " ".join(text for text in texts if text).strip(),
                "segments": segments,
                "audio_duration_seconds": len(audio) / sample_rate,
                "errors": [],
            }
        )
        if args.model == "google/gemma-4-12b-it":
            record["warnings"].append(
                "Original configured Hub id google/gemma-4-12b-audio does not exist; used public audio-capable google/gemma-4-12b-it."
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
