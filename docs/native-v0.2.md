# Billie Flow Native v0.2

Billie Flow v0.2 is an unsupported, local-only proof of concept for Apple
Silicon Macs running macOS 26 or later. Hold a configured global hotkey, speak
English, release, and the cleaned result is copied to the clipboard. Audio and
model inference stay on the Mac after the consented initial setup.

## Product boundary

v0.2 includes a native Swift 6 menu-bar app, a nonactivating glass HUD,
microphone recording, three cleanup styles, one custom hold-to-record hotkey,
optional launch at login, and one persistent local Python worker. It does not
include auto-paste, Accessibility or Input Monitoring permissions, transcript
history, model or vocabulary pickers, an updater, notarisation, the App Store,
or a support and compatibility commitment.

The app and bundled bootstrap executable are arm64. Intel Macs are not
supported. The worker fixes its recognition language to English (`en`);
multilingual input is outside this proof of concept.

## Install

1. Download `Billie-Flow-v0.2.0-apple-silicon.zip` and its `.sha256` file from
   [GitHub Releases](https://github.com/BillieM/billie-flow/releases).
2. Verify the published checksum, unzip the archive, and move
   `Billie Flow.app` to `/Applications`.
3. Open the app. The unnotarised-build warning and bounded Gatekeeper exception
   are documented below.

The release app already contains the pinned installer executable, worker
source, and exact dependency lock. Release users do not need a repository
checkout, Terminal, Homebrew, or a separately installed Python.

## First-launch setup and download consent

The app contains no Python runtime, Python packages, or model weights. It never
starts the large installation silently. When the installed worker is missing,
Settings opens automatically and shows the Apple Silicon, macOS 26, English-only,
local-inference, Hugging Face, and approximate 3.5 GB boundaries.

Choose **Install local models…** to open the **Install local speech models?**
consent alert. The download and installation start only after choosing
**Install**; choosing **Cancel** leaves the machine unchanged.

The app reports these phases:

1. Preparing Python
2. Installing local runtime
3. Downloading speech model
4. Downloading cleanup model
5. Verifying setup

Setup can be cancelled, and a failed installation can be retried. The installed
runtime occupies roughly 1.1 GB under
`~/Library/Application Support/Billie Flow/runtime`. The two fixed models add
roughly 2.5 GB to the Hugging Face cache. Exact transfer and disk use vary when
files are already cached.

The packaged bootstrap payload is under
`Billie Flow.app/Contents/Resources/Bootstrap` and contains:

- the Apple Silicon `uv` 0.11.28 executable and its Apache 2.0 and MIT licences;
- the Billie Flow worker source and package metadata;
- the fully pinned `worker/requirements.lock` dependency set;
- no model weights.

The setup uses bundled `uv` to prepare Python 3.12, install the local worker,
and fetch its dependencies. It deliberately leaves `HF_HOME` unset, so the
normal shared Hugging Face cache is reused. Network requests during setup go to
the Python and model download services used by `uv` and Hugging Face. No
recording or transcript exists during installation.

## Fixed models and runtime

Production inference uses:

- ASR: [`mlx-community/whisper-large-v3-turbo`](https://huggingface.co/mlx-community/whisper-large-v3-turbo),
  converted to MLX from
  [`openai/whisper-large-v3-turbo`](https://huggingface.co/openai/whisper-large-v3-turbo)
  under the MIT licence.
- Cleanup: [`mlx-community/Qwen2.5-1.5B-Instruct-4bit`](https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit),
  converted to MLX from
  [`Qwen/Qwen2.5-1.5B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)
  under the Apache 2.0 licence.

The runtime requires Python 3.12 and pins `mlx==0.32.0`,
`mlx-metal==0.32.0`, `mlx-whisper==0.4.3`, and `mlx-lm==0.31.3`. The complete
transitive dependency set is in `worker/requirements.lock`. Model weights are
not stored in this repository and are governed by their own model cards and
licences rather than the source-code licence in this repository.

## Opening the unnotarised build

The proof-of-concept release is ad-hoc signed, not Developer ID signed, and not
notarised by Apple. macOS cannot verify the developer or confirm that Apple has
checked the downloaded build for malicious software. Only make an exception if
you obtained the app from this repository, verified the published checksum, and
accept the risk.

After trying to open the app once:

1. Open **System Settings → Privacy & Security**.
2. Scroll to **Security** and choose **Open Anyway**.
3. Authenticate and confirm **Open**.

Apple documents this temporary exception in
[Open a Mac app from an unknown developer](https://support.apple.com/en-gb/guide/mac-help/mh40616/mac).
Do not disable Gatekeeper globally.

## Dictation lifecycle

1. Complete the consented local setup.
2. Approve microphone access and choose a custom hotkey containing Command or
   Control.
3. The first recording starts the installed worker, completes the protocol
   handshake, and warms both models. The worker remains resident until app quit
   or cancellation.
4. Press and hold the hotkey to record. Release it to transcribe, clean, correct,
   and copy. ASR or empty-input failure leaves the clipboard untouched. Cleanup
   failure copies raw ASR and displays a warning.

Recordings shorter than 0.5 seconds are discarded. A held recording stops and
submits automatically at five minutes. The HUD shows live input level and
elapsed time on the screen containing the pointer when recording begins.
Settings reports installation progress and worker health.

## Privacy and storage boundary

- Inference is local after setup. The app does not send recordings,
  transcripts, prompts, or clipboard results to a server.
- The app creates one temporary 16 kHz mono PCM WAV for an active request. It
  owns deletion after success, failure, cancellation, and quit, and removes
  stale owned WAVs on the next launch after a crash.
- Cancelling terminates the worker before audio deletion so inference cannot
  race the app's cleanup.
- Transcript text exists in process memory and the system clipboard. The app
  stores no transcript history or content logs, but other applications with
  clipboard access may read the clipboard.
- The installed worker lives under
  `~/Library/Application Support/Billie Flow/runtime`.
- Models use the shared Hugging Face cache under `~/.cache/huggingface/hub`
  unless the user's environment configures another `HF_HOME`.
- The standard preferences domain is `uk.billiem.BillieFlow`.

Protocol stdout is machine-only NDJSON. stderr diagnostics and app logs must
never include audio paths, transcripts, prompts, or cleanup content.

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

The shared boundary is `contracts/billie-flow.worker.v1.md`.

## Uninstall

Turn off **Launch Billie Flow at login** before deleting the app, or remove it
later in **System Settings → General → Login Items**. Quit Billie Flow, then
delete:

- `/Applications/Billie Flow.app`
- `~/Library/Application Support/Billie Flow`
- `~/Library/Preferences/uk.billiem.BillieFlow.plist`

The two model caches can be removed separately if no other local tool needs
them:

- `~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo`
- `~/.cache/huggingface/hub/models--mlx-community--Qwen2.5-1.5B-Instruct-4bit`

Do not remove the entire shared Hugging Face cache merely to uninstall Billie
Flow.

## Development and verification

Run the model-free repository test suite with:

```sh
make test
```

For development outside the packaged in-app setup flow, install the current
checkout's worker and models with:

```sh
scripts/bootstrap_worker.sh
```

With full Xcode and the pinned Apple Silicon `uv` 0.11.28 distribution
available, build the app, release archive, and checksum with:

```sh
scripts/package_release.sh
```

Run the complete local release gate with:

```sh
scripts/run_system_acceptance.sh
```

Public proof-of-concept builds are created and attached to GitHub Releases
manually; there is no updater or automatic deployment pipeline.
