#!/usr/bin/env python3
"""Add evaluator scores, warnings, and app recommendations to results JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REFERENCE_TERMS = ["Wispr Flow", "Billie Flow", "LLM", "MacBook"]
ASR_TERM_ERRORS = {
    "Wispr Flow": ["Whisperflow", "WhisperFlow", "whisper flow", "with flow", "with the flow"],
    "Billie Flow": ["Billy Flow", "BillyFlow", "Billy flow"],
    "LLM": ["LLL"],
    "MacBook": ["Macbook"],
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


LOCAL_ONLY_KEYS = {
    "model_output",
    "raw_output",
    "raw_response",
    "system_prompt",
    "user_prompt",
}


def strip_local_evidence(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_local_evidence(child)
            for key, child in value.items()
            if key not in LOCAL_ONLY_KEYS
        }
    if isinstance(value, list):
        return [strip_local_evidence(child) for child in value]
    return value


def contains_term(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text, flags=re.IGNORECASE) is not None


def vocabulary_findings(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for term in REFERENCE_TERMS:
        observed = contains_term(text, term)
        aliases = [alias for alias in ASR_TERM_ERRORS.get(term, []) if alias in text]
        findings.append(
            {
                "term": term,
                "status": "correct" if observed else "missing-or-wrong",
                "observed_errors": aliases,
            }
        )
    return findings


def score_asr(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("status") != "complete":
        return item.get("review", {})
    text = item.get("stitched_transcript", "")
    findings = vocabulary_findings(text)
    wrong_terms = [f for f in findings if f["status"] != "correct"]
    base_accuracy = 5 - min(3, len(wrong_terms))
    if item["id"] == "mlx-whisper-large-v3-turbo":
        rank = 1
        summary = (
            "Best default ASR result. It is fast, coherent, and hears LLM, "
            "but still needs vocabulary correction for Wispr Flow and Billie Flow."
        )
        strengths = [
            "Correctly hears local LLM",
            "Readable punctuation and casing",
            "Warm runtime is practical for a menu bar app",
        ]
        weaknesses = [
            "Normalizes Wispr Flow to Whisperflow",
            "Writes Billie Flow as Billy Flow",
            "Needs a vocabulary/context correction layer",
        ]
        latency = 4
        hallucination_risk = 1
    elif item["id"] == "parakeet-tdt-0.6b-v3":
        rank = 2
        summary = (
            "Strong lab candidate. It preserves filler and timing detail better than Whisper, "
            "but is much slower and still misses the product names."
        )
        strengths = [
            "Preserves ums and spoken cadence",
            "Produces useful timestamps",
            "Correctly hears local LLM and MacBook",
        ]
        weaknesses = [
            "Normalizes Wispr Flow to Whisperflow",
            "Writes Billie Flow as Billy Flow",
            "Runtime is too slow for the first default on this memo",
        ]
        latency = 2
        hallucination_risk = 1
    elif item["id"] == "voxtral-mini-3b":
        rank = 3
        summary = (
            "High-readability lab candidate. It produces a clean transcript and gets LLM/MacBook, "
            "but the runtime is high and it collapses the project names."
        )
        strengths = [
            "Readable punctuation and casing",
            "Correctly hears local LLM and MacBook",
            "Runs through the current Transformers Voxtral path on MPS",
        ]
        weaknesses = [
            "Writes Wispr Flow as WhisperFlow",
            "Writes Billie Flow as BillyFlow",
            "Much slower than the MLX Whisper default",
        ]
        latency = 1
        hallucination_risk = 1
    elif item["id"] == "gemma-4-12b-audio":
        rank = 4
        summary = (
            "Completed, but not default-worthy. The public audio-capable Gemma 4 12B checkpoint ran, "
            "but chunk overlap introduced text drift and the path is far slower than Whisper."
        )
        strengths = [
            "Public Gemma 4 12B audio-capable checkpoint can run locally through Transformers",
            "Correctly hears local LLM and MacBook",
            "Useful evidence for the native-audio branch",
        ]
        weaknesses = [
            "The originally named google/gemma-4-12b-audio Hub id does not exist",
            "Chunk overlap produced drift around the Wispr Flow sentence",
            "Too slow and too fragile for the first app default",
        ]
        latency = 1
        hallucination_risk = 3
    elif item["id"] == "mlx-whisper-tiny":
        rank = 5
        summary = (
            "Good smoke test, not good enough for quality. It keeps the shape, "
            "but loses exactly the project vocabulary this app cares about."
        )
        strengths = ["Very fast warm runtime", "Captures the broad idea", "Useful for runner checks"]
        weaknesses = [
            "Hears LLM as LLL",
            "Splits Wispr Flow into the wrong phrase",
            "Lower confidence around key terms",
        ]
        latency = 5
        hallucination_risk = 2
    else:
        rank = 99
        summary = "Completed ASR path needs manual review."
        strengths = []
        weaknesses = [f"Missed {finding['term']}" for finding in wrong_terms]
        latency = 3
        hallucination_risk = 2

    return {
        "rank": rank,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "vocabulary": findings,
        "scores": {
            "accuracy": base_accuracy,
            "vocabulary": max(1, 5 - len(wrong_terms)),
            "readability": 5 if item["id"] in {"mlx-whisper-large-v3-turbo", "voxtral-mini-3b"} else 4,
            "latency": latency,
            "hallucination_risk": hallucination_risk,
        },
    }


def score_cleanup(item: dict[str, Any], asr_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if item.get("status") != "complete":
        return {
            "rank": None,
            "summary": "Blocked cleanup run.",
            "scores": {"fidelity": None, "usefulness": None, "voice_preservation": None, "style_fit": None, "invention_risk": None},
        }

    output = item.get("output", "")
    source = asr_by_id.get(item.get("source_asr_id"), {})
    source_rank = source.get("review", {}).get("rank", 99) or 99
    style = item.get("style_id")
    model = item.get("cleanup_model_id")
    corrected_terms = sum(1 for term in REFERENCE_TERMS if contains_term(output, term))
    has_source_error = any(alias in output for aliases in ASR_TERM_ERRORS.values() for alias in aliases)
    unwanted_preamble = output.lower().startswith(("sure", "here", "of course"))
    too_short = len(output.split()) < 18 and style not in {"message", "command"}

    fidelity = 3 + (1 if corrected_terms >= 3 else 0) + (1 if source_rank == 1 else 0)
    if has_source_error:
        fidelity -= 1
    if too_short:
        fidelity -= 1
    fidelity = max(1, min(5, fidelity))

    style_fit_base = {
        "verbatim-context-corrected": 4,
        "light-cleanup": 5,
        "message": 4,
        "email": 4,
        "notes": 4,
        "blog-draft": 3,
        "command": 4,
    }.get(style, 3)
    if unwanted_preamble:
        style_fit_base -= 1
    if style == "verbatim-context-corrected" and source_rank != 1:
        style_fit_base -= 1
    style_fit = max(1, min(5, style_fit_base))

    voice = {
        "verbatim-context-corrected": 5,
        "light-cleanup": 4,
        "message": 3,
        "email": 3,
        "notes": 3,
        "blog-draft": 4,
        "command": 2,
    }.get(style, 3)
    if model == "mlx-local-strong-text" and style in {"blog-draft", "email"}:
        voice = min(5, voice + 1)
    if unwanted_preamble:
        voice = max(1, voice - 1)

    usefulness = {
        "verbatim-context-corrected": 4,
        "light-cleanup": 5,
        "message": 4,
        "email": 4,
        "notes": 5,
        "blog-draft": 4,
        "command": 4,
    }.get(style, 3)
    if source_rank != 1:
        usefulness = max(1, usefulness - 1)

    invention_risk = 1
    if style in {"blog-draft", "email", "command"}:
        invention_risk = 2
    if unwanted_preamble or too_short:
        invention_risk += 1
    if source_rank != 1:
        invention_risk += 1

    combined = fidelity + usefulness + voice + style_fit - invention_risk
    summary_bits = []
    if style == "light-cleanup" and source_rank == 1:
        summary_bits.append("Best default-style candidate")
    elif style == "verbatim-context-corrected":
        summary_bits.append("Best audit-style candidate")
    elif style == "notes":
        summary_bits.append("Useful for scanning, less useful for fidelity review")
    elif style == "command":
        summary_bits.append("Useful as an advanced mode, not the first default")
    else:
        summary_bits.append("Useful style-specific transform")
    if source_rank != 1:
        summary_bits.append("source ASR errors still leak through")
    if corrected_terms >= 3:
        summary_bits.append("keeps the important vocabulary visible")
    return {
        "rank": None,
        "sort_score": combined,
        "summary": "; ".join(summary_bits) + ".",
        "scores": {
            "fidelity": fidelity,
            "usefulness": usefulness,
            "voice_preservation": voice,
            "style_fit": style_fit,
            "invention_risk": invention_risk,
        },
        "warnings": [
            warning
            for warning, active in [
                ("Still contains an ASR vocabulary error", has_source_error),
                ("Starts with assistant-style preamble", unwanted_preamble),
                ("Looks too compressed for this style", too_short),
                ("Uses deterministic vocabulary post-processing", bool(item.get("postprocess_corrections"))),
            ]
            if active
        ],
    }


def choose_default(style_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in style_results
        if item.get("status") == "complete"
        and item.get("source_asr_id") == "mlx-whisper-large-v3-turbo"
        and item.get("style_id") == "light-cleanup"
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item["review"].get("sort_score", 0), reverse=True)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reviews-output", type=Path)
    parser.add_argument(
        "--cleanup-models",
        default=Path(__file__).resolve().parents[1] / "configs" / "cleanup_models.json",
        type=Path,
    )
    args = parser.parse_args()

    data = strip_local_evidence(load_json(args.input))
    cleanup_model_config = load_json(args.cleanup_models)
    cleanup_model_blockers = []
    for model in cleanup_model_config.get("models", []):
        for blocker in model.get("blocked_candidates", []):
            cleanup_model_blockers.append(
                {
                    "cleanup_model_id": model.get("id"),
                    "cleanup_model_label": model.get("label", model.get("id")),
                    **blocker,
                }
            )
    data["schema_version"] = "billie-flow.results.v2"
    data.setdefault("run", {})["known_vocabulary"] = REFERENCE_TERMS
    data["run"]["audio_normalization"] = {
        "source": "input.m4a",
        "normalized": "input-16khz.wav",
        "sample_rate_hz": 16000,
        "channels": 1,
    }

    for asr in data.get("asr_results", []):
        asr["review"] = score_asr(asr)

    asr_by_id = {item["id"]: item for item in data.get("asr_results", [])}
    reviewed_styles: list[dict[str, Any]] = []
    for style in data.get("style_results", []):
        style["review"] = score_cleanup(style, asr_by_id)
        reviewed_styles.append(style)

    ranked_styles = sorted(
        [item for item in reviewed_styles if item.get("status") == "complete"],
        key=lambda item: item["review"].get("sort_score", 0),
        reverse=True,
    )
    for rank, item in enumerate(ranked_styles, start=1):
        item["review"]["rank"] = rank

    default_cleanup = choose_default(reviewed_styles)
    default_asr_backend = "mlx-whisper-large-v3-turbo"
    fallback_asr_backend = "mlx-whisper-tiny"
    lab_only_asr = [
        item
        for item in data.get("asr_results", [])
        if item.get("id") not in {default_asr_backend, fallback_asr_backend}
    ]
    blocked_asr = [item for item in data.get("asr_results", []) if item.get("status") != "complete"]
    data["evaluations"] = {
        "asr_rankings": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "status": item.get("status"),
                "rank": item.get("review", {}).get("rank"),
                "summary": item.get("review", {}).get("summary"),
            }
            for item in sorted(
                data.get("asr_results", []),
                key=lambda item: item.get("review", {}).get("rank") or 999,
            )
        ],
        "cleanup_rankings": [
            {
                "id": item.get("id"),
                "source_asr_id": item.get("source_asr_id"),
                "cleanup_model_id": item.get("cleanup_model_id"),
                "style_id": item.get("style_id"),
                "rank": item.get("review", {}).get("rank"),
                "sort_score": item.get("review", {}).get("sort_score"),
                "summary": item.get("review", {}).get("summary"),
            }
            for item in ranked_styles[:12]
        ],
        "recommended_defaults": {
            "default_asr_backend": default_asr_backend,
            "fallback_asr_backend": fallback_asr_backend,
            "fallback_note": "Tiny is a runner/smoke fallback only, not a quality fallback.",
            "default_cleanup_model": default_cleanup.get("cleanup_model_id") if default_cleanup else None,
            "default_cleanup_style": "light-cleanup",
            "default_combination_id": default_cleanup.get("id") if default_cleanup else None,
            "advanced_styles": [
                "verbatim-context-corrected",
                "message",
                "email",
                "notes",
                "blog-draft",
                "command",
            ],
            "lab_only_asr_backends": [item.get("id") for item in lab_only_asr],
        },
        "blocked_paths": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "status": item.get("status"),
                "errors": item.get("errors", []),
            }
            for item in blocked_asr
        ],
        "setup_findings": [
            {
                "id": "google/gemma-4-12b-audio",
                "status": "unavailable",
                "summary": "The originally configured Gemma audio Hub id is not a valid public model identifier. The run used google/gemma-4-12b-it instead and recorded that warning on the ASR result.",
            },
            {
                "id": "google/gemma-3n-E4B-it",
                "status": "gated",
                "summary": "Gemma 3n E4B is gated and was not available for this run.",
            },
        ],
        "lab_only_paths": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "status": item.get("status"),
                "summary": item.get("review", {}).get("summary"),
                "warnings": item.get("warnings", []),
                "runtime_seconds": item.get("runtime_seconds"),
            }
            for item in lab_only_asr
        ],
        "cleanup_model_blockers": cleanup_model_blockers,
        "vocabulary_failures": [
            {
                "asr_id": item.get("id"),
                "findings": item.get("review", {}).get("vocabulary", []),
            }
            for item in data.get("asr_results", [])
            if item.get("status") == "complete"
        ],
    }

    default_model_label = (
        default_cleanup.get("cleanup_model_label", default_cleanup.get("cleanup_model_id"))
        if default_cleanup
        else "No cleanup model completed"
    )
    data["recommendations"] = [
        {
            "level": "pick",
            "title": "Default ASR: MLX Whisper large-v3-turbo",
            "body": "It remains the best first app default: much faster than the native-audio alternatives, coherent, and correct on LLM. It still needs vocabulary correction for Wispr Flow and Billie Flow.",
        },
        {
            "level": "pick",
            "title": f"Default cleanup: {default_model_label} / light cleanup",
            "body": "Light cleanup is the right first app default because it removes dictation friction without pretending ASR mistakes did not happen.",
        },
        {
            "level": "watch",
            "title": "Keep vocabulary correction explicit",
            "body": "The report should keep raw ASR visible. Wispr Flow, Billie Flow, LLM, and MacBook are the terms to bias or repair first.",
        },
        {
            "level": "avoid",
            "title": "Do not ship Gemma, Voxtral, or Parakeet as defaults yet",
            "body": "They now run locally where public access allows, but they are slower and still miss the key vocabulary. Gemma also depends on the public google/gemma-4-12b-it checkpoint because the originally named google/gemma-4-12b-audio id does not exist.",
        },
    ]

    write_json(args.output, data)
    if args.reviews_output:
        write_json(
            args.reviews_output,
            {
                "schema_version": "billie-flow.reviews.v1",
                "evaluations": data["evaluations"],
                "recommendations": data["recommendations"],
            },
        )
    print(f"Wrote reviewed results to {args.output}")


if __name__ == "__main__":
    main()
