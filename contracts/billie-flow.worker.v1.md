# Billie Flow Worker Protocol v1

`billie-flow.worker.v1` is a newline-delimited JSON (NDJSON) protocol between
the native app and one managed, persistent Python worker. This file and the
adjacent JSON Schema are the frozen v1 wire contract.

## Transport

- The app starts one worker child process and writes commands to its standard
  input. The worker writes events to standard output.
- Every line is one complete UTF-8 JSON object followed by `\n`. Empty lines,
  arrays, non-object values, and non-protocol output on stdout are invalid.
- Diagnostic output may use stderr, but must never contain transcript text,
  cleanup output, vocabulary prompts, or audio paths.
- `protocol_version` is the integer `1` on every message.
- Commands contain a unique non-empty `id`. Events echo it as `request_id`.
- At most one `process` command is in flight. `hello`, `warmup`, and `shutdown`
  are also handled serially.
- Unknown fields are rejected. v1 changes require a new protocol version.

## Commands

### `hello`

The first command after launch.

```json
{"protocol_version":1,"id":"hello-1","command":"hello","payload":{"client_name":"Billie Flow","client_version":"0.1.0"}}
```

The worker answers with one terminal `ready` event. This confirms protocol and
fixed-model compatibility; it does not require models to be loaded.

### `warmup`

Loads both fixed models and keeps them resident until shutdown.

```json
{"protocol_version":1,"id":"warmup-1","command":"warmup","payload":{}}
```

The worker may emit `phase` events and then emits a terminal `result` event
whose payload has `kind: "warmup"`.

### `process`

Transcribes a finalized 16 kHz mono PCM WAV, applies the requested cleanup
style, then applies versioned deterministic vocabulary corrections.

```json
{"protocol_version":1,"id":"process-1","command":"process","payload":{"audio_path":"/private/var/folders/example/recording.wav","style":"light-cleanup","debug":false}}
```

The worker may emit `phase` events in this order: `loading_asr`,
`transcribing`, `loading_cleanup`, `cleaning`, `correcting`. Already-warm load
phases may be omitted. It then emits exactly one terminal `result` or `error`
event for the request. `debug` controls diagnostic stderr detail only; stdout
always follows the same result shape and stderr never contains user content.

### `shutdown`

```json
{"protocol_version":1,"id":"shutdown-1","command":"shutdown","payload":{}}
```

The worker emits a terminal `result` with `kind: "shutdown"`, flushes stdout,
and exits normally. Cancellation is deliberately transport-level: the app
terminates the worker process, escalates to kill after a short grace period,
and deletes the temporary audio. There is no v1 cancellation command.

## Events

### `ready`

Terminal response to `hello`:

```json
{"protocol_version":1,"request_id":"hello-1","event":"ready","payload":{"worker_version":"0.1.0","asr_model":"mlx-community/whisper-large-v3-turbo","cleanup_model":"mlx-community/Qwen2.5-1.5B-Instruct-4bit","language":"en","corrections_version":"1"}}
```

### `phase`

Non-terminal progress response to `warmup` or `process`:

```json
{"protocol_version":1,"request_id":"process-1","event":"phase","payload":{"phase":"transcribing"}}
```

Allowed phases are `loading_asr`, `transcribing`, `loading_cleanup`, `cleaning`,
and `correcting`.

### `result`

Terminal response to `warmup`, `process`, or `shutdown`. Process success:

```json
{"protocol_version":1,"request_id":"process-1","event":"result","payload":{"kind":"process","raw_asr":"Billy Flow is ready.","raw_cleanup":"Billy Flow is ready.","final_text":"Billie Flow is ready.","corrections":[{"from":"Billy Flow","to":"Billie Flow","count":1}],"timings":{"loading_asr_seconds":0.0,"asr_seconds":1.2,"loading_cleanup_seconds":0.0,"cleanup_seconds":0.8,"correction_seconds":0.001,"total_seconds":2.001},"asr_model":"mlx-community/whisper-large-v3-turbo","cleanup_model":"mlx-community/Qwen2.5-1.5B-Instruct-4bit","style":"light-cleanup","warning":null}}
```

Cleanup failure is the only successful fallback. The worker copies raw ASR
through `final_text`, sets `raw_cleanup` to `null`, returns no corrections, and
returns the stable warning `cleanup_failed_raw_asr`. The app may place that
text on the clipboard and must surface a warning. ASR failure and
empty/whitespace-only transcription are terminal errors, so the app leaves the
clipboard untouched. All six timing values are non-negative seconds;
`total_seconds` covers the complete process request.

Warmup success uses `{"kind":"warmup","warmed":true}`. Shutdown success uses
`{"kind":"shutdown"}`.

### `error`

Terminal failure:

```json
{"protocol_version":1,"request_id":"process-1","event":"error","payload":{"code":"asr_failed","message":"Speech recognition failed.","recoverable":true}}
```

Stable v1 codes are `invalid_request`, `protocol_mismatch`, `not_ready`,
`audio_invalid`, `asr_failed`, `empty_transcript`, and `internal_error`.
Messages are safe display strings and must not include content or paths.

## Fixed v1 behaviour

- ASR: `mlx-community/whisper-large-v3-turbo`, English.
- Cleanup: `mlx-community/Qwen2.5-1.5B-Instruct-4bit`.
- Styles: `verbatim-context-corrected`, `light-cleanup`, and `message`.
- Cleanup receives the known vocabulary `Billie Flow`, `Wispr Flow`, `LLM`,
  `MacBook`, `SwiftUI`, `MLX`, `Hugging Face`, and `Qwen` as spelling context.
- Corrections version `1` performs case-insensitive, boundary-aware,
  longest-first replacements for known unambiguous variants. It never replaces
  the ambiguous phrase `with flow`.
- The worker never deletes input audio. The app owns the temporary file and
  guarantees deletion after success, failure, cancellation, and quit.
