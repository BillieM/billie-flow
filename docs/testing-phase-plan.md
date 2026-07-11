# Testing Phase Plan

Status: completed for the voice memo bake-off. This document records the test
contract that produced the current recommendation and report.

The immediate goal is not to build the Swift app. The goal is to run a serious,
repeatable bake-off that tells us which local model path is good enough to build
around.

The test artefact should answer:

- Which ASR backend produces the best raw transcript for Billie-style dictation?
- Which ASR backend is fast enough for a macOS menu bar app?
- Which cleanup model and prompt preserve the user's voice instead of flattening
  it into generic assistant prose?
- Which combinations should become defaults in the app?
- Which combinations should remain available as manual advanced choices?

## Acceptance Criteria

The testing phase is complete when `reports/voice-memo.html` has been replaced
by a redesigned report that includes:

- A diagrammatic branch/tree view of the whole pipeline.
- Every completed ASR backend result.
- Curated cleanup examples derived from the completed style matrix.
- A ranked recommendation section with explicit default choices.
- Transcript/error evidence kept behind click-in sections.
- Failures and blocked model paths shown honestly, not hidden.
- No embedded raw runner JSON, full prompts, raw responses, local paths, or
  raw-output breadcrumbs in the public artifact.

## Experiment Shape

The pipeline is:

```text
audio file
  -> audio normalization
  -> chunking strategy
  -> ASR backend
  -> raw chunk transcripts
  -> stitched transcript
  -> cleanup model
  -> cleanup prompt/style
  -> reviewed output
  -> recommended app defaults
```

Every branch should keep enough metadata to make the result auditable:

- model id
- runtime
- model/runtime install status
- audio duration
- chunk count
- stitched transcript
- cleanup prompt id
- cleanup model id
- output text
- evaluator notes
- known errors

## Current Baseline

The first real clip is:

- `experiments/voice-memo/input.m4a`
- duration: about `35.3s`
- source: Voice Memos export
- useful vocabulary: `Wispr Flow`, `Billie Flow`, `LLM`, `MacBook`

Completed ASR branches:

- `mlx-community/whisper-tiny`
- `mlx-community/whisper-large-v3-turbo`
- `google/gemma-4-12b-it`
- `mistralai/Voxtral-Mini-3B-2507`
- `nvidia/parakeet-tdt-0.6b-v3`

Observed:

- `large-v3-turbo` is a much better baseline than `tiny`.
- `large-v3-turbo` fixed `LLM`, which `tiny` heard as `LLL`.
- both Whisper runs struggled with `Wispr Flow` and `Billie Flow`.
- vocabulary/context correction is required before app defaults are chosen.

## Execution Rules

- Do not run more than one heavy local model generation at a time.
- Use fresh isolated contexts for independent model work.
- Do not silently substitute a model if the requested one fails.
- Preserve broken outputs locally when running experiments, but summarize
  failures in the public report.
- Keep raw transcripts separate from cleanup outputs.
- Do not let a polished cleanup hide ASR errors.
- Prefer local/on-device paths, but record when a local path is blocked.

The run also completed all seven cleanup styles for both configured cleanup
models across all five ASR branches: `70` cleanup outputs in total.

## Implemented Workstreams

The completed testing phase was split into these coordinated workstreams:

1. **Experiment Contract**
   Harden the JSON schema and runner conventions so all model adapters write the
   same shape.

2. **ASR Adapters**
   Implement and run adapters for each candidate backend.

3. **Cleanup Adapters**
   Implement prompt/model combinations over the stitched transcripts.

4. **Evaluation Layer**
   Add ranking, warning flags, and human-readable recommendations.

5. **Report Redesign**
   Replace the generic dashboard with a BillieM-style, diagrammatic comparison
   artefact.

The main orchestration thread owned integration and final judgment. Subthreads
owned individual adapters or report slices.

## Output Files

Expected final testing-phase files:

- `experiments/voice-memo/results.json`
- `experiments/voice-memo/reviews.json`
- `reports/voice-memo.html`
- `docs/decisions.md`

Local runner receipts under `experiments/*/raw/` are ignored by Git. The public
report should be self-contained and should not depend on local audio or raw
JSON files.
