"""Serial NDJSON worker service."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Iterable
from typing import Any, TextIO

from . import (
    ASR_MODEL,
    CLEANUP_MODEL,
    CORRECTIONS_VERSION,
    LANGUAGE,
    WORKER_VERSION,
)
from .corrections import apply_corrections
from .audio import validate_pcm_wav
from .protocol import Command, RequestError, error_event, event, parse_command
from .runtime import ModelRuntime

Clock = Callable[[], float]


class WorkerService:
    def __init__(self, runtime: ModelRuntime, clock: Clock = time.perf_counter) -> None:
        self.runtime = runtime
        self.clock = clock
        self.greeted = False
        self.stopped = False

    def handle_line(self, line: str) -> Iterable[dict[str, Any]]:
        try:
            command = parse_command(line)
        except RequestError as exc:
            yield error_event(exc.request_id, exc.code, exc.message, exc.recoverable)
            return

        if not self.greeted and command.name != "hello":
            yield error_event(
                command.request_id,
                "not_ready",
                "Send hello before other commands.",
            )
            return
        if command.name == "hello":
            yield self._hello(command)
        elif command.name == "warmup":
            yield from self._warmup(command)
        elif command.name == "process":
            yield from self._process(command)
        elif command.name == "shutdown":
            self.stopped = True
            yield event(command.request_id, "result", {"kind": "shutdown"})

    def _hello(self, command: Command) -> dict[str, Any]:
        if self.greeted:
            return error_event(
                command.request_id,
                "invalid_request",
                "The worker request was invalid.",
            )
        self.greeted = True
        return event(
            command.request_id,
            "ready",
            {
                "worker_version": WORKER_VERSION,
                "asr_model": ASR_MODEL,
                "cleanup_model": CLEANUP_MODEL,
                "language": LANGUAGE,
                "corrections_version": CORRECTIONS_VERSION,
            },
        )

    def _warmup(self, command: Command) -> Iterable[dict[str, Any]]:
        try:
            if not self.runtime.asr_loaded:
                yield self._phase(command, "loading_asr")
                self.runtime.load_asr()
            if not self.runtime.cleanup_loaded:
                yield self._phase(command, "loading_cleanup")
                self.runtime.load_cleanup()
        except Exception as exc:
            self._diagnose(command, "internal_error", exc)
            yield error_event(
                command.request_id,
                "internal_error",
                "The worker encountered an internal error.",
            )
            return
        yield event(command.request_id, "result", {"kind": "warmup", "warmed": True})

    def _process(self, command: Command) -> Iterable[dict[str, Any]]:
        audio_path = command.payload["audio_path"]
        if not validate_pcm_wav(audio_path):
            yield error_event(
                command.request_id,
                "audio_invalid",
                "The recording is not a valid 16 kHz mono PCM WAV file.",
            )
            return

        started = self.clock()
        timings = {
            "loading_asr_seconds": 0.0,
            "asr_seconds": 0.0,
            "loading_cleanup_seconds": 0.0,
            "cleanup_seconds": 0.0,
            "correction_seconds": 0.0,
            "total_seconds": 0.0,
        }

        try:
            if not self.runtime.asr_loaded:
                yield self._phase(command, "loading_asr")
                stage = self.clock()
                self.runtime.load_asr()
                timings["loading_asr_seconds"] = self.clock() - stage
            yield self._phase(command, "transcribing")
            stage = self.clock()
            raw_asr = self.runtime.transcribe(audio_path).strip()
            timings["asr_seconds"] = self.clock() - stage
        except Exception as exc:
            self._diagnose(command, "asr_failed", exc)
            yield error_event(
                command.request_id,
                "asr_failed",
                "Speech recognition failed.",
            )
            return

        if not raw_asr:
            yield error_event(
                command.request_id,
                "empty_transcript",
                "No speech was detected.",
            )
            return

        try:
            if not self.runtime.cleanup_loaded:
                yield self._phase(command, "loading_cleanup")
                stage = self.clock()
                self.runtime.load_cleanup()
                timings["loading_cleanup_seconds"] = self.clock() - stage
            yield self._phase(command, "cleaning")
            stage = self.clock()
            raw_cleanup = self.runtime.cleanup(raw_asr, command.payload["style"]).strip()
            timings["cleanup_seconds"] = self.clock() - stage
            if not raw_cleanup:
                raise RuntimeError("cleanup returned empty output")
        except Exception as exc:
            self._diagnose(command, "cleanup_failed_raw_asr", exc)
            timings["total_seconds"] = self.clock() - started
            yield self._process_result(
                command,
                raw_asr=raw_asr,
                raw_cleanup=None,
                final_text=raw_asr,
                corrections=[],
                timings=timings,
                warning="cleanup_failed_raw_asr",
            )
            return

        yield self._phase(command, "correcting")
        stage = self.clock()
        final_text, corrections = apply_corrections(raw_cleanup)
        timings["correction_seconds"] = self.clock() - stage
        timings["total_seconds"] = self.clock() - started
        yield self._process_result(
            command,
            raw_asr=raw_asr,
            raw_cleanup=raw_cleanup,
            final_text=final_text,
            corrections=corrections,
            timings=timings,
            warning=None,
        )

    @staticmethod
    def _phase(command: Command, phase: str) -> dict[str, Any]:
        return event(command.request_id, "phase", {"phase": phase})

    @staticmethod
    def _process_result(
        command: Command,
        *,
        raw_asr: str,
        raw_cleanup: str | None,
        final_text: str,
        corrections: list[dict[str, object]],
        timings: dict[str, float],
        warning: str | None,
    ) -> dict[str, Any]:
        return event(
            command.request_id,
            "result",
            {
                "kind": "process",
                "raw_asr": raw_asr,
                "raw_cleanup": raw_cleanup,
                "final_text": final_text,
                "corrections": corrections,
                "timings": timings,
                "asr_model": ASR_MODEL,
                "cleanup_model": CLEANUP_MODEL,
                "style": command.payload["style"],
                "warning": warning,
            },
        )

    @staticmethod
    def _diagnose(command: Command, code: str, exc: Exception) -> None:
        if command.payload.get("debug") is True:
            # The exception string can contain transcript content or a path. Only its
            # class is safe to disclose.
            print(
                f"worker_error code={code} cause={type(exc).__name__}",
                file=sys.stderr,
                flush=True,
            )


def run(stdin: TextIO, stdout: TextIO, runtime: ModelRuntime) -> int:
    service = WorkerService(runtime)
    for raw_line in stdin:
        line = raw_line.rstrip("\r\n")
        if not line:
            responses = [
                error_event(
                    "unknown",
                    "invalid_request",
                    "The worker request was invalid.",
                )
            ]
        else:
            responses = service.handle_line(line)
        for response in responses:
            stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
            stdout.write("\n")
            stdout.flush()
        if service.stopped:
            return 0
    return 0
