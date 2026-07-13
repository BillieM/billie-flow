"""Prefetch and load the two fixed production models into the HF cache."""

from __future__ import annotations

import argparse
import json
import sys

from . import ASR_MODEL, CLEANUP_MODEL
from .runtime import MLXRuntime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--component",
        choices=("all", "asr", "cleanup"),
        default="all",
        help="download and verify one fixed model or both",
    )
    args = parser.parse_args(argv)
    runtime = MLXRuntime()
    try:
        if args.component in {"all", "asr"}:
            runtime.load_asr()
        if args.component in {"all", "cleanup"}:
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
                "component": args.component,
                "asr_model": ASR_MODEL,
                "cleanup_model": CLEANUP_MODEL,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
