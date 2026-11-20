# ten_ai_base

## Development setup

Install `uv`, `task`, and `tman`, then prepare the platform-specific TEN runtime
and Python environment:

```sh
task prepare
```

The command installs TEN packages into `.ten` and creates or updates the local
`dev/.venv` from `dev/pyproject.toml`. Run checks through the same managed environment
with `task lint` and `task test`.

The patched TEN Python runtime is installed into `dev/.venv` as a local development
dependency, including its native libraries. After `task prepare`, run package
tests with `uv run --project dev pytest tests`; no `PYTHONPATH` configuration is needed.

The root `pyproject.toml` declares the reusable package only. Local sources and
standalone development tools belong to the separate `dev` project. A parent uv
workspace can use `ten_ai_base` as a member and configure its own TEN runtime
source without requiring this repository's `.ten` directory.

## Speech tracing

`AsyncASRBaseExtension` and `AsyncTTS2BaseExtension` use the host's OpenTelemetry
provider through the `ten_ai_base.asr` and `ten_ai_base.tts2` tracers. Each creates
one session span: `asr.session` or `tts.session`.

Each WebSocket connection has its own `asr.websocket.connection` or
`tts.websocket.connection` span under the session. It starts with the connection
attempt and ends when the connection closes or the attempt fails. Reconnection
starts another connection span. Abnormal closures and failed attempts set error
status; normal closures do not. Session and connection spans carry
`ten.span.long_running=True`.

ASR creates `asr.segment` under `asr.session` on receipt of the first audio frame.
It records `asr.finalize` when a valid finalize signal arrives. After emitting
`asr_finalize_end`, it records `asr.finalize_end` on the segment it closes and
starts the next segment. Both events carry `finalize_id`. Segments continue
across reconnects and close on shutdown if no finalize end arrives.

TTS creates one `tts.synthesis` span per `request_id`, starting with the first
accepted text chunk and including queue wait. It records `tts.request.received`
once. Successful emission of `tts_audio_end` records `tts.result.end` and ends
the synthesis span. Processing failure, interruption, flush, or shutdown also
ends unfinished synthesis spans. Request cleanup alone does not end an active
synthesis span before its result end.

The first text chunk's upstream parent context and baggage are retained across
queued and interleaved chunks. TTS output helpers use that context even when
called from background provider tasks, including outputs sent after audio end
and before request cleanup. Attributes include `tts.request_id` and
`tts.request.outcome` (`completed`, `error`, or `interrupted`); synthesis errors
set error status. Text and audio are not added to span attributes.

Legacy data events are also recorded as `asr.error`, `asr.metrics`, `tts.error`,
and `tts.metrics` span events. They attach to the active ASR segment or matching
TTS synthesis span, with connection and session fallback when the operation span
is unavailable. Metric and metadata maps are serialized as JSON attributes.
These events do not create OTel metric instruments or perform client aggregation.

The host configures the SDK provider and exporters. Without a provider, valid
incoming context still propagates, but no spans are recorded. Tracing failures
do not block callbacks or message delivery. Application and transport exceptions
retain their existing behavior. Tracing does not change request scheduling.
