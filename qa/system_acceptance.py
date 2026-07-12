#!/usr/bin/env python3
"""Deterministic v0.1 release acceptance without touching the installed app.

The harness intentionally treats worker stdout as a private protocol transport. It
never includes subprocess output, audio paths, or transcript text in its report.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import select
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP = ROOT / "dist/Billie Flow.app"
INSTALLED_APP = Path("/Applications/Billie Flow.app")
DEFAULT_WORKER = Path.home() / "Library/Application Support/Billie Flow/runtime/.venv/bin/billie-flow-worker"
FORBIDDEN_PERMISSION_APIS = {
    "AXIsProcessTrusted",
    "AXIsProcessTrustedWithOptions",
    "CGEventTapCreate",
    "CGEventTapCreateForPSN",
    "IOHIDCheckAccess",
    "IOHIDRequestAccess",
    "kTCCServiceAccessibility",
    "kTCCServiceListenEvent",
}
PRIVATE_FAKE_TEXT = "Billy Flow uses Swift UI and M L X."


class CheckFailure(RuntimeError):
    pass


@dataclass
class Check:
    check_id: str
    status: str
    seconds: float
    detail: str
    release_blocker: bool


class Acceptance:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def run(
        self,
        check_id: str,
        function: Callable[[], str],
        *,
        release_blocker: bool = True,
    ) -> None:
        started = time.perf_counter()
        try:
            detail = function()
            status = "pass"
        except CheckFailure as exc:
            detail = str(exc)
            status = "fail"
        except Exception as exc:  # Keep reports private and deterministic.
            detail = f"unexpected {type(exc).__name__}"
            status = "fail"
        self.checks.append(
            Check(
                check_id=check_id,
                status=status,
                seconds=round(time.perf_counter() - started, 3),
                detail=detail,
                release_blocker=release_blocker,
            )
        )

    def skip(self, check_id: str, detail: str) -> None:
        self.checks.append(Check(check_id, "skip", 0.0, detail, False))

    @property
    def blockers(self) -> list[Check]:
        return [item for item in self.checks if item.status == "fail" and item.release_blocker]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def run_command(
    arguments: list[str],
    *,
    timeout: float,
    cwd: Path = ROOT,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            cwd=cwd,
            env=environment,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise CheckFailure("timed out") from exc


def full_verifier() -> str:
    completed = run_command([str(ROOT / "scripts/verify_native_v1.sh"), "--full"], timeout=1800)
    require(completed.returncode == 0, "repository verifier failed; inspect it directly for diagnostics")
    require(DEFAULT_APP.is_dir(), "repository verifier did not produce the Release app")
    return "contracts, worker, Swift, Xcode, result validation, and Release packaging passed"


def app_metadata() -> str:
    info_path = DEFAULT_APP / "Contents/Info.plist"
    require(info_path.is_file(), "packaged Info.plist is missing")
    with info_path.open("rb") as handle:
        info = plistlib.load(handle)
    require(info.get("LSUIElement") is True, "LSUIElement must be true")
    microphone = info.get("NSMicrophoneUsageDescription")
    require(isinstance(microphone, str) and microphone.strip(), "microphone usage text is missing")
    require("NSAccessibilityUsageDescription" not in info, "Accessibility usage text is present")
    require("NSInputMonitoringUsageDescription" not in info, "Input Monitoring usage text is present")
    return "LSUIElement is enabled; microphone purpose is declared; no Accessibility/Input Monitoring purpose is declared"


def extract_entitlements(output: str) -> dict[str, Any]:
    start = output.find("<?xml")
    if start < 0:
        start = output.find("<plist")
    if start < 0:
        # An ad-hoc signed, unsandboxed app with an empty entitlement file has no
        # embedded entitlement blob. A successful codesign query is the empty dict.
        return {}
    try:
        return plistlib.loads(output[start:].encode("utf-8"))
    except Exception as exc:
        raise CheckFailure("codesign returned malformed entitlements") from exc


def signing_and_architectures() -> str:
    executable = DEFAULT_APP / "Contents/MacOS/Billie Flow"
    require(executable.is_file(), "packaged executable is missing")
    verified = run_command(["codesign", "--verify", "--deep", "--strict", str(DEFAULT_APP)], timeout=30)
    require(verified.returncode == 0, "strict code-signature verification failed")
    signature = run_command(["codesign", "-dv", "--verbose=4", str(DEFAULT_APP)], timeout=30)
    signature_text = signature.stdout + signature.stderr
    require(signature.returncode == 0, "signature metadata could not be read")
    require("Signature=adhoc" in signature_text, "Release app is not ad-hoc signed")
    archs = run_command(["lipo", "-archs", str(executable)], timeout=30)
    require(archs.returncode == 0, "binary architectures could not be read")
    actual = set(archs.stdout.split())
    require({"arm64", "x86_64"}.issubset(actual), "Release binary is not universal arm64/x86_64")
    return "strict ad-hoc signature and universal arm64/x86_64 executable verified"


def permission_surface() -> str:
    entitlements_result = run_command(
        ["codesign", "-d", "--entitlements", ":-", str(DEFAULT_APP)], timeout=30
    )
    require(entitlements_result.returncode == 0, "entitlements could not be read")
    entitlements = extract_entitlements(entitlements_result.stdout + entitlements_result.stderr)
    forbidden_entitlements = {
        key
        for key in entitlements
        if "accessibility" in key.lower()
        or "listen-event" in key.lower()
        or "input-monitor" in key.lower()
    }
    require(not forbidden_entitlements, "Accessibility/Input Monitoring entitlement is present")

    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "app/Sources").rglob("*.swift")
    )
    source_hits = sorted(token for token in FORBIDDEN_PERMISSION_APIS if token in source_text)
    require(not source_hits, "permission-gated API appears in application source")

    executable = DEFAULT_APP / "Contents/MacOS/Billie Flow"
    symbols = run_command(["nm", "-u", str(executable)], timeout=30)
    require(symbols.returncode == 0, "undefined symbols could not be inspected")
    binary_hits = sorted(token for token in FORBIDDEN_PERMISSION_APIS if token in symbols.stdout)
    require(not binary_hits, "permission-gated API is linked by the Release binary")
    return "no Accessibility/Input Monitoring entitlement, source use, or linked API symbol found"


def ui_and_settings_contract() -> str:
    hud = (ROOT / "app/Sources/BillieFlowApp/HUDPanel.swift").read_text()
    app_model = (ROOT / "app/Sources/BillieFlowApp/AppModel.swift").read_text()
    settings = (ROOT / "app/Sources/BillieFlowApp/SettingsView.swift").read_text()
    policy = (ROOT / "app/Sources/BillieFlowCore/RecordingPolicy.swift").read_text()
    lifecycle_tests = (ROOT / "app/Tests/BillieFlowCoreTests/FlowStateTests.swift").read_text()

    hud_tokens = {
        ".nonactivatingPanel",
        "panel.ignoresMouseEvents = true",
        ".canJoinAllSpaces",
        ".fullScreenAuxiliary",
        "NSGlassEffectView",
        "beginRecordingOnPointerScreen",
        "NSEvent.mouseLocation",
        "ScreenSelection.index",
    }
    require(all(token in hud for token in hud_tokens), "HUD focus/Space/glass/pointer-screen contract changed")
    require("healthStatesAndPointerScreenSelectionAreDeterministic" in lifecycle_tests, "pointer-screen unit evidence is missing")

    require('Toggle("Launch Billie Flow at login"' in settings, "launch-at-login toggle is missing")
    require("launchAtLogin = SMAppService.mainApp.status == .enabled" in app_model, "launch-at-login does not default from the disabled system service")
    require("try SMAppService.mainApp.register()" in app_model, "launch-at-login enable wiring is missing")
    require("try SMAppService.mainApp.unregister()" in app_model, "launch-at-login disable wiring is missing")
    require(app_model.count("SMAppService.mainApp.register()") == 1, "launch-at-login is registered outside the explicit toggle path")

    require("Billie Flow keeps no transcript history." in settings, "no-history disclosure is missing")
    require("CoreData" not in app_model and "SwiftData" not in app_model and "ModelContainer" not in app_model, "transcript persistence framework appears in AppModel")
    require(app_model.count("defaults.set(") == 2, "settings persistence expanded beyond style and shortcut")
    require("defaults.set(style.rawValue, forKey: Keys.style)" in app_model, "style persistence changed")
    require("defaults.set(data, forKey: Keys.hotKey)" in app_model, "shortcut persistence changed")

    require("minimumDuration: TimeInterval = 0.5" in policy, "minimum recording duration changed")
    require("maximumDuration: TimeInterval = 5 * 60" in policy, "maximum recording duration changed")
    require("RecordingPolicy.maximumDuration" in app_model and "finishRecording()" in app_model, "five-minute auto-stop is not wired")
    require("RecordingPolicy.disposition(for: 0.499) == .discardTooShort" in lifecycle_tests, "short-recording boundary test is missing")
    require("RecordingPolicy.disposition(for: 0.5) == .submit" in lifecycle_tests, "minimum submit boundary test is missing")
    require("RecordingPolicy.maximumDuration == 300" in lifecycle_tests, "five-minute policy test is missing")
    return "HUD focus/Space/glass/pointer-screen, explicit login toggle, settings-only persistence, and 0.5s/5m recording policy are source-and-test verified"


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def process_group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def isolated_app_launch(seconds: float) -> str:
    require(DEFAULT_APP.resolve() != INSTALLED_APP.resolve(), "refusing to exercise the installed app")
    executable = DEFAULT_APP / "Contents/MacOS/Billie Flow"
    require(executable.is_file(), "packaged executable is missing")
    with tempfile.TemporaryDirectory(prefix="billie-flow-app-acceptance-") as temporary:
        isolated = Path(temporary)
        home = isolated / "home"
        tmp = isolated / "tmp"
        home.mkdir()
        tmp.mkdir()
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": str(home),
                "CFFIXED_USER_HOME": str(home),
                "TMPDIR": f"{tmp}/",
                "BILLIE_FLOW_WORKER_EXECUTABLE": str(isolated / "worker-not-used"),
            }
        )
        child = subprocess.Popen(
            [str(executable), "-ApplePersistenceIgnoreState", "YES"],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise CheckFailure("isolated Release app terminated during launch smoke")
                time.sleep(0.1)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            stdout, stderr = child.communicate(timeout=2)

        require(not process_group_alive(child.pid), "isolated app left a child process behind")
        require(not list(isolated.rglob("*.wav")), "isolated app left temporary audio behind")
        require(not list(isolated.rglob("*.ips")), "isolated app produced a crash report")
        require(PRIVATE_FAKE_TEXT not in stdout + stderr, "private protocol text appeared in app logs")

    return f"isolated packaged app remained live for {seconds:.1f}s and exited without child/audio/crash residue; installed app was not addressed"


def write_test_wav(path: Path, seconds: float = 0.75) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\0\0" * int(16_000 * seconds))


def request(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "id": f"qa-{name}-{uuid.uuid4()}",
        "command": name,
        "payload": payload,
    }


class WorkerSession:
    def __init__(self, mode: str = "success") -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "worker/src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["BILLIE_FLOW_FAKE_MODE"] = mode
        self.child = subprocess.Popen(
            [sys.executable, "-m", "billie_flow_worker.fake"],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
            start_new_session=True,
        )
        self.output_buffer = bytearray()

    def send(self, value: dict[str, Any] | str) -> str:
        require(self.child.stdin is not None, "worker stdin unavailable")
        line = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
        self.child.stdin.write((line + "\n").encode("utf-8"))
        self.child.stdin.flush()
        return value["id"] if isinstance(value, dict) else "unknown"

    def read(self, timeout: float = 5) -> dict[str, Any]:
        require(self.child.stdout is not None, "worker stdout unavailable")
        deadline = time.monotonic() + timeout
        while b"\n" not in self.output_buffer:
            remaining = deadline - time.monotonic()
            require(remaining > 0, "worker response timed out")
            ready, _, _ = select.select([self.child.stdout], [], [], remaining)
            require(bool(ready), "worker response timed out")
            chunk = os.read(self.child.stdout.fileno(), 65_536)
            require(bool(chunk), "worker exited before responding")
            self.output_buffer.extend(chunk)
        line, _, remainder = self.output_buffer.partition(b"\n")
        self.output_buffer = bytearray(remainder)
        try:
            value = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise CheckFailure("worker emitted malformed JSON") from exc
        require(isinstance(value, dict), "worker emitted a non-object record")
        return value

    def exchange(self, value: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        request_id = self.send(value)
        phases: list[str] = []
        while True:
            message = self.read()
            require(message.get("request_id") == request_id, "worker request id mismatch")
            event = message.get("event")
            if event == "phase":
                phases.append(message.get("payload", {}).get("phase"))
                continue
            require(event in {"ready", "result", "error"}, "worker emitted an unknown event")
            return phases, message

    def hello(self) -> dict[str, Any]:
        _, message = self.exchange(
            request("hello", {"client_name": "Billie Flow QA", "client_version": "0.1.0"})
        )
        require(message.get("event") == "ready", "fake worker hello failed")
        return message

    def shutdown(self) -> str:
        _, message = self.exchange(request("shutdown", {}))
        require(message.get("payload") == {"kind": "shutdown"}, "worker rejected shutdown")
        self.child.wait(timeout=5)
        require(self.child.returncode == 0, "worker shutdown was not clean")
        return self.stderr()

    def stderr(self) -> str:
        require(self.child.stderr is not None, "worker stderr unavailable")
        return self.child.stderr.read().decode("utf-8", errors="replace")

    def terminate(self, sig: int = signal.SIGTERM) -> None:
        if self.child.poll() is None:
            os.killpg(self.child.pid, sig)
            self.child.wait(timeout=5)

    def close(self) -> None:
        if self.child.poll() is None:
            self.terminate()


def worker_fault_matrix() -> str:
    sessions: list[WorkerSession] = []
    worker_pids: set[int] = set()
    private_path = ""
    try:
        with tempfile.TemporaryDirectory(prefix="billie-flow-worker-acceptance-") as temporary:
            audio = Path(temporary) / "qa-private-audio.wav"
            private_path = str(audio)
            write_test_wav(audio)
            payload = {"audio_path": str(audio), "style": "light-cleanup", "debug": True}

            success = WorkerSession()
            sessions.append(success)
            worker_pids.add(success.child.pid)
            success.hello()
            phases, warmed = success.exchange(request("warmup", {}))
            require(phases == ["loading_asr", "loading_cleanup"], "warmup phase sequence changed")
            require(warmed.get("payload", {}).get("kind") == "warmup", "warmup result changed")
            phases, processed = success.exchange(request("process", payload))
            require(phases == ["transcribing", "cleaning", "correcting"], "warm process phase sequence changed")
            require(processed.get("payload", {}).get("kind") == "process", "success process result changed")
            require(success.shutdown() == "", "successful worker wrote to stderr")

            fallback = WorkerSession("cleanup_failure")
            sessions.append(fallback)
            worker_pids.add(fallback.child.pid)
            fallback.hello()
            _, message = fallback.exchange(request("process", payload))
            result = message.get("payload", {})
            require(message.get("event") == "result", "cleanup failure did not fall back")
            require(result.get("warning") == "cleanup_failed_raw_asr", "cleanup fallback warning changed")
            require(result.get("raw_cleanup") is None, "cleanup fallback returned cleanup text")
            require(result.get("final_text") == result.get("raw_asr"), "cleanup fallback altered raw ASR")
            fallback_log = fallback.shutdown()
            require(private_path not in fallback_log and PRIVATE_FAKE_TEXT not in fallback_log, "fallback log disclosed private data")

            for mode, code in (("asr_failure", "asr_failed"), ("empty", "empty_transcript")):
                failure = WorkerSession(mode)
                sessions.append(failure)
                worker_pids.add(failure.child.pid)
                failure.hello()
                _, message = failure.exchange(request("process", payload))
                require(message.get("event") == "error", f"{mode} did not return an error")
                require(message.get("payload", {}).get("code") == code, f"{mode} returned the wrong code")
                failure_log = failure.shutdown()
                require(private_path not in failure_log and PRIVATE_FAKE_TEXT not in failure_log, f"{mode} log disclosed private data")

            malformed = WorkerSession()
            sessions.append(malformed)
            worker_pids.add(malformed.child.pid)
            malformed.send("{malformed-json")
            message = malformed.read()
            require(message.get("event") == "error", "malformed request was not rejected")
            require(message.get("payload", {}).get("code") == "invalid_request", "malformed request error changed")
            malformed.hello()
            require(malformed.shutdown() == "", "malformed-input worker wrote to stderr")

            crashed = WorkerSession()
            sessions.append(crashed)
            worker_pids.add(crashed.child.pid)
            crashed.hello()
            crashed.terminate(signal.SIGKILL)
            require(crashed.child.returncode is not None and crashed.child.returncode < 0, "crash injection did not kill worker")

            after_crash = WorkerSession()
            sessions.append(after_crash)
            worker_pids.add(after_crash.child.pid)
            after_crash.hello()
            require(after_crash.shutdown() == "", "worker did not restart cleanly after crash")

            cancelled = WorkerSession()
            sessions.append(cancelled)
            worker_pids.add(cancelled.child.pid)
            cancelled.hello()
            cancelled.send(request("warmup", {}))
            cancelled.terminate(signal.SIGTERM)
            require(cancelled.child.returncode is not None, "cancel injection left worker running")

            after_cancel = WorkerSession()
            sessions.append(after_cancel)
            worker_pids.add(after_cancel.child.pid)
            after_cancel.hello()
            require(after_cancel.shutdown() == "", "worker did not restart cleanly after cancellation")
    finally:
        for session in sessions:
            session.close()

    require(not any(pid_alive(pid) for pid in worker_pids), "fault matrix left a worker process behind")
    return "hello/warmup/process, cleanup fallback, ASR/empty/malformed errors, crash, cancel, restart, and shutdown passed"


def privacy_and_safety_contract() -> str:
    app_sources = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "app/Sources").rglob("*.swift")
    )
    require("NSPasteboard.general.clearContents()" in app_sources, "clipboard write path changed")
    require("ClipboardPolicy.decision" in app_sources, "clipboard policy is not applied")
    require("Logger(" not in app_sources and "os_log" not in app_sources and "NSLog(" not in app_sources, "application source contains a logging API")

    protocol_tests = (ROOT / "app/Tests/BillieFlowCoreTests/WorkerProtocolTests.swift").read_text()
    lifecycle_tests = (ROOT / "app/Tests/BillieFlowCoreTests/FlowStateTests.swift").read_text()
    require("ClipboardPolicy.decision(for: result) == .preserve" in protocol_tests, "clipboard preservation test is missing")
    require("temporaryAudioDeletesIdempotently" in lifecycle_tests, "temporary-audio deletion test is missing")
    require("staleCleanupOnlyRemovesWAVs" in lifecycle_tests, "next-launch WAV cleanup test is missing")
    return "full verifier covers clipboard preservation and temp-WAV deletion; app has no transcript logging API"


def discover_production_audio(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit.expanduser().resolve()
    local = ROOT / "experiments/voice-memo/input-16khz.wav"
    if local.is_file():
        return local
    worktrees = run_command(["git", "worktree", "list", "--porcelain"], timeout=30)
    if worktrees.returncode != 0:
        return None
    for line in worktrees.stdout.splitlines():
        if line.startswith("worktree "):
            candidate = Path(line.removeprefix("worktree ")) / "experiments/voice-memo/input-16khz.wav"
            if candidate.is_file():
                return candidate
    return None


def make_30_second_audio(source: Path, destination: Path) -> None:
    try:
        with wave.open(str(source), "rb") as input_file:
            require(input_file.getnchannels() == 1, "production memo is not mono")
            require(input_file.getsampwidth() == 2, "production memo is not 16-bit PCM")
            require(input_file.getframerate() == 16_000, "production memo is not 16 kHz")
            frames = input_file.readframes(input_file.getnframes())
    except (wave.Error, OSError) as exc:
        raise CheckFailure("production memo is not a readable WAV") from exc
    require(bool(frames), "production memo is empty")
    target_bytes = 30 * 16_000 * 2
    repeated = (frames * ((target_bytes // len(frames)) + 1))[:target_bytes]
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(repeated)


def production_performance(source: Path, worker: Path, limit: float) -> str:
    require(source.is_file(), "production memo is unavailable")
    require(worker.is_file() and os.access(worker, os.X_OK), "pinned production worker is unavailable")
    with tempfile.TemporaryDirectory(prefix="billie-flow-production-acceptance-") as temporary:
        audio = Path(temporary) / "thirty-seconds.wav"
        make_30_second_audio(source, audio)
        completed = run_command(
            [
                sys.executable,
                str(ROOT / "scripts/run_worker_acceptance.py"),
                "--audio",
                str(audio),
                "--worker",
                str(worker),
            ],
            timeout=900,
        )
        require(completed.returncode == 0, "production worker acceptance failed")
        try:
            summary = json.loads(completed.stdout.strip())
        except json.JSONDecodeError as exc:
            raise CheckFailure("production acceptance returned malformed summary") from exc
        require(summary.get("status") == "ok", "production acceptance reported an error")
        process_seconds = summary.get("process_wall_seconds")
        require(isinstance(process_seconds, (int, float)), "production timing is missing")
        require(process_seconds < limit, f"30-second warm dictation exceeded {limit:.1f}s")
        require(summary.get("stderr_private_content") is False, "production worker disclosed private content")
        require(summary.get("worker_exit_code") == 0, "production worker did not shut down")
        require(not audio.exists() or audio.stat().st_size > 0, "production fixture changed unexpectedly")
    return f"30-second production dictation processed in {process_seconds:.3f}s (limit {limit:.1f}s), with privacy and shutdown checks"


def write_report(acceptance: Acceptance, output: Path) -> dict[str, Any]:
    counts = {
        status: sum(item.status == status for item in acceptance.checks)
        for status in ("pass", "fail", "skip")
    }
    report = {
        "schema_version": "billie-flow.system-acceptance.v1",
        "status": "failed" if acceptance.blockers else "passed",
        "counts": counts,
        "checks": [asdict(item) for item in acceptance.checks],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/qa/system-acceptance.json")
    parser.add_argument("--production-audio", type=Path)
    parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--performance-limit", type=float, default=10.0)
    parser.add_argument("--launch-seconds", type=float, default=3.0)
    parser.add_argument("--skip-production", action="store_true")
    parser.add_argument("--skip-full-verifier", action="store_true")
    args = parser.parse_args()

    acceptance = Acceptance()
    if args.skip_full_verifier:
        acceptance.skip("repository.full_verifier", "disabled by command line")
    else:
        acceptance.run("repository.full_verifier", full_verifier)

    acceptance.run("app.metadata", app_metadata)
    acceptance.run("app.signature_and_architectures", signing_and_architectures)
    acceptance.run("app.permission_surface", permission_surface)
    acceptance.run("app.ui_and_settings_contract", ui_and_settings_contract)
    acceptance.run("app.isolated_launch", lambda: isolated_app_launch(args.launch_seconds))
    acceptance.run("worker.fault_matrix", worker_fault_matrix)
    acceptance.run("privacy.clipboard_audio_logs", privacy_and_safety_contract)

    if args.skip_production:
        acceptance.skip("worker.production_30_second", "disabled by command line")
    else:
        audio = discover_production_audio(args.production_audio)
        if audio is None:
            acceptance.skip("worker.production_30_second", "local production memo unavailable")
        elif not args.worker.expanduser().is_file():
            acceptance.skip("worker.production_30_second", "pinned production runtime unavailable")
        else:
            acceptance.run(
                "worker.production_30_second",
                lambda: production_performance(
                    audio, args.worker.expanduser().resolve(), args.performance_limit
                ),
            )

    output = args.output.expanduser().resolve()
    report = write_report(acceptance, output)
    print(f"Billie Flow v0.1 system acceptance: {report['status']}")
    for check in acceptance.checks:
        print(f"{check.status.upper():4} {check.check_id}: {check.detail} ({check.seconds:.3f}s)")
    print(f"Machine report: {output}")
    return 1 if acceptance.blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
