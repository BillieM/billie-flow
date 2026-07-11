#!/usr/bin/env python3
"""Validate the Billie Flow results contract without external dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_STYLES = {
    "verbatim-context-corrected",
    "light-cleanup",
    "message",
    "email",
    "notes",
    "blog-draft",
    "command",
}

FORBIDDEN_PUBLIC_KEYS = {
    "model_output",
    "raw_output",
    "raw_response",
    "system_prompt",
    "user_prompt",
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def require_keys(errors: list[str], where: str, obj: dict[str, Any], keys: list[str]) -> None:
    for key in keys:
        if key not in obj:
            fail(errors, f"{where} missing {key}")


def reject_local_evidence(errors: list[str], value: Any, where: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_where = f"{where}.{key}"
            if key in FORBIDDEN_PUBLIC_KEYS:
                fail(errors, f"{child_where} is local-only and must not be published")
            reject_local_evidence(errors, child, child_where)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_local_evidence(errors, child, f"{where}[{index}]")


def validate(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    reject_local_evidence(errors, data)
    require_keys(errors, "root", data, ["run", "asr_results", "style_results", "recommendations"])
    run = data.get("run", {})
    require_keys(errors, "run", run, ["id", "title", "audio_file", "duration_seconds"])

    asr_ids = set()
    complete_asr_ids = set()
    for index, item in enumerate(data.get("asr_results", [])):
        where = f"asr_results[{index}]"
        require_keys(errors, where, item, ["id", "label", "status", "chunking_strategy", "review"])
        asr_ids.add(item.get("id"))
        if item.get("status") == "complete":
            complete_asr_ids.add(item.get("id"))
            require_keys(errors, where, item, ["chunks", "stitched_transcript"])
            if not item.get("stitched_transcript"):
                fail(errors, f"{where} complete result has empty stitched_transcript")
        elif not item.get("errors"):
            fail(errors, f"{where} blocked/non-complete result should include errors")

    expected_asr = {
        "mlx-whisper-large-v3-turbo",
        "mlx-whisper-tiny",
        "gemma-4-12b-audio",
        "voxtral-mini-3b",
        "parakeet-tdt-0.6b-v3",
    }
    missing_asr = expected_asr - asr_ids
    if missing_asr:
        fail(errors, f"missing ASR result(s): {', '.join(sorted(missing_asr))}")

    styles_by_asr: dict[str, set[str]] = {}
    for index, item in enumerate(data.get("style_results", [])):
        where = f"style_results[{index}]"
        require_keys(
            errors,
            where,
            item,
            ["id", "source_asr_id", "style_id", "cleanup_model_id", "status", "review"],
        )
        if item.get("source_asr_id") not in complete_asr_ids:
            fail(errors, f"{where} references non-complete ASR {item.get('source_asr_id')}")
        styles_by_asr.setdefault(item.get("source_asr_id"), set()).add(item.get("style_id"))
        if item.get("status") == "complete" and not item.get("output"):
            fail(errors, f"{where} complete result has empty output")

    for asr_id in complete_asr_ids:
        missing_styles = REQUIRED_STYLES - styles_by_asr.get(asr_id, set())
        if missing_styles:
            fail(errors, f"{asr_id} missing cleanup style(s): {', '.join(sorted(missing_styles))}")

    defaults = data.get("evaluations", {}).get("recommended_defaults", {})
    require_keys(
        errors,
        "evaluations.recommended_defaults",
        defaults,
        [
            "default_asr_backend",
            "fallback_asr_backend",
            "default_cleanup_model",
            "default_cleanup_style",
        ],
    )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    errors = validate(args.path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print(f"Valid Billie Flow results: {args.path}")


if __name__ == "__main__":
    main()
