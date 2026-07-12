"""Explicit tiny-model smoke; never used by the production protocol CLI."""

from __future__ import annotations

import argparse
import json
import time
from importlib.resources import files

from .audio import validate_pcm_wav
from .runtime import MLXRuntime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument(
        "--config",
        default=str(files("billie_flow_worker").joinpath("smoke_models.json")),
    )
    args = parser.parse_args()
    if not validate_pcm_wav(args.audio):
        print(json.dumps({"status": "error", "stage": "audio_validation"}))
        return 2

    with open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    runtime = MLXRuntime(config["asr_model"], config["cleanup_model"])
    timings: dict[str, float] = {}
    try:
        started = time.perf_counter()
        runtime.load_asr()
        timings["load_asr_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        raw = runtime.transcribe(args.audio).strip()
        timings["asr_seconds"] = time.perf_counter() - started
        if not raw:
            raise ValueError("empty transcript")
        started = time.perf_counter()
        runtime.load_cleanup()
        timings["load_cleanup_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        cleaned = runtime.cleanup(raw, "light-cleanup").strip()
        timings["cleanup_seconds"] = time.perf_counter() - started
        if not cleaned:
            raise ValueError("empty cleanup")
    except Exception as exc:
        print(
            json.dumps(
                {"status": "error", "cause": type(exc).__name__},
                separators=(",", ":"),
            )
        )
        return 1
    print(
        json.dumps(
            {"status": "ok", "nonempty": True, "timings": timings},
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
