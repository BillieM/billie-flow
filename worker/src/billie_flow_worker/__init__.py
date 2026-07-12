"""Billie Flow's private, persistent offline worker."""

from __future__ import annotations

PROTOCOL_VERSION = 1
WORKER_VERSION = "0.1.0"
ASR_MODEL = "mlx-community/whisper-large-v3-turbo"
CLEANUP_MODEL = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
LANGUAGE = "en"
CORRECTIONS_VERSION = "1"
STYLES = (
    "verbatim-context-corrected",
    "light-cleanup",
    "message",
)

KNOWN_VOCABULARY = (
    "Billie Flow",
    "Wispr Flow",
    "LLM",
    "MacBook",
    "SwiftUI",
    "MLX",
    "Hugging Face",
    "Qwen",
)

__all__ = [
    "ASR_MODEL",
    "CLEANUP_MODEL",
    "CORRECTIONS_VERSION",
    "KNOWN_VOCABULARY",
    "LANGUAGE",
    "PROTOCOL_VERSION",
    "STYLES",
    "WORKER_VERSION",
]
