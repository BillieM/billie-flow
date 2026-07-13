# Billie Flow

Billie Flow is an unsupported proof of concept for privacy-preserving local
speech to text on Apple Silicon. It is a macOS 26 Swift 6 menu-bar app: hold a
custom global hotkey, speak, release, and receive locally transcribed and
lightly cleaned English text on the clipboard.

This repository contains the native app, its local Python/MLX worker, the model
evaluation lab used to select the fixed models, and the automated acceptance
gate. It is source code and a working demonstration, not a maintained product.
There is no support commitment, updater, compatibility promise, App Store
release, or notarised distribution.

## Supported setup

- Apple Silicon Mac. The release app and its bundled setup executable are
  arm64-only; Intel Macs are not supported.
- macOS 26 or later.
- English dictation only. The worker protocol fixes the language to `en`.
- About 3.5 GB of free space for the Python runtime and model downloads, plus
  working space and any existing Hugging Face cache overhead.
- An internet connection for the one-time runtime, dependency, and model setup.

## Install and run

1. Download `Billie-Flow-v0.2.0-apple-silicon.zip` and its checksum from
   [GitHub Releases](https://github.com/BillieM/billie-flow/releases), unzip it,
   and move `Billie Flow.app` to `/Applications`.
2. Open the app. Because this proof-of-concept build is not notarised, macOS may
   block it; follow the bounded Gatekeeper steps below if you choose to proceed.
3. When the worker is missing, Settings opens automatically. Choose
   **Install local models…**, review the **Install local speech models?** consent
   alert, then choose **Install**. Nothing large is downloaded before this
   confirmation.
4. The app prepares Python, installs the local runtime, downloads the speech
   model, downloads the cleanup model, and verifies the setup. You can cancel
   during setup or retry a failed installation. The install uses the pinned
   `uv` executable and worker payload bundled inside the app; release users do
   not need Terminal, Homebrew, or a repository checkout.
5. Approve microphone access, choose a shortcut containing Command or Control,
   then hold the shortcut while speaking and release it to process. The result
   is copied to the clipboard; the app does not paste it.

The consented setup installs roughly 1.1 GB under
`~/Library/Application Support/Billie Flow/runtime` and fetches roughly 2.5 GB
of fixed model data into the Hugging Face cache. Exact transfer and disk use
vary when dependencies or model files are already cached.

### Gatekeeper warning

The proof-of-concept build is ad-hoc signed and is **not notarised by Apple**.
macOS therefore cannot verify the developer or check that the downloaded build
was notarised. Do not override Gatekeeper unless you obtained the app from this
repository, verified any published checksum, and accept that risk.

After trying to open the app once, open **System Settings → Privacy & Security**,
scroll to **Security**, choose **Open Anyway**, authenticate, and confirm
**Open**. Apple documents this exception flow in
[Open a Mac app from an unknown developer](https://support.apple.com/en-gb/guide/mac-help/mh40616/mac).
Do not disable Gatekeeper globally.

## Models and dependencies

The app has no model picker. Production inference uses exactly:

- ASR: [`mlx-community/whisper-large-v3-turbo`](https://huggingface.co/mlx-community/whisper-large-v3-turbo),
  an MLX conversion of
  [`openai/whisper-large-v3-turbo`](https://huggingface.co/openai/whisper-large-v3-turbo)
  (MIT licensed).
- Cleanup: [`mlx-community/Qwen2.5-1.5B-Instruct-4bit`](https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit),
  an MLX conversion of
  [`Qwen/Qwen2.5-1.5B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)
  (Apache 2.0 licensed).

The release app bundles `uv==0.11.28`, the worker source, and the dependency
lock, but no model weights. The installed worker uses Python 3.12 and pins its
core MLX stack to `mlx==0.32.0`,
`mlx-metal==0.32.0`, `mlx-whisper==0.4.3`, and `mlx-lm==0.31.3`. Every resolved
Python dependency is pinned in `worker/requirements.lock`. Model weights are
downloaded from Hugging Face and are not included in this repository or covered
by this repository's MIT licence; their own model cards and licences apply.
The source code is available under the [MIT License](LICENSE).

## Privacy and local storage

- Inference runs locally after setup. The app does not upload audio or
  transcripts. The consented installer contacts the Python and model download
  services used by `uv` and Hugging Face.
- Each recording is a temporary 16 kHz mono WAV. The app deletes it after
  success, failure, cancellation, and quit, and removes stale owned WAVs on the
  next launch after a crash.
- Transcript text is held only for processing and copied to the system
  clipboard. Billie Flow keeps no transcript history or content logs. Other
  applications with clipboard access may still read clipboard contents.
- The runtime is stored under
  `~/Library/Application Support/Billie Flow/runtime`. Model files remain in
  the shared Hugging Face cache under `~/.cache/huggingface/hub`.
- Settings are stored in the standard preferences domain
  `uk.billiem.BillieFlow`.

See `docs/native-v0.2.md` for the full lifecycle and storage boundary.

## Uninstall

Turn off **Launch Billie Flow at login** in the app first, or remove it from
**System Settings → General → Login Items**. Then quit the app and delete:

- `/Applications/Billie Flow.app`
- `~/Library/Application Support/Billie Flow`
- `~/Library/Preferences/uk.billiem.BillieFlow.plist`

To reclaim model space as well, remove only these model directories from the
shared Hugging Face cache:

- `~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo`
- `~/.cache/huggingface/hub/models--mlx-community--Qwen2.5-1.5B-Instruct-4bit`

Do not delete the whole Hugging Face cache if other local tools use it.

## Repository layout and development

- `app/`: Swift app, Xcode project, and Swift tests.
- `worker/`: persistent Python 3.12 NDJSON model worker and tests.
- `contracts/`: frozen `billie-flow.worker.v1` wire contract.
- `scripts/bootstrap_worker.sh`: developer-only local runtime setup.
- `docs/native-v0.2.md`: public release architecture, setup, and privacy boundary.
- `docs/native-v0.1-qa.md`: historical v0.1 automated acceptance record.

Run the model-free repository tests with:

```sh
make test
```

For development outside the packaged setup flow, install the current checkout's
worker and fixed models with:

```sh
scripts/bootstrap_worker.sh
```

With full Xcode installed, build the arm64 app, release zip, and SHA-256 file:

```sh
scripts/package_release.sh
```

The full system acceptance gate is intentionally local because it exercises the
packaged macOS app and production MLX models:

```sh
scripts/run_system_acceptance.sh
```

## Model evaluation lab

Billie Flow Lab is a small offline harness for comparing local speech-to-text
and cleanup models before building the native macOS app.

The first useful workflow is intentionally simple:

1. Put an audio file somewhere under `experiments/<run-id>/`.
2. Run ASR backends against it.
3. Run cleanup/style prompts over each stitched transcript.
4. Save the outputs in `results.json`.
5. Generate a self-contained comparison page with `scripts/build_report.py`.

The report is meant to answer practical questions:

- Which ASR backend produced the most usable transcript?
- Which backend hallucinated, dropped words, or mangled punctuation?
- Which cleanup style preserved the original thought while making it easier to read?
- Which model path is good enough for the first Swift app?

## Current Shape

This repo separates model execution from report generation. Model runs can
write local runner receipts, then the assembler normalizes useful evidence into
the `results.json` report contract.

```sh
python3 scripts/build_report.py \
  --input experiments/voice-memo/results.json \
  --output reports/voice-memo.html
```

Then open `reports/voice-memo.html` in a browser.

For a real run, model adapters first write local receipts under the ignored
`experiments/<run-id>/raw/` tree:

```sh
python3 scripts/attempt_asr_adapters.py \
  --manifest experiments/voice-memo/manifest.json

python3 scripts/assemble_results.py \
  --manifest experiments/voice-memo/manifest.json \
  --output experiments/voice-memo/results.json

python3 scripts/run_cleanup_passes.py \
  --input experiments/voice-memo/results.json \
  --output experiments/voice-memo/results.json

python3 scripts/review_results.py \
  --input experiments/voice-memo/results.json \
  --output experiments/voice-memo/results.json \
  --reviews-output experiments/voice-memo/reviews.json

python3 scripts/validate_results.py \
  experiments/voice-memo/results.json

python3 scripts/build_report.py \
  --input experiments/voice-memo/results.json \
  --output reports/voice-memo.html
```

Audio files are intentionally ignored by Git. Public reports do not embed local
audio or raw runner JSON. The committed `results.json` snapshot also excludes
receipt paths, prompts, raw responses, and pre-correction model output.

`run_cleanup_passes.py` needs a Python runtime with `mlx-lm` when generating
real local cleanup outputs. If a model path is blocked or renamed during setup,
record the setup finding instead of silently replacing it with a different
model. Local raw receipts under `experiments/*/raw/` are ignored by Git.

## Lab Model Matrix

ASR backends:

- `mlx-whisper-large-v3-turbo`: pragmatic Apple Silicon Whisper baseline.
- `gemma-4-12b-audio`: native-audio Gemma branch. The current run uses
  `google/gemma-4-12b-it`; `google/gemma-4-12b-audio` is not a valid public Hub id.
- `voxtral-mini-3b`: long-form audio candidate.
- `parakeet-tdt-0.6b-v3`: timestamped ASR candidate through NeMo.

Cleanup styles:

- `verbatim-context-corrected`: minimal punctuation and obvious correction only.
- `light-cleanup`: readable, but still close to the spoken wording.
- `message`: concise chat/message style.
- `email`: slightly more formal structure.
- `notes`: skimmable bullets and headings.
- `blog-draft`: preserve the rough thought while making it publishable enough to edit.
- `command`: interpret the dictation as an instruction for an app or agent.

## Data Contract

`experiments/<run-id>/results.json` contains:

- `run`: metadata about the audio and run.
- `asr_results`: one entry per ASR backend.
- `style_results`: cleanup outputs derived from ASR transcripts.
- `evaluations`: rankings, warning flags, lab-only/setup findings, blocked
  model paths, and app defaults.
- `recommendations`: reviewer notes used by the report.

The generated public report uses `results.json` as its source. It intentionally
does not embed full prompts, raw responses, raw JSON, local paths, or audio.

See `experiments/voice-memo/results.json` for the completed public evidence
snapshot.

## Planning Docs

- `docs/testing-phase-plan.md`: acceptance criteria and execution plan for the
  full bake-off.
- `docs/model-matrix.md`: ASR backends, cleanup models, styles, and scoring
  dimensions.
- `docs/report-design-plan.md`: direction for the redesigned diagrammatic
  report.
- `docs/swift-app-plan.md`: deferred native macOS app plan.
- `docs/decisions.md`: decisions and open questions.

## Public Source Boundary

The repository keeps the code, model configuration, reviewed experiment
results, and generated public report. It intentionally does not keep source
audio, model caches, runner receipts, prompts, raw responses, local filesystem
paths, or environment credentials.

The committed voice memo results are a reviewed experiment snapshot, not a
promise that the model run can be reproduced without the original local audio,
model downloads, and platform-specific runtimes.

## Report Artifact

The canonical artifact is `reports/voice-memo.html`. It is self-contained and
can be opened directly or served by any static file server. Publication belongs
to the BillieM website repository so its route, shared chrome, sensitivity
checks, sitemap entry, and deployment remain part of the main site contract.
