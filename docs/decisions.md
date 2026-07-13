# Decisions

This file records decisions made while the project is still exploratory.

## 2026-07-08: Build the Testing Harness Before the Swift App

Decision: run a full model/style bake-off before building the native app.

Reasoning:

- The main unknown is model quality and runtime behaviour, not Swift UI.
- ASR and cleanup should be evaluated separately.
- The report can become source material for the eventual blog post.

## 2026-07-08: Keep ASR and Cleanup as Separate Stages

Decision: the app and testing harness should treat speech recognition and text
cleanup as separate model stages.

Reasoning:

- ASR errors must remain visible.
- Cleanup prompts are cheap to vary.
- A polished cleanup can hide transcription failure.
- The eventual app can expose styles without changing ASR backend.

## 2026-07-08: Use MLX Whisper large-v3-turbo as the First Baseline

Decision: keep `mlx-community/whisper-large-v3-turbo` as the first serious ASR
baseline.

Evidence:

- On the source voice memo, it handled `LLM` correctly where tiny heard `LLL`.
- Warm runtime was roughly `3.68s` for a `35.3s` clip.
- It still failed on `Wispr Flow` and `Billie Flow`, so it needs context or
  correction.

## 2026-07-08: Do Not Use Whisper Tiny for Quality Decisions

Decision: keep `mlx-community/whisper-tiny` only as a smoke-test backend.

Reasoning:

- It is fast enough for runner checks.
- It mangles important project vocabulary.
- It should not decide app defaults.

## 2026-07-08: First App Should Avoid Accessibility API

Decision: first Swift app pass should copy to clipboard instead of pasting into
the focused app.

Reasoning:

- Global recording and microphone capture do not require Accessibility.
- Automatic paste can be phase two.
- Copy-to-clipboard is enough to validate the model pipeline.

## 2026-07-08: Default ASR Should Be MLX Whisper large-v3-turbo

Decision: use `mlx-community/whisper-large-v3-turbo` as the first Swift worker
ASR default.

Evidence:

- It is the fastest practical quality ASR path in the completed voice memo
  bake-off.
- It produced a coherent full transcript in roughly `3.68s` for a `35.3s`
  memo.
- It correctly heard `LLM`, where `mlx-whisper-tiny` heard `LLL`.
- It still wrote `Wispr Flow` as `Whisperflow` and `Billie Flow` as
  `Billy Flow`, so the app needs explicit vocabulary correction.
- Parakeet, Voxtral, and Gemma all completed after installing their runtimes,
  but took roughly `42.81s`, `110.85s`, and `258.79s` respectively on the same
  memo.

App implication: expose `mlx-whisper-tiny` only as a smoke-test/manual fallback,
not a quality fallback.

## 2026-07-08: Default Cleanup Should Be Small Local Text + Light Cleanup

Decision: use `mlx-local-small-text` with `light-cleanup` as the first cleanup
default.

Concrete model for this run:

- `mlx-local-small-text`: `mlx-community/Qwen2.5-1.5B-Instruct-4bit`

Evidence:

- It completed all seven required styles for all five completed ASR
  transcripts.
- Its top `light-cleanup` output tied the stronger model in evaluator score.
- It was faster and less verbose than the Qwen3 strong pass on this memo.
- The stronger `mlx-local-strong-text` slot used
  `mlx-community/Qwen3-4B-4bit`; it completed, but did not beat the small model
  for the likely default style.

App implication: keep the stronger cleanup model as an advanced/manual choice
for now rather than the default.

## 2026-07-08: Vocabulary Correction Must Be Deterministic and Visible

Decision: add a deterministic vocabulary correction layer around cleanup output
instead of relying on the cleanup model to repair project names unaided.

Evidence:

- All completed ASR paths got at least one key project term wrong.
- The local cleanup models often repeated `Whisperflow` and `Billy Flow` even
  after the prompt listed the correct vocabulary.
- The final run kept raw model output separately and applied explicit
  post-processing for `Wispr Flow`, `Billie Flow`, `LLM`, and `MacBook`.
- `65` of `70` cleanup outputs needed at least one deterministic vocabulary
  replacement.

App implication: the worker API should return raw ASR, raw cleanup model output,
and final corrected output separately in debug/test mode.

## 2026-07-08: Audio Model Paths Are Lab-Only After Install-and-Run Pass

Decision: do not use Gemma audio, Voxtral Mini, or Parakeet in first app
defaults.

Evidence:

- `parakeet-tdt-0.6b-v3` completed through NeMo on MPS in roughly `42.81s`.
  It preserved filler and timing detail well, but still wrote `Wispr Flow` as
  `Whisperflow` and `Billie Flow` as `Billy Flow`.
- `voxtral-mini-3b` completed through Transformers on MPS in roughly
  `110.85s`. It produced readable text and heard `LLM`/`MacBook`, but wrote
  `Wispr Flow` as `WhisperFlow` and `Billie Flow` as `BillyFlow`.
- `gemma-4-12b-audio` completed through Transformers on MPS in roughly
  `258.79s` using `google/gemma-4-12b-it`, because the originally configured
  `google/gemma-4-12b-audio` Hub id does not exist. The run showed chunk
  overlap drift around the Wispr Flow sentence.
- `google/gemma-3n-E4B-it` remains blocked by Hugging Face gated-repo access
  without local authentication.
- The cached `mlx-community/gemma-4-12B-it-4bit` cleanup candidate also failed
  under `mlx-lm 0.31.3` because `gemma4_unified` is unsupported, so it was not
  used as the strong cleanup model.

App implication: keep these as explicit lab-only branches in the report. They
are useful evidence and possible future advanced options, but not first app
defaults.

## 2026-07-08: Public Report Should Not Embed Raw Runner Receipts

Decision: keep `experiments/*/raw/` out of the public repo and public report.

Reasoning:

- The raw files are useful local receipts, but they include full prompts, raw
  responses, setup notes, and repeated transcript text.
- The public artifact should support a reader skimming the evidence, not expose
  a lab dump.
- The cleaned `results.json` contract already contains the review, ranking,
  curated output, vocabulary failures, and app-default evidence needed by the
  report.
- Keeping raw receipts ignored by Git lowers the chance that a future local run
  accidentally publishes sensitive input.

App implication: debug/test modes can still return raw ASR, raw cleanup model
output, and final corrected output. The public artifact should render selected
evidence only.

## 2026-07-12: Freeze Native v0.1 as a Narrow Proof of Concept

Decision: ship macOS 26-only Swift 6 sources for a menu-bar, hold-to-record,
copy-only utility backed by one persistent Python 3.12 worker.

The shared process boundary is the frozen `billie-flow.worker.v1` NDJSON
contract. The first app has exactly three styles and fixed evidence-backed ASR
and cleanup models. It has no model picker, vocabulary editor, auto-paste,
transcript history, updater, notarization, App Store path, or automatic public
release workflow.

Reasoning:

- The bake-off already selected the useful fixed defaults.
- Copy-only avoids Accessibility and Input Monitoring permissions.
- A small native surface keeps the first acceptance test about dictation quality,
  latency, lifecycle correctness, and privacy rather than distribution features.
- Versioned deterministic corrections make known-name repair inspectable without
  adding first-version vocabulary UI.

## 2026-07-12: App Owns Temporary Audio and Worker Cancellation

Decision: the native app owns every temporary WAV and deletes it after success,
failure, cancellation, and quit. The worker never deletes input audio.

Cancellation terminates the persistent worker and escalates to kill before the
app removes the audio. A later recording starts a fresh worker. This gives the
app one unambiguous lifecycle owner and prevents inference from racing deletion.

## 2026-07-13: Publish the Source Without Turning It Into a Product

Decision: make the source and manually built app available as an unsupported
proof of concept. Keep the narrow product boundary, local automated release
gate, and fixed models. Do not add an updater, App Store work, automatic release
pipeline, support commitment, or broader compatibility promise.

The public documentation must state that the worker is Apple Silicon-only,
recognition is fixed to English, first setup installs and downloads roughly
3.5 GB, and the downloadable app is ad-hoc signed rather than notarised. The app
must ask for explicit consent before its bundled bootstrap installs the runtime
or downloads either model.

Reasoning:

- The source and experiment report are useful evidence for a project write-up.
- Manual GitHub Releases are proportionate for a proof of concept.
- Honest setup, model attribution, privacy, and Gatekeeper documentation matter
  more here than product infrastructure.
- Developer ID signing and notarisation can be added later without changing the
  local app architecture.
