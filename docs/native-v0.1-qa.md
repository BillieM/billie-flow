# Native v0.1 QA

Record exact results, machine conditions, and timings. Never paste transcript
content or audio paths into the QA record.

## Automated gates

- [x] frozen schema and valid/invalid NDJSON fixtures pass
- [x] worker protocol, correction, style, fallback, and error tests pass
- [x] Swift state, protocol, hotkey-validation, worker, and deletion tests pass
- [x] duration bounds, stale-WAV cleanup, worker health, and HUD metrics tests pass
- [x] fake worker end-to-end path passes
- [x] tiny-model smoke completes with no content logs
- [x] real large-v3-turbo plus Qwen request completes
- [x] existing model-bake-off result contract still validates
- [x] Release configuration builds from a clean derived-data directory
- [x] copied Release app is ad-hoc signed and passes deep/strict verification

## Acceptance evidence

Runtime-observed on the installed app:

- [x] first-run custom Command/Control hotkey setup
- [x] physical hold-to-record and release-to-process flow
- [x] non-empty clipboard result
- [x] app and persistent worker remain healthy after success
- [x] successful recording leaves no temporary WAV or new crash report

Automated release gate (`scripts/run_system_acceptance.sh`):

- [x] modifier validation and transactional hotkey conflict/rebinding
- [x] exact production audio conversion and finalized 16 kHz mono Int16 WAV
- [x] 0.5-second discard and five-minute auto-stop policy/wiring
- [x] clipboard success, cleanup fallback, empty-ASR, and failure preservation
- [x] cancellation-safe audio deletion, worker kill, restart, and no orphan
- [x] cleanup fallback plus ASR/empty/malformed/crash fault matrix
- [x] LSUIElement, microphone purpose, and no Accessibility/Input Monitoring API
- [x] HUD nonactivation/Spaces/glass/pointer-screen contract and tests
- [x] launch-at-login wiring, settings health, settings-only persistence, no history
- [x] stdout NDJSON, stderr privacy, and absence of application transcript logging
- [x] isolated packaged-app launch and termination without process/audio/crash residue
- [x] 30-second production-model processing under ten seconds

HUD appearance across displays/Spaces, macOS TCC dialog presentation,
`SMAppService` registration, physical five-minute timing, and physical clipboard
side effects for every injected failure are structurally asserted or tested below
the OS boundary rather than driven through UI automation. They are documented
limitations, not tasks delegated to the user.

## Verified on 2026-07-12

Automated and packaging gates:

- [x] frozen contract validator: 15 valid and 4 invalid fixtures passed
- [x] Python 3.12 model-free worker suite: 44 tests passed
- [x] SwiftPM full app build and suite: 23 tests passed
- [x] native Xcode `BillieFlow` test action: 23 tests passed on My Mac
- [x] automated system acceptance: 9 passed, 0 failed, 0 skipped
- [x] production audio writer integration: 48 kHz stereo Float32 to finalized
      16 kHz mono interleaved Int16 WAV
- [x] cancellation kills the worker, deletes request audio, restarts with a new
      PID, and shuts down without an orphan
- [x] persistent fake-worker hello/warmup/process/shutdown test passed
- [x] tiny Whisper plus Qwen smoke passed with non-empty ASR and cleanup
- [x] existing model-bake-off `results.json` still validates
- [x] idempotent supported bootstrap passed twice with exact runtime pins
- [x] Xcode 26.6 Release app built as universal arm64/x86_64
- [x] Release Info.plist lint, ad-hoc signing, and deep/strict verification passed
- [x] Release metadata reports macOS 26.0 minimum and `LSUIElement=true`
- [x] signed `dist/Billie Flow.app` launched outside Xcode, stayed running from
      its bundle executable, terminated cleanly, and left no app process

Production-model acceptance used the existing 35.3-second voice memo without
printing its path or content. Fixed model IDs and all expected phases matched
the v1 contract. Warmup took 5.585 seconds. Warm processing took 1.923 seconds:
ASR 1.239 seconds and cleanup 0.683 seconds. The result had no warning, applied
three deterministic corrections, disclosed no private audio/transcript content
on stderr, and the worker exited cleanly with status 0. This passes the warm
30-second-under-10-seconds requirement.

The final zero-skip automated gate processed a generated 30-second production
fixture in 1.874 seconds after warmup. It also ran the complete controlled
failure matrix and opened the packaged app through LaunchServices for three
seconds before terminating it, with no child process, temporary audio, private
log content, or new system crash report. An earlier harness revision directly
executed the GUI binary from a temporary path and triggered an AppKit
registration abort; this was a harness artifact, not the installed app, and the
release gate now explicitly monitors the real DiagnosticReports directory.

The final read-only release audit found and then verified fixes for two blockers:
cleanup generation now detects token-limit termination and falls back to the
complete raw ASR instead of copying truncated text, and hotkey rebinding now
preserves the existing registration when a replacement conflicts. Persistent
warning/error HUD state and the `Copied · [style]` success treatment were also
aligned with the product contract before integration.

The primary microphone, hotkey, clipboard, success-cleanup, and crash-free flow
was physically observed once. Remaining OS presentation details are covered by
automated structural assertions and are not assigned to the user for testing.

## Final installation state

- Repository moved with history and ignored lab assets to
  `/Users/billie/Developer/billie-flow`.
- Clean-cache `scripts/verify_native_v1.sh --full` passed at the permanent path.
- The final production-model acceptance passed there in 2.059 seconds warm
  processing, with all expected phases, no warning, and no private stderr content.
- The ad-hoc-signed universal Release app is installed at
  `/Applications/Billie Flow.app`; its executable hash matches the permanent-path
  `dist/Billie Flow.app`, strict signature verification passes, and it launches
  without spawning the worker before a recording.
- Final read-only QA found no code blockers. The zero-skip automated report has
  passed and the installed executable matches the current release artifact.

## Microphone crash fix

The first physical recording attempt produced a Swift executor precondition
crash when Core Audio delivered its first buffer. The `AVAudioEngine` tap block
had inherited `AudioRecorder`'s main-actor isolation even though AVFAudio invokes
it on a realtime queue. The tap is now constructed in an explicitly
`nonisolated` function; only metering is handed back to the main actor. The full
contract, worker, SwiftPM, Xcode, Release build, Info.plist, and strict signing
verification suite passed after the fix; a later physical recording completed.

The second physical attempt passed the executor boundary, then Core Audio
aborted while writing the converted buffer: `AVAudioFile` had selected its
default processing format rather than the recorder's Int16 interleaved format.
The file is now opened with an explicit processing format matching the
converter output. A direct integration smoke converted 48 kHz stereo float
buffers through the recorder path, finalized the output, and read it back as a
valid 16 kHz mono Int16 WAV before the full release suite passed again.

## Successful physical flow

After both microphone-path fixes were installed, a real hold-to-record and
release-to-process attempt completed without a new crash. The app remained
running, the persistent worker remained alive as designed, the clipboard held
a non-empty result, and no temporary recording remained. This verifies the
primary installed-app flow without storing or recording the dictated content.
