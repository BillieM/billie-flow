"""Prefetch and load the two fixed production models into the HF cache."""

from __future__ import annotations

import json
import sys

from . import ASR_MODEL, CLEANUP_MODEL
from .runtime import MLXRuntime


def main() -> int:
    runtime = MLXRuntime()
    try:
        runtime.load_asr()
        runtime.load_cleanup()
    except Exception as exc:
        print(
            json.dumps(
                {"status": "error", "cause": type(exc).__name__},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "ready",
                "asr_model": ASR_MODEL,
                "cleanup_model": CLEANUP_MODEL,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
