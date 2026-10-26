#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#

import json

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from ten_ai_base import InstrumentedExtension
from ten_ai_base.otel import extract_otel_context, inject_otel_context
from ten_runtime import AsyncExtension


class _Message:
    def __init__(self) -> None:
        self.properties: dict[str, str] = {}

    def get_property_to_json(self, name: str) -> tuple[str | None, None | str]:
        value = self.properties.get(name)
        return (value, None) if value is not None else (None, "missing")

    def set_property_from_json(self, name: str, value: str) -> None:
        self.properties[name] = value


class _Env:
    def __init__(self) -> None:
        self.sent: list[_Message] = []

    async def send_data(self, message: _Message, options=None) -> None:
        self.sent.append(message)


class _InstrumentedDataExtension(InstrumentedExtension):
    otel_instrumentation_name = "test.instrumented_extension"

    def __init__(self, name: str = "test") -> None:
        super().__init__(name)
        self.received_trace_id: int | None = None

    async def on_data(self, ten_env: _Env, data: _Message) -> None:
        self.received_trace_id = (
            trace.get_current_span().get_span_context().trace_id
        )
        await ten_env.send_data(_Message())


def test_instrumented_extension_is_public_and_propagates_active_span() -> None:
    assert issubclass(InstrumentedExtension, AsyncExtension)

    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    span = trace.get_tracer("test").start_span("parent")
    try:
        with trace.use_span(span, end_on_exit=False):
            message = _Message()
            inject_otel_context(message)

            context = extract_otel_context(message)
            extracted = trace.get_current_span(context).get_span_context()
            assert extracted.trace_id == span.get_span_context().trace_id
            assert json.loads(message.properties["_otel"])["traceparent"]
    finally:
        span.end()


def test_instrumented_extension_attaches_inbound_and_injects_outbound_context() -> None:
    span = trace.get_tracer("test").start_span("parent")
    extension = _InstrumentedDataExtension("test")
    env = _Env()
    message = _Message()
    try:
        with trace.use_span(span, end_on_exit=False):
            inject_otel_context(message)
        import asyncio

        asyncio.run(extension._wrapper_on_data(env, message))
    finally:
        span.end()

    assert extension.received_trace_id == span.get_span_context().trace_id
    assert len(env.sent) == 1
    outbound_context = extract_otel_context(env.sent[0])
    assert (
        trace.get_current_span(outbound_context).get_span_context().trace_id
        == span.get_span_context().trace_id
    )


def test_tts2_command_propagates_context_and_restores_caller():
    import asyncio

    from ten_ai_base.tts2 import AsyncTTS2BaseExtension
    from ten_runtime import Cmd, Data, StatusCode

    class TTS(AsyncTTS2BaseExtension):
        def vendor(self):
            return "test"

        def synthesize_audio_sample_rate(self):
            return 16000

        async def request_tts(self, text):
            raise AssertionError("Unexpected synthesis request")

        async def update_configs(self, configs):
            data = Data.create("configured")
            data.set_property_string("model", configs["model"])
            await self.ten_env.send_data(data)

    class Env(_Env):
        def __init__(self):
            super().__init__()
            self.results = []

        def log_info(self, message):
            pass

        async def return_result(self, result, options=None):
            self.results.append(result)

    async def run():
        extension = TTS("test")
        env = Env()
        await extension._wrapper_on_init(env)
        cmd = Cmd.create("update_configs")
        cmd.set_property_string("model", "test-model")
        parent = trace.NonRecordingSpan(
            trace.SpanContext(123, 456, False, trace.TraceFlags(1))
        )
        with trace.use_span(parent):
            inject_otel_context(cmd)
        caller = trace.get_current_span().get_span_context()
        await extension._wrapper_on_cmd(env, cmd)
        assert trace.get_current_span().get_span_context() == caller
        assert len(env.sent) == len(env.results) == 1
        assert env.sent[0].get_property_string("model")[0] == "test-model"
        assert env.results[0].get_status_code() == StatusCode.OK
        for message in [env.sent[0], env.results[0]]:
            propagated = trace.get_current_span(
                extract_otel_context(message)
            ).get_span_context()
            assert propagated.trace_id == 123
            assert propagated.span_id == 456

    asyncio.run(run())
