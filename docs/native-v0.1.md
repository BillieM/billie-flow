# Billie Flow Native v0.1

Billie Flow is a private, local-only macOS 26 menu-bar dictation utility. Hold
the configured global hotkey, speak, release, and the cleaned result is copied
to the clipboard. Audio and model inference stay on the Mac.

## Product boundary

v0.1 includes a native Swift 6 menu-bar app, a nonactivating glass HUD,
microphone recording, three cleanup styles, one custom hold-to-record hotkey,
optional launch at login, and one persistent local Python worker. It does not
include auto-paste, Accessibility or Input Monitoring permissions, transcript
history, model or vocabulary pickers, an updater, notarization, or App Store
distribution.

The app does not retain transcript history or content logs. It creates one
temporary 16 kHz mono PCM WAV for an active request and owns deletion on every
exit path. The worker does not delete audio. Cancelling terminates the worker so
no inference can continue against a file the app is about to remove.

## Runtime lifecycle

1. Run `scripts/bootstrap_worker.sh` once in Terminal. It creates a Python 3.12
   environment under `~/Library/Application Support/Billie Flow/runtime`,
   installs exact pins, and prefetches the two fixed models. It deliberately
   leaves `HF_HOME` unset so an existing Hugging Face cache is reused.
2. Launch the Release app. The first run asks for microphone access and requires
   a custom hotkey containing Command or Control.
3. The first recording starts the persistent worker, completes `hello`, and
   warms both models. The worker remains resident until app quit or cancellation.
4. Press and hold the hotkey to record. Release it to transcribe, clean, correct,
   and copy. ASR or empty-input failure leaves the clipboard untouched. Cleanup
   failure copies raw ASR and displays a warning.

Recordings shorter than 0.5 seconds are discarded. A held recording stops and
submits automatically at five minutes. The HUD shows live input level and
elapsed time on the screen containing the pointer when recording begins.
Settings reports whether the installed worker executable is present and whether
the current process has completed hello/warmup, with the exact bootstrap command
when setup is missing. On launch, the app removes stale WAVs left by a previous
crash before allowing a new recording.

## Architecture

```text
RegisterEventHotKey ─┐
menu-bar controls ───┼─> app state ─> AVAudioEngine ─> temporary PCM WAV
                     │                    │
glass NSPanel HUD <──┘                    └─> persistent NDJSON worker
                                                  │
                                 Whisper ASR -> Qwen cleanup -> corrections
                                                  │
                                  result -> clipboard -> delete temporary WAV
```

The shared boundary is `contracts/billie-flow.worker.v1.md`. Protocol stdout is
machine-only NDJSON. stderr diagnostics and app logs must never include audio
paths, transcripts, prompts, or cleanup content.

## Development

Quick verification:

```sh
make test
```

Repository-level verification including the existing public experiment data:

```sh
scripts/verify_native_v1.sh
```

With full Xcode installed, build and verify a local ad-hoc-signed Release app:

```sh
scripts/package_release.sh
```

The output is `dist/Billie Flow.app`. v0.1 is private and intentionally has no
push, public repository, notarization, updater, or distribution workflow here.
