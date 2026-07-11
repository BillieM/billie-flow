# Billie Flow Lab

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

## Planned Model Matrix

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
