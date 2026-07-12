"""Deterministic protocol worker for native integration tests."""

from __future__ import annotations

import os
import sys

from .service import run


class FakeRuntime:
    def __init__(self) -> None:
        self.asr_loaded = False
        self.cleanup_loaded = False
        self.mode = os.environ.get("BILLIE_FLOW_FAKE_MODE", "success")

    def load_asr(self) -> None:
        self.asr_loaded = True

    def load_cleanup(self) -> None:
        self.cleanup_loaded = True

    def transcribe(self, audio_path: str) -> str:
        if self.mode == "asr_failure":
            raise RuntimeError("injected")
        if self.mode == "empty":
            return "   "
        return "Billy Flow uses Swift UI and M L X."

    def cleanup(self, text: str, style: str) -> str:
        if self.mode == "cleanup_failure":
            raise RuntimeError("injected")
        return text


def main() -> int:
    return run(sys.stdin, sys.stdout, FakeRuntime())


if __name__ == "__main__":
    raise SystemExit(main())
