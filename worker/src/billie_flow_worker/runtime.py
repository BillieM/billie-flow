"""Injected model interface and the production MLX implementation."""

from __future__ import annotations

import contextlib
import io
from typing import Protocol

from . import ASR_MODEL, CLEANUP_MODEL
from .audio import read_pcm_wav
from .prompts import ASR_INITIAL_PROMPT, cleanup_messages


class ModelRuntime(Protocol):
    asr_loaded: bool
    cleanup_loaded: bool

    def load_asr(self) -> None: ...

    def load_cleanup(self) -> None: ...

    def transcribe(self, audio_path: str) -> str: ...

    def cleanup(self, text: str, style: str) -> str: ...


class _Discard(io.TextIOBase):
    def write(self, value: str) -> int:
        return len(value)


class MLXRuntime:
    """Lazily load fixed models once and retain them for the worker lifetime."""

    def __init__(
        self,
        asr_model: str = ASR_MODEL,
        cleanup_model: str = CLEANUP_MODEL,
    ) -> None:
        self.asr_model = asr_model
        self.cleanup_model = cleanup_model
        self.asr_loaded = False
        self.cleanup_loaded = False
        self._cleanup_model_object = None
        self._cleanup_tokenizer = None
        self._discard = _Discard()

    def load_asr(self) -> None:
        if self.asr_loaded:
            return
        with contextlib.redirect_stdout(self._discard):
            import mlx.core as mx
            from mlx_whisper.transcribe import ModelHolder

            ModelHolder.get_model(self.asr_model, mx.float16)
        self.asr_loaded = True

    def load_cleanup(self) -> None:
        if self.cleanup_loaded:
            return
        with contextlib.redirect_stdout(self._discard):
            from mlx_lm import load

            model, tokenizer = load(self.cleanup_model, lazy=False)
        self._cleanup_model_object = model
        self._cleanup_tokenizer = tokenizer
        self.cleanup_loaded = True

    def transcribe(self, audio_path: str) -> str:
        if not self.asr_loaded:
            raise RuntimeError("ASR model is not loaded")
        samples = read_pcm_wav(audio_path)
        with contextlib.redirect_stdout(self._discard):
            from mlx_whisper import transcribe

            result = transcribe(
                samples,
                path_or_hf_repo=self.asr_model,
                language="en",
                task="transcribe",
                initial_prompt=ASR_INITIAL_PROMPT,
                condition_on_previous_text=True,
                verbose=None,
            )
        return str(result.get("text", ""))

    def cleanup(self, text: str, style: str) -> str:
        if not self.cleanup_loaded or self._cleanup_tokenizer is None:
            raise RuntimeError("Cleanup model is not loaded")

        messages = cleanup_messages(text, style)
        with contextlib.redirect_stdout(self._discard):
            from mlx_lm import generate

            prompt = self._cleanup_tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            output = generate(
                self._cleanup_model_object,
                self._cleanup_tokenizer,
                prompt,
                verbose=False,
                max_tokens=max(64, min(1024, len(text) // 2 + 64)),
            )
        return _normalise_model_output(output)


def _normalise_model_output(value: str) -> str:
    output = value.strip()
    if output.startswith("```") and output.endswith("```"):
        lines = output.splitlines()
        if len(lines) >= 2:
            output = "\n".join(lines[1:-1]).strip()
    if len(output) >= 2 and output[0] == output[-1] and output[0] in {'"', "'"}:
        output = output[1:-1].strip()
    return output
