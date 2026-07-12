from __future__ import annotations

import json
import wave
from pathlib import Path


def command(request_id: str, name: str, payload: dict) -> str:
    return json.dumps(
        {
            "protocol_version": 1,
            "id": request_id,
            "command": name,
            "payload": payload,
        }
    )


def write_wav(path: Path, *, rate: int = 16_000, channels: int = 1) -> Path:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\0\0" * (rate // 100))
    return path


class StubRuntime:
    def __init__(
        self,
        *,
        transcript: str = "Billy Flow uses Swift UI and M L X.",
        cleanup: str | None = None,
        fail_asr: bool = False,
        fail_cleanup: bool = False,
    ) -> None:
        self.asr_loaded = False
        self.cleanup_loaded = False
        self.transcript = transcript
        self.cleaned = transcript if cleanup is None else cleanup
        self.fail_asr = fail_asr
        self.fail_cleanup = fail_cleanup
        self.asr_loads = 0
        self.cleanup_loads = 0
        self.audio_paths: list[str] = []
        self.styles: list[str] = []

    def load_asr(self) -> None:
        self.asr_loads += 1
        self.asr_loaded = True

    def load_cleanup(self) -> None:
        self.cleanup_loads += 1
        self.cleanup_loaded = True

    def transcribe(self, audio_path: str) -> str:
        self.audio_paths.append(audio_path)
        if self.fail_asr:
            raise RuntimeError(f"private {audio_path} {self.transcript}")
        return self.transcript

    def cleanup(self, text: str, style: str) -> str:
        self.styles.append(style)
        if self.fail_cleanup:
            raise RuntimeError(f"private {text}")
        return self.cleaned
