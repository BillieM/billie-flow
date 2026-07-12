"""Deterministic versioned vocabulary corrections."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rule:
    source: str
    target: str


# Ambiguous phrases, especially "with flow", deliberately do not appear here.
_RULES = (
    Rule("whisper flow", "Wispr Flow"),
    Rule("whisperflow", "Wispr Flow"),
    Rule("wisprflow", "Wispr Flow"),
    Rule("wisper flow", "Wispr Flow"),
    Rule("billy flow", "Billie Flow"),
    Rule("billie flo", "Billie Flow"),
    Rule("huggingface", "Hugging Face"),
    Rule("hugging-face", "Hugging Face"),
    Rule("swift ui", "SwiftUI"),
    Rule("mac book", "MacBook"),
    Rule("m l x", "MLX"),
    Rule("q-wen", "Qwen"),
    Rule("q wen", "Qwen"),
)

RULES = tuple(sorted(_RULES, key=lambda rule: (-len(rule.source), rule.source)))
_BY_SOURCE = {rule.source.casefold(): rule for rule in RULES}
_PATTERN = re.compile(
    "|".join(
        f"(?<!\\w)(?:{re.escape(rule.source)})(?!\\w)" for rule in RULES
    ),
    re.IGNORECASE,
)


def apply_corrections(text: str) -> tuple[str, list[dict[str, object]]]:
    """Apply all rules in one pass and return stable correction receipts."""

    counts: dict[str, int] = {}

    def replacement(match: re.Match[str]) -> str:
        rule = _BY_SOURCE[match.group(0).casefold()]
        counts[rule.source] = counts.get(rule.source, 0) + 1
        return rule.target

    corrected = _PATTERN.sub(replacement, text)
    receipts = [
        {"from": rule.source, "to": rule.target, "count": counts[rule.source]}
        for rule in RULES
        if rule.source in counts
    ]
    return corrected, receipts
