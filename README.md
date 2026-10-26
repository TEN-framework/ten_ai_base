# ten_ai_base

## Development setup

Install `uv`, `task`, and `tman`, then prepare the platform-specific TEN runtime
and Python environment:

```sh
task prepare
```

The command installs TEN packages into `.ten` and creates or updates the local
`.venv` from `pyproject.toml`. Run checks through the same managed environment
with `task lint` and `task test`.

The patched TEN Python runtime is installed into `.venv` as a local development
dependency, including its native libraries. After `task prepare`, run package
tests with `uv run pytest tests`; no `PYTHONPATH` configuration is needed.

## TTS request tracing

`AsyncTTS2BaseExtension` uses the host's OpenTelemetry provider through the
`ten_ai_base.tts2` tracer. It creates one `tts.request` span per accepted request,
starting with the first text chunk and including queue wait. The first chunk's
parent context and baggage are retained across queued and interleaved chunks.
The request context is also used by TTS output helpers called from background
provider tasks.

Spans end at `finish_request`, processing failure, flush, or shutdown. Attributes
include `tts.request_id` and `tts.request.outcome` (`completed`, `error`, or
`interrupted`); synthesis errors set the span's error status. Text and audio are
not added to span attributes.

The host configures the SDK provider and exporters. Without a provider, valid
incoming context still propagates, but no request spans are recorded. Tracing
exceptions are suppressed at instrumentation boundaries so they do not block
callbacks or message delivery. Application and transport exceptions retain
their existing behavior. Cancellation and failures still follow the existing
TTS request state machine; tracing does not change request scheduling.

