#!/usr/bin/env python3
"""Run cleanup model/style passes over completed ASR transcripts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KNOWN_VOCABULARY = ["Wispr Flow", "Billie Flow", "LLM", "MacBook"]
VOCABULARY_CORRECTIONS = [
    ("Whisperflow", "Wispr Flow"),
    ("whisperflow", "Wispr Flow"),
    ("WhisperFlow", "Wispr Flow"),
    ("Whisper Flow", "Wispr Flow"),
    ("whisper flow", "Wispr Flow"),
    ("with the flow", "Wispr Flow"),
    ("with flow", "Wispr Flow"),
    ("BillyFlow", "Billie Flow"),
    ("Billy Flow", "Billie Flow"),
    ("Billy flow", "Billie Flow"),
    ("billy flow", "Billie Flow"),
    ("LLL", "LLM"),
    ("lll", "LLM"),
    ("Macbook", "MacBook"),
    ("macbook", "MacBook"),
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def slug(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in text).strip("-")


def build_prompt(source: dict[str, Any], style: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are cleaning a Billie voice memo transcript for a local dictation app bake-off. "
        "Preserve the speaker's meaning, roughness, uncertainty, and project vocabulary. "
        "Known vocabulary: Wispr Flow, Billie Flow, LLM, MacBook. "
        "Correct obvious ASR vocabulary errors: Whisperflow or Whisper Flow means Wispr Flow; "
        "Billy Flow means Billie Flow; LLL means LLM; Macbook means MacBook. "
        "Return only the requested cleaned text. No preamble, no Markdown fence, no commentary."
    )
    user = f"""Source ASR backend: {source.get("id")}
Style: {style.get("label")}
Style instruction: {style.get("prompt")}

Raw ASR transcript:
{source.get("stitched_transcript", "").strip()}

Output only the cleaned text for this style."""
    return system, user


def cleanup_raw_rel(source_id: str, model_id: str, style_id: str) -> Path:
    return (
        Path("raw")
        / "cleanup"
        / slug(source_id)
        / slug(model_id)
        / f"{slug(style_id)}.json"
    )


def style_result_from_raw(raw_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{raw_record['source_asr_id']}::{raw_record['cleanup_model_id']}::{raw_record['style_id']}",
        "source_asr_id": raw_record["source_asr_id"],
        "source_asr_label": raw_record.get("source_asr_label", raw_record["source_asr_id"]),
        "style_id": raw_record["style_id"],
        "style_label": raw_record.get("style_label", raw_record["style_id"]),
        "cleanup_model_id": raw_record["cleanup_model_id"],
        "cleanup_model_label": raw_record.get("cleanup_model_label", raw_record["cleanup_model_id"]),
        "model_ref": raw_record.get("model_ref"),
        "runtime": raw_record.get("runtime"),
        "status": raw_record.get("status", "complete"),
        "runtime_seconds": raw_record.get("runtime_seconds"),
        "model_load_seconds": raw_record.get("model_load_seconds"),
        "prompt_id": f"{raw_record['style_id']}.v1",
        "output": raw_record.get("output", ""),
        "postprocess_corrections": raw_record.get("postprocess_corrections", []),
        "errors": raw_record.get("errors", []),
        "review": {},
    }


def render_chat_prompt(tokenizer: Any, system: str, user: str) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if getattr(tokenizer, "has_chat_template", False):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    return f"System:\n{system}\n\nUser:\n{user}\n\nAssistant:\n"


def clean_model_output(text: str) -> str:
    cleaned = text.strip()
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1].strip()
    if cleaned.startswith("<think>"):
        cleaned = ""
    for prefix in ("Assistant:", "assistant:", "Output:", "Cleaned text:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()
    return cleaned


def apply_vocabulary_corrections(text: str) -> tuple[str, list[dict[str, Any]]]:
    corrected = text
    applied: list[dict[str, Any]] = []
    for before, after in VOCABULARY_CORRECTIONS:
        count = corrected.count(before)
        if count:
            corrected = corrected.replace(before, after)
            applied.append({"from": before, "to": after, "count": count})
    return corrected, applied


def package_missing() -> bool:
    return importlib.util.find_spec("mlx_lm") is None


def run_mlx_cleanup(
    data: dict[str, Any],
    models: list[dict[str, Any]],
    styles: list[dict[str, Any]],
    output_base: Path,
    model_filter: set[str] | None,
    force: bool,
) -> list[dict[str, Any]]:
    from mlx_lm import generate, load

    completed_asr = [
        item
        for item in data.get("asr_results", [])
        if item.get("status") == "complete" and item.get("stitched_transcript")
    ]
    style_results: list[dict[str, Any]] = []
    checked_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    for cleanup_model in models:
        model_id = cleanup_model["id"]
        if model_filter and model_id not in model_filter:
            continue
        pairs = [(source, style) for source in completed_asr for style in styles]
        if not force:
            existing_records = []
            for source, style in pairs:
                rel_raw = cleanup_raw_rel(source["id"], model_id, style["id"])
                raw_path = output_base / rel_raw
                if not raw_path.exists():
                    existing_records = []
                    break
                raw_record = load_json(raw_path)
                if raw_record.get("status") != "complete":
                    existing_records = []
                    break
                existing_records.append(style_result_from_raw(raw_record))
            if existing_records:
                style_results.extend(existing_records)
                continue
        load_started = time.perf_counter()
        model, tokenizer = load(cleanup_model["model_ref"])
        load_seconds = time.perf_counter() - load_started
        for source, style in pairs:
            rel_raw = cleanup_raw_rel(source["id"], model_id, style["id"])
            raw_path = output_base / rel_raw
            if raw_path.exists() and not force:
                raw_record = load_json(raw_path)
                if raw_record.get("status") == "complete":
                    style_results.append(style_result_from_raw(raw_record))
                    continue
            system, user = build_prompt(source, style)
            prompt = render_chat_prompt(tokenizer, system, user)
            started = time.perf_counter()
            raw_text = generate(
                model,
                tokenizer,
                prompt,
                verbose=False,
                max_tokens=int(cleanup_model.get("max_tokens", 260)),
            )
            runtime_seconds = time.perf_counter() - started
            model_output = clean_model_output(raw_text)
            output, corrections = apply_vocabulary_corrections(model_output)
            raw_record = {
                "schema_version": "billie-flow.cleanup-output.v1",
                "status": "complete",
                "created_at": checked_at,
                "source_asr_id": source["id"],
                "source_asr_label": source.get("label", source["id"]),
                "style_id": style["id"],
                "style_label": style.get("label", style["id"]),
                "cleanup_model_id": model_id,
                "cleanup_model_label": cleanup_model.get("label", model_id),
                "model_ref": cleanup_model.get("model_ref"),
                "runtime": cleanup_model.get("runtime"),
                "model_load_seconds": load_seconds,
                "runtime_seconds": runtime_seconds,
                "system_prompt": system,
                "user_prompt": user,
                "raw_response": raw_text,
                "model_output": model_output,
                "postprocess_corrections": corrections,
                "output": output,
                "errors": [],
            }
            write_json(output_base / rel_raw, raw_record)
            style_results.append(
                {
                    "id": f"{source['id']}::{model_id}::{style['id']}",
                    "source_asr_id": source["id"],
                    "source_asr_label": source.get("label", source["id"]),
                    "style_id": style["id"],
                    "style_label": style.get("label", style["id"]),
                    "cleanup_model_id": model_id,
                    "cleanup_model_label": cleanup_model.get("label", model_id),
                    "model_ref": cleanup_model.get("model_ref"),
                    "runtime": cleanup_model.get("runtime"),
                    "status": "complete",
                    "runtime_seconds": runtime_seconds,
                    "model_load_seconds": load_seconds,
                    "prompt_id": f"{style['id']}.v1",
                    "output": output,
                    "postprocess_corrections": corrections,
                    "errors": [],
                    "review": {},
                }
            )
    return style_results


def blocked_cleanup_results(
    data: dict[str, Any],
    models: list[dict[str, Any]],
    styles: list[dict[str, Any]],
    output_base: Path,
    reason: str,
    model_filter: set[str] | None,
) -> list[dict[str, Any]]:
    completed_asr = [
        item
        for item in data.get("asr_results", [])
        if item.get("status") == "complete" and item.get("stitched_transcript")
    ]
    created_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    results: list[dict[str, Any]] = []
    for cleanup_model in models:
        model_id = cleanup_model["id"]
        if model_filter and model_id not in model_filter:
            continue
        for source in completed_asr:
            for style in styles:
                rel_raw = (
                    Path("raw")
                    / "cleanup"
                    / slug(source["id"])
                    / slug(model_id)
                    / f"{slug(style['id'])}.blocked.json"
                )
                raw_record = {
                    "schema_version": "billie-flow.cleanup-output.v1",
                    "status": "blocked",
                    "created_at": created_at,
                    "source_asr_id": source["id"],
                    "style_id": style["id"],
                    "cleanup_model_id": model_id,
                    "model_ref": cleanup_model.get("model_ref"),
                    "output": "",
                    "errors": [reason],
                }
                write_json(output_base / rel_raw, raw_record)
                results.append(
                    {
                        "id": f"{source['id']}::{model_id}::{style['id']}",
                        "source_asr_id": source["id"],
                        "source_asr_label": source.get("label", source["id"]),
                        "style_id": style["id"],
                        "style_label": style.get("label", style["id"]),
                        "cleanup_model_id": model_id,
                        "cleanup_model_label": cleanup_model.get("label", model_id),
                        "model_ref": cleanup_model.get("model_ref"),
                        "runtime": cleanup_model.get("runtime"),
                        "status": "blocked",
                        "output": "",
                        "errors": [reason],
                        "review": {},
                    }
                )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--styles", default=ROOT / "configs" / "cleanup_styles.json", type=Path
    )
    parser.add_argument(
        "--models", default=ROOT / "configs" / "cleanup_models.json", type=Path
    )
    parser.add_argument("--model", action="append", dest="model_filter")
    parser.add_argument("--force", action="store_true", help="Regenerate even when raw cleanup JSON exists.")
    parser.add_argument(
        "--blocked-only",
        action="store_true",
        help="Write blocked cleanup records without attempting local generation.",
    )
    args = parser.parse_args()

    data = load_json(args.input)
    styles = load_json(args.styles).get("styles", [])
    models = load_json(args.models).get("models", [])
    model_filter = set(args.model_filter) if args.model_filter else None

    if args.blocked_only:
        style_results = blocked_cleanup_results(
            data,
            models,
            styles,
            args.input.parent,
            "Cleanup generation was explicitly run in blocked-only mode.",
            model_filter,
        )
    elif package_missing():
        style_results = blocked_cleanup_results(
            data,
            models,
            styles,
            args.input.parent,
            "mlx_lm is not importable in the active Python runtime.",
            model_filter,
        )
    else:
        style_results = run_mlx_cleanup(
            data,
            models,
            styles,
            args.input.parent,
            model_filter,
            args.force,
        )

    if model_filter:
        kept = [
            item
            for item in data.get("style_results", [])
            if item.get("cleanup_model_id") not in model_filter
        ]
        data["style_results"] = kept + style_results
    else:
        data["style_results"] = style_results
    data.setdefault("run", {})["cleanup_generated_at"] = (
        datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    write_json(args.output, data)
    print(f"Wrote {len(style_results)} cleanup results to {args.output}")


if __name__ == "__main__":
    main()
