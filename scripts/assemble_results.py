#!/usr/bin/env python3
"""Assemble Billie Flow report JSON from raw ASR outputs and a manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def segment_to_chunk(segment: dict[str, Any], fallback_index: int) -> dict[str, Any]:
    return {
        "index": int(segment.get("id", fallback_index)) + 1,
        "start_seconds": segment.get("start"),
        "end_seconds": segment.get("end"),
        "text": segment.get("text", "").strip(),
    }


def assemble_asr_result(base_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    raw_json = item.get("raw_json")
    raw_path = base_dir / raw_json if raw_json else None
    raw = load_json(raw_path) if raw_path and raw_path.exists() else {}
    status = raw.get("status", item.get("status", "complete"))
    segments = raw.get("segments", []) if status == "complete" else []
    result = {
        "id": item["id"],
        "label": item.get("label", item["id"]),
        "status": status,
        "install_status": item.get("install_status", "available" if status == "complete" else status),
        "runtime": raw.get("runtime", item.get("runtime")),
        "model_ref": raw.get("model_ref", item.get("model_ref")),
        "chunking_strategy": raw.get("chunking_strategy", item.get("chunking_strategy", "whole-file")),
        "runtime_seconds": raw.get("runtime_seconds", item.get("runtime_seconds")),
        "peak_memory_gb": raw.get("peak_memory_gb", item.get("peak_memory_gb")),
        "chunks": [segment_to_chunk(segment, index) for index, segment in enumerate(segments)],
        "stitched_transcript": raw.get("text", "").strip(),
        "language": raw.get("language"),
        "adapter": item.get("adapter", raw.get("adapter", {})),
        "errors": raw.get("errors", item.get("errors", [])),
        "warnings": raw.get("warnings", item.get("warnings", [])),
        "review": item.get("review", {}),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Experiment manifest JSON")
    parser.add_argument("--output", required=True, type=Path, help="Output results JSON")
    parser.add_argument(
        "--include-manifest-style-results",
        action="store_true",
        help="Carry style_results from the manifest. Off by default so manual prototypes do not leak into generated runs.",
    )
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    base_dir = args.manifest.parent
    results = {
        "schema_version": "billie-flow.results.v2",
        "run": manifest["run"],
        "asr_results": [
            assemble_asr_result(base_dir, item) for item in manifest.get("asr_inputs", [])
        ],
        "style_results": manifest.get("style_results", [])
        if args.include_manifest_style_results
        else [],
        "recommendations": manifest.get("recommendations", []),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
