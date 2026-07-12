# Native v0.1 QA

Record exact results, machine conditions, and timings. Never paste transcript
content or audio paths into the QA record.

## Automated gates

- [ ] frozen schema and valid/invalid NDJSON fixtures pass
- [ ] worker protocol, correction, style, fallback, and error tests pass
- [ ] Swift state, protocol, hotkey-validation, worker, and deletion tests pass
- [ ] duration bounds, stale-WAV cleanup, worker health, and HUD metrics tests pass
- [ ] fake worker end-to-end path passes
- [ ] tiny-model smoke completes with no content logs
- [ ] real large-v3-turbo plus Qwen request completes
- [ ] existing model-bake-off result contract still validates
- [ ] Release configuration builds from a clean derived-data directory
- [ ] copied Release app is ad-hoc signed and passes deep/strict verification

## Manual app acceptance

- [x] launch `dist/Billie Flow.app` outside Xcode
- [ ] app appears only in the menu bar (`LSUIElement`); no Dock icon
- [ ] first run requires a custom hotkey with Command or Control
- [ ] a modifier-free or Shift/Option-only hotkey is rejected
- [ ] microphone denial produces a clear error without changing clipboard
- [ ] holding the hotkey records; releasing it stops and processes
- [ ] a recording shorter than 0.5 seconds is discarded without clipboard change
- [ ] a held recording automatically stops and submits at five minutes
- [ ] HUD is nonactivating, floats above normal windows, and uses native glass
- [ ] HUD shows live input level and elapsed time while recording
- [ ] HUD appears bottom-center on the screen containing the pointer at start
- [ ] each of the three styles reaches the worker and produces clipboard output
- [ ] cleanup fallback copies raw ASR and shows a warning
- [ ] ASR failure and empty input leave existing clipboard contents untouched
- [ ] cancellation stops recording/inference and dismisses the HUD
- [ ] launch-at-login is off initially and can be enabled then disabled
- [ ] Settings shows installed/missing worker and ready/warming state
- [ ] missing setup shows the exact `scripts/bootstrap_worker.sh` command
- [ ] normal use does not request Accessibility or Input Monitoring

## Privacy and lifecycle

- [ ] no `Billie Flow-*.wav` remains after success
- [ ] no temporary audio remains after worker error
- [ ] no temporary audio remains after cancellation or app quit
- [ ] no worker remains after app quit or cancellation
- [ ] stdout contains only valid protocol NDJSON
- [ ] stderr, Console, and application logs contain no transcript or audio content
- [ ] the app has no transcript-history UI or persisted transcript store

## Performance

- [ ] prefetch and warmup have completed before measurement
- [ ] record a 30-second utterance, release, and measure to clipboard update
- [ ] warm end-to-end processing is under 10 seconds
- [ ] record model IDs, stage timings, build SHA, and pass/fail without content

## Verified on 2026-07-12

Automated and packaging gates:

- [x] frozen contract validator: 15 valid and 4 invalid fixtures passed
- [x] Python 3.12 model-free worker suite: 40 tests passed
- [x] SwiftPM full app build and suite: 15 tests passed
- [x] native Xcode `BillieFlow` test action: 15 tests passed on My Mac
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

The live microphone, physical hotkey, multi-display HUD, clipboard, login-item,
and quit/cancel observations remain manual checks until explicitly marked above.
