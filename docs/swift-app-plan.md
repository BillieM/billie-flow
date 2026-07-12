# Swift App Plan

The testing phase chose evidence-backed model defaults. This plan is now the
implemented native v0.1 boundary; see `native-v0.1.md` for setup and runtime
details.

## Product Shape

Working name: `Billie Flow`

First app version:

- native macOS Swift/SwiftUI app
- menu bar presence
- global record hotkey
- small liquid-glass recording HUD
- microphone capture
- local worker process for model inference
- final text copied to clipboard
- no automatic paste on day one
- no account, sync, or cloud dependency

## Deferred Capabilities

Automatic insertion into the focused app can wait. It likely requires
Accessibility permissions and increases app complexity. The first pass can copy
to clipboard and show a completion HUD.

Deferred:

- Accessibility paste
- per-app behaviours
- transcript history
- custom vocabulary editor
- model download manager
- command mode
- streaming partial transcript

## App Architecture

```text
Swift menu bar app
  -> recorder service
  -> temporary 16 kHz mono PCM WAV
  -> managed Python child over stdin/stdout NDJSON
    -> fixed ASR model
    -> fixed cleanup model
    -> deterministic corrections
  -> clipboard output
  -> HUD state updates
```

The worker should remain outside the Swift binary initially. That keeps model
runtime churn away from the app shell and makes the testing harness reusable.

## v0.1 Settings

Simple settings:

- record hotkey
- default style
- launch at login, off by default

Model selection, custom vocabulary, auto-paste, and transcript history are out
of scope rather than hidden advanced settings.

## Defaults Chosen From Testing

The testing phase recommends:

- default ASR backend: `mlx-whisper-large-v3-turbo`
- fallback ASR backend: `mlx-whisper-tiny` for smoke tests only
- default cleanup model: `mlx-local-small-text`
- default style: `light-cleanup`
- minimum hardware direction: Apple Silicon with local MLX runtimes
- lab-only branches: Gemma, Voxtral, and Parakeet

## App Acceptance Test

The first real app acceptance test should be:

1. press hotkey
2. speak for 10-30 seconds
3. release hotkey
4. local worker transcribes and cleans text
5. final text lands on clipboard
6. HUD shows completion and selected style

The app should not pretend to be Wispr Flow. It is a learning project and local
model testbed with a narrow dictation workflow.
