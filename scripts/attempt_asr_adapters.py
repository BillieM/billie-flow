#!/usr/bin/env python3
"""Record ASR adapter availability for the voice memo bake-off.

This script does not silently substitute models. If a requested audio model or
runtime is missing, it writes a blocked raw-output JSON file and updates the
manifest with that blocked branch.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HUB_DIR = Path.home() / ".cache" / "huggingface" / "hub"


ASR_REVIEWS: dict[str, dict[str, Any]] = {
    "gemma-4-12b-audio": {
        "rank": None,
        "summary": "Blocked locally. The cached Gemma checkpoint is text-only, not the requested audio-capable path.",
        "strengths": [],
        "weaknesses": [
            "No audio-capable Gemma checkpoint found in the local Hugging Face cache",
            "The project venv does not currently provide a Gemma audio runtime",
            "The cached mlx-community/gemma-4-12B-it-4bit text model was not substituted",
        ],
        "scores": {
            "accuracy": None,
            "readability": None,
            "latency": None,
            "hallucination_risk": None,
        },
    },
    "voxtral-mini-3b": {
        "rank": None,
        "summary": "Blocked locally. Voxtral Mini is not cached and the required Mistral audio runtime is unavailable in this venv.",
        "strengths": [],
        "weaknesses": [
            "No Voxtral Mini model cache found",
            "No local Mistral audio stack import path found",
            "Not safe to replace it with a text-only Mistral model",
        ],
        "scores": {
            "accuracy": None,
            "readability": None,
            "latency": None,
            "hallucination_risk": None,
        },
    },
    "parakeet-tdt-0.6b-v3": {
        "rank": None,
        "summary": "Blocked locally. Parakeet needs a NeMo or supported Transformers ASR setup that is not installed here.",
        "strengths": [],
        "weaknesses": [
            "No Parakeet model cache found",
            "NeMo ASR is not installed in the project venv",
            "Transformers is not installed in the project venv",
        ],
        "scores": {
            "accuracy": None,
            "readability": None,
            "latency": None,
            "hallucination_risk": None,
        },
    },
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def module_available(python: Path, module: str) -> bool:
    if not python.exists():
        return False
    result = subprocess.run(
        [str(python), "-c", f"import {module}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def hub_matches(*needles: str) -> list[str]:
    if not HUB_DIR.exists():
        return []
    matches: list[str] = []
    lowered = [needle.lower() for needle in needles]
    for child in HUB_DIR.iterdir():
        name = child.name.lower()
        if all(needle in name for needle in lowered):
            matches.append(child.name)
    return sorted(matches)


def check_model(model_id: str, python: Path) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            blockers.append(detail)

    if model_id == "gemma-4-12b-audio":
        audio_cache = hub_matches("gemma", "audio")
        text_cache = hub_matches("gemma-4-12b-it")
        add(
            "audio_checkpoint_cache",
            bool(audio_cache),
            "No audio-capable Gemma checkpoint is cached locally.",
        )
        add(
            "no_text_substitution",
            bool(audio_cache) or not text_cache,
            "Only a text Gemma cache is present; it is not a valid ASR/audio adapter.",
        )
        add(
            "transformers_runtime",
            module_available(python, "transformers"),
            "transformers is not installed in the project venv.",
        )
    elif model_id == "voxtral-mini-3b":
        voxtral_cache = hub_matches("voxtral")
        add("voxtral_cache", bool(voxtral_cache), "No Voxtral model cache is present.")
        add(
            "mistral_audio_runtime",
            module_available(python, "mistral_common"),
            "mistral_common is not installed in the project venv.",
        )
        add(
            "transformers_runtime",
            module_available(python, "transformers"),
            "transformers is not installed in the project venv.",
        )
    elif model_id == "parakeet-tdt-0.6b-v3":
        parakeet_cache = hub_matches("parakeet")
        add("parakeet_cache", bool(parakeet_cache), "No Parakeet model cache is present.")
        add(
            "nemo_asr_runtime",
            module_available(python, "nemo.collections.asr"),
            "NeMo ASR is not installed in the project venv.",
        )
        add(
            "transformers_runtime",
            module_available(python, "transformers"),
            "transformers is not installed in the project venv.",
        )
    return checks, blockers


def upsert_manifest_item(
    manifest: dict[str, Any],
    model: dict[str, Any],
    raw_json: str,
    raw_record: dict[str, Any],
) -> None:
    item = {
        "id": model["id"],
        "label": model.get("label", model["id"]),
        "status": raw_record["status"],
        "install_status": "blocked",
        "raw_json": raw_json,
        "runtime_seconds": None,
        "peak_memory_gb": None,
        "runtime": model.get("runtime"),
        "model_ref": model.get("model_ref"),
        "chunking_strategy": model.get("chunking_strategy"),
        "adapter": raw_record["adapter"],
        "errors": raw_record["errors"],
        "review": ASR_REVIEWS[model["id"]],
    }
    existing = manifest.setdefault("asr_inputs", [])
    for index, current in enumerate(existing):
        if current.get("id") == model["id"]:
            existing[index] = item
            return
    existing.append(item)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--models", default=ROOT / "configs" / "asr_models.json", type=Path)
    parser.add_argument("--python", default=ROOT / ".venv" / "bin" / "python", type=Path)
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    model_config = load_json(args.models)
    base_dir = args.manifest.parent
    checked_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    for model in model_config.get("models", []):
        model_id = model.get("id")
        if model_id not in ASR_REVIEWS:
            continue
        checks, blockers = check_model(model_id, args.python)
        raw_json = f"raw/asr/{model_id}.blocked.json"
        raw_record = {
            "schema_version": "billie-flow.asr-output.v1",
            "id": model_id,
            "label": model.get("label", model_id),
            "status": "blocked" if blockers else "ready-not-run",
            "checked_at": checked_at,
            "model_ref": model.get("model_ref"),
            "runtime": model.get("runtime"),
            "chunking_strategy": model.get("chunking_strategy"),
            "adapter": {
                "id": model_id,
                "kind": "availability-check",
                "script": "scripts/attempt_asr_adapters.py",
            },
            "checks": checks,
            "errors": blockers,
            "text": "",
            "segments": [],
        }
        write_json(base_dir / raw_json, raw_record)
        upsert_manifest_item(manifest, model, raw_json, raw_record)

    write_json(args.manifest, manifest)
    print(f"Wrote ASR adapter availability into {args.manifest}")


if __name__ == "__main__":
    main()
