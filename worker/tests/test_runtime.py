from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from billie_flow_worker.runtime import (
    CleanupOutputTruncated,
    MLXRuntime,
    _normalise_model_output,
)


class StubTokenizer:
    def apply_chat_template(self, messages, **kwargs) -> str:
        assert kwargs == {"tokenize": False, "add_generation_prompt": True}
        return f"prompt:{messages[-1]['content']}"

    def encode(self, text: str, *, add_special_tokens: bool) -> list[str]:
        assert add_special_tokens is False
        return text.split()


def loaded_runtime() -> MLXRuntime:
    runtime = MLXRuntime()
    runtime.cleanup_loaded = True
    runtime._cleanup_model_object = object()
    runtime._cleanup_tokenizer = StubTokenizer()
    return runtime


def response(text: str, finish_reason: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(text=text, finish_reason=finish_reason)


def test_normalises_only_common_model_wrappers():
    assert _normalise_model_output('  "Hello there."  ') == "Hello there."
    assert _normalise_model_output("```text\nHello there.\n```") == "Hello there."
    assert _normalise_model_output("A 'quoted' word") == "A 'quoted' word"


def test_cleanup_accepts_only_generation_that_reaches_end_marker(monkeypatch):
    captured = {}

    def stream_generate(model, tokenizer, prompt, **kwargs):
        captured.update(kwargs)
        yield response("Complete ")
        yield response("text.", "stop")

    monkeypatch.setitem(
        sys.modules,
        "mlx_lm",
        SimpleNamespace(stream_generate=stream_generate),
    )

    assert loaded_runtime().cleanup("original words", "light-cleanup") == "Complete text."
    assert captured == {"max_tokens": 256}


def test_cleanup_raises_instead_of_returning_length_truncated_text(monkeypatch):
    def stream_generate(model, tokenizer, prompt, **kwargs):
        yield response("This output looks plausible but is incomplete", "length")

    monkeypatch.setitem(
        sys.modules,
        "mlx_lm",
        SimpleNamespace(stream_generate=stream_generate),
    )

    with pytest.raises(CleanupOutputTruncated):
        loaded_runtime().cleanup("original words", "message")


def test_long_cleanup_budget_scales_beyond_old_limit_and_remains_bounded(monkeypatch):
    captured_budgets: list[int] = []

    def stream_generate(model, tokenizer, prompt, **kwargs):
        captured_budgets.append(kwargs["max_tokens"])
        yield response("complete", "stop")

    monkeypatch.setitem(
        sys.modules,
        "mlx_lm",
        SimpleNamespace(stream_generate=stream_generate),
    )
    runtime = loaded_runtime()

    runtime.cleanup("word " * 1500, "verbatim-context-corrected")
    runtime.cleanup("word " * 10_000, "light-cleanup")

    assert captured_budgets == [2378, 4096]
