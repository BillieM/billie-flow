# Model Matrix

This matrix records what the voice memo bake-off tested before choosing app
defaults, plus the branches that remain lab-only.

## ASR Backends

| ID | Role | Priority | Why Test It | Expected Risk |
| --- | --- | --- | --- | --- |
| `mlx-whisper-large-v3-turbo` | ASR | Required | Best current local Whisper baseline on Apple Silicon. Already performs well on the source voice memo. | Still needs vocabulary bias/correction for project names. |
| `mlx-whisper-tiny` | ASR | Required smoke test | Fast sanity-check backend. Useful to keep for runner/debug speed. | Not good enough for quality decisions. |
| `gemma-4-12b-audio` | ASR/audio understanding | Required lab candidate | Interesting native-audio Gemma path and original project hypothesis. Current run uses public `google/gemma-4-12b-it`; the originally named `google/gemma-4-12b-audio` id does not exist. | Completed locally, but slow and vulnerable to chunk-overlap drift. Keep out of first default. |
| `voxtral-mini-3b` | ASR/audio understanding | Required lab candidate | Long-form audio candidate that may avoid explicit 30-second clip limits. | Completed locally through Transformers, but slow and still misses Billie Flow/Wispr Flow vocabulary. |
| `parakeet-tdt-0.6b-v3` | ASR | Lab candidate | Potential ASR with timestamps and strong filler preservation. | Completed locally through NeMo, but slower than Whisper and still misses Billie Flow/Wispr Flow vocabulary. |

## Cleanup Models

The cleanup path is separate from ASR. Styles are prompts, but the cleanup model
also matters.

| ID | Priority | Use |
| --- | --- | --- |
| `mlx-local-small-text` | Required | Fast local cleanup baseline for the eventual app. |
| `mlx-local-strong-text` | Required | Higher-quality local cleanup for quality comparison. |
| `codex-reference` | Optional | Reference-quality non-app path for judging what good cleanup should look like. |

The completed run used `mlx-community/Qwen2.5-1.5B-Instruct-4bit` for the small
path and `mlx-community/Qwen3-4B-4bit` for the strong path. Do not silently swap
a requested model. If a model is unavailable, mark it blocked and record the
requested and actual checkpoint in the reviewed results.

## Cleanup Styles

Every usable ASR transcript should be passed through these styles:

| ID | Purpose |
| --- | --- |
| `verbatim-context-corrected` | Correct obvious ASR/context errors only. Preserve rough spoken shape. |
| `light-cleanup` | Best likely default for dictation. Remove friction without changing meaning. |
| `message` | Short casual message format. |
| `email` | Clear email draft. |
| `notes` | Headings and bullets for scanning. |
| `blog-draft` | Rough blog-draft shape while preserving uncertainty and voice. |
| `command` | Interpret the dictation as an instruction for an app/agent. |

## Chunking Strategies

The first clip is 35.3 seconds, so it should test simple boundary behavior.

Strategies:

- `whole-file`: for backends that accept the full file.
- `fixed-25s-overlap-2s`: safe Gemma-compatible strategy.
- `vad-logical`: preferred future strategy if VAD is available.

The report should show which strategy each backend used.

## Scoring Dimensions

ASR scoring:

- accuracy
- vocabulary handling
- punctuation/readability
- chunk-boundary continuity
- timestamp usefulness
- latency
- setup friction
- hallucination/compression risk

Cleanup scoring:

- fidelity
- usefulness
- voice preservation
- style fit
- degree of unwanted invention

The final recommendation should choose:

- default ASR backend
- default cleanup model
- default style
- fallback ASR backend
- models exposed in advanced/manual settings
