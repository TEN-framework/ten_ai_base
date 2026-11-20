# ABOUTME: Verifies request tracing across the TTS2 queue and lifecycle.
# ABOUTME: Exercises SDK-exported spans and delivery with failed instrumentation.

import asyncio
import json
import time

import pytest
from opentelemetry import baggage, context, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from ten_ai_base.message import TTSAudioEndReason
from ten_ai_base.otel import extract_otel_context, inject_otel_context
from ten_ai_base.otel.ten_env import InstrumentedTenEnv
from ten_ai_base.tts2 import AsyncTTS2BaseExtension
from ten_runtime import Data


class Env:
    def __init__(self):
        self.sent = []

    async def send_data(self, data, options=None):
        self.sent.append(data)

    def log_info(self, *args, **kwargs):
        pass

    log_debug = log_warn = log_error = log_info


class TTS(AsyncTTS2BaseExtension):
    def __init__(self, name):
        super().__init__(name)
        self.received = asyncio.Queue()

    def vendor(self):
        return "test"

    def synthesize_audio_sample_rate(self):
        return 16000

    async def request_tts(self, text):
        await self.send_tts_audio_start(text.request_id)
        if text.text_input_end:
            await self.send_tts_audio_end(text.request_id, 0, 0)
            await self.finish_request(text.request_id)
        await self.received.put(text.request_id)


@pytest.fixture
def spans(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    yield exporter
    provider.shutdown()


async def receive(extension, env, request_id, parent, end=False):
    data = Data.create("tts_text_input")
    data.set_property_from_json(
        "",
        json.dumps(
            {
                "request_id": request_id,
                "text": "hello",
                "text_input_end": end,
            }
        ),
    )
    token = context.attach(baggage.set_baggage("request", request_id))
    try:
        with trace.use_span(parent):
            inject_otel_context(data)
            await extension._wrapper_on_data(env, data)
    finally:
        context.detach(token)


def parent(trace_id):
    return trace.NonRecordingSpan(
        trace.SpanContext(trace_id, trace_id + 1, False, trace.TraceFlags(1))
    )


@pytest.mark.asyncio
async def test_request_spans_include_queue_wait_and_keep_interleaved_context(spans):
    env = Env()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    before = time.time_ns()
    await receive(ext, env, "a", parent(100))
    await receive(ext, env, "b", parent(200), end=True)
    await receive(ext, env, "a", parent(300), end=True)
    queued = time.time_ns()
    assert not spans.get_finished_spans()
    worker = asyncio.create_task(ext._process_input_queue(env))
    try:
        order = [await asyncio.wait_for(ext.received.get(), 2) for _ in range(3)]
        assert order == ["a", "a", "b"]
        finished = {
            s.attributes["tts.request_id"]: s for s in spans.get_finished_spans()
        }
        assert set(finished) == {"a", "b"}
        for request_id, trace_id in [("a", 100), ("b", 200)]:
            span = finished[request_id]
            assert span.name == "tts.synthesis"
            assert span.context.trace_id == trace_id
            assert span.parent.span_id == trace_id + 1
            assert before <= span.start_time <= queued <= span.end_time
            assert span.events[0].name == "tts.request.received"
            assert span.events[0].attributes["tts.request_id"] == request_id
            assert sum(event.name == "tts.request.received" for event in span.events) == 1
            assert [event.name for event in span.events] == [
                "tts.request.received", "tts.result.end",
            ]
        for data in env.sent:
            request_id = json.loads(data.get_property_to_json("")[0])["request_id"]
            propagated = extract_otel_context(data)
            assert (
                trace.get_current_span(propagated).get_span_context().span_id
                == finished[request_id].context.span_id
            )
            assert baggage.get_baggage("request", propagated) == request_id
    finally:
        await ext.input_queue.put(None)
        await asyncio.wait_for(worker, 2)


@pytest.mark.asyncio
async def test_flush_ends_waiting_spans_and_preserves_flush_ack(spans):
    env = Env()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    await receive(ext, env, "a", parent(100))
    data = Data.create("tts_flush")
    data.set_property_from_json("", '{"flush_id":"flush"}')
    await ext._wrapper_on_data(env, data)
    assert [d.get_name() for d in env.sent] == ["tts_flush_end"]
    finished = spans.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].attributes["tts.request.outcome"] == "interrupted"


@pytest.mark.asyncio
async def test_injection_failure_does_not_prevent_message_delivery(monkeypatch):
    from ten_ai_base.otel import propagation

    def fail(*args, **kwargs):
        raise RuntimeError("broken propagator")

    monkeypatch.setattr(propagation, "inject", fail)
    env = Env()
    data = Data.create("message")
    await InstrumentedTenEnv(env).send_data(data)
    assert env.sent == [data]


def test_extraction_failure_returns_empty_context(monkeypatch):
    from ten_ai_base.otel import propagation

    def fail():
        raise RuntimeError("broken propagator")

    monkeypatch.setattr(propagation, "get_global_textmap", fail)
    extracted = extract_otel_context(Data.create("message"))
    assert not trace.get_current_span(extracted).get_span_context().is_valid


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["no_provider", "start", "end"])
async def test_tracing_failure_preserves_tts_delivery(monkeypatch, failure):
    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    if failure == "no_provider":
        tracer = trace.NoOpTracerProvider().get_tracer("test")
    elif failure == "start":

        class BrokenTracer:
            def start_span(self, *args, **kwargs):
                raise RuntimeError("span creation failed")

        tracer = BrokenTracer()
    else:
        from opentelemetry.sdk.trace import SpanProcessor

        class BrokenProcessor(SpanProcessor):
            def on_end(self, span):
                raise RuntimeError("span processor failed")

        provider.add_span_processor(BrokenProcessor())
    monkeypatch.setattr(trace, "get_tracer", lambda *args, **kwargs: tracer)
    env = Env()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    await receive(ext, env, "a", parent(100), end=True)
    await ext.input_queue.put(None)
    await asyncio.wait_for(ext._process_input_queue(env), 2)
    assert [d.get_name() for d in env.sent] == ["tts_audio_start", "tts_audio_end"]
    for data in env.sent:
        extracted = extract_otel_context(data)
        assert trace.get_current_span(extracted).get_span_context().trace_id == 100
        assert baggage.get_baggage("request", extracted) == "a"
    provider.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["error", "interrupted"])
async def test_processing_failure_ends_span_and_next_request_still_runs(spans, reason):
    class FailingTTS(TTS):
        async def request_tts(self, text):
            if text.request_id == "a":
                if reason == "interrupted":
                    raise asyncio.CancelledError()
                raise RuntimeError("synthesis failed")
            await super().request_tts(text)

    env = Env()
    ext = FailingTTS("tts")
    await ext._wrapper_on_init(env)
    await receive(ext, env, "a", parent(100))
    await ext.input_queue.put(None)
    await asyncio.wait_for(ext._process_input_queue(env), 2)
    finished = spans.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].attributes["tts.request.outcome"] == reason
    if reason == "error":
        assert finished[0].status.status_code == trace.StatusCode.ERROR
    # A flush releases the existing TTS state machine after a provider failure.
    data = Data.create("tts_flush")
    data.set_property_from_json("", '{"flush_id":"flush"}')
    await ext._wrapper_on_data(env, data)
    await receive(ext, env, "b", parent(200), end=True)
    await ext.input_queue.put(None)
    await asyncio.wait_for(ext._process_input_queue(env), 2)
    assert len(spans.get_finished_spans()) == 2
    assert [d.get_name() for d in env.sent] == [
        "tts_flush_end",
        "tts_audio_start",
        "tts_audio_end",
    ]


@pytest.mark.asyncio
async def test_shutdown_ends_unfinished_request_once(spans):
    env = Env()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    await receive(ext, env, "a", parent(100))
    await ext._wrapper_on_stop(env)
    await ext._wrapper_on_deinit(env)
    finished = spans.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].attributes["tts.request.outcome"] == "interrupted"
    assert "metrics" in [d.get_name() for d in env.sent]


@pytest.mark.asyncio
async def test_background_output_uses_request_context(spans):
    env = Env()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    ready = asyncio.Event()

    async def output():
        await ready.wait()
        await ext.send_tts_audio_end("a", 0, 0)
        await ext.finish_request("a")

    background = asyncio.create_task(output())
    await receive(ext, env, "a", parent(100))
    ready.set()
    await asyncio.wait_for(background, 2)
    finished = spans.get_finished_spans()
    assert len(finished) == 1
    extracted = trace.get_current_span(
        extract_otel_context(env.sent[0])
    ).get_span_context()
    assert extracted.span_id == finished[0].context.span_id


@pytest.mark.asyncio
async def test_synthesis_ends_at_audio_end_and_retains_context_until_cleanup(spans):
    env = Env()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    await receive(ext, env, "a", parent(100))
    before_end = time.time_ns()
    await ext.send_tts_audio_end("a", 12, 34)
    after_end = time.time_ns()
    finished = spans.get_finished_spans()
    assert len(finished) == 1
    synthesis = finished[0]
    assert synthesis.name == "tts.synthesis"
    assert synthesis.parent.span_id == 101
    assert synthesis.context.trace_id == 100
    assert before_end <= synthesis.end_time <= after_end
    assert [event.name for event in synthesis.events] == [
        "tts.request.received", "tts.result.end",
    ]
    assert synthesis.events[-1].attributes["tts.request_id"] == "a"
    assert before_end <= synthesis.events[-1].timestamp <= synthesis.end_time

    await ext.send_usage_metrics("a")
    propagated = extract_otel_context(env.sent[-1])
    propagated_span = trace.get_current_span(propagated).get_span_context()
    assert propagated_span.trace_id == synthesis.context.trace_id
    assert propagated_span.span_id == synthesis.context.span_id
    assert baggage.get_baggage("request", propagated) == "a"
    await ext.finish_request("a")
    assert len(spans.get_finished_spans()) == 1


@pytest.mark.asyncio
async def test_request_cleanup_does_not_end_synthesis_before_result_end(spans):
    env = Env()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    await receive(ext, env, "a", parent(100))
    await ext.finish_request("a")
    assert not spans.get_finished_spans()
    await ext.send_tts_audio_end("a", 0, 0)
    assert len(spans.get_finished_spans()) == 1
    assert spans.get_finished_spans()[0].events[-1].name == "tts.result.end"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", [TTSAudioEndReason.REQUEST_END, TTSAudioEndReason.ERROR, TTSAudioEndReason.INTERRUPTED],
)
async def test_synthesis_result_end_status_matches_reason(spans, reason):
    env = Env()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    await receive(ext, env, "a", parent(100))
    await ext.send_tts_audio_end("a", 0, 0, reason=reason)
    await ext.finish_request("a", reason=reason)
    finished = spans.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].status.status_code == (
        trace.StatusCode.ERROR if reason == TTSAudioEndReason.ERROR else trace.StatusCode.UNSET
    )
    assert finished[0].events[-1].attributes["reason"] == reason.value


@pytest.mark.asyncio
async def test_failed_audio_end_delivery_does_not_record_result_end(spans):
    class BrokenEnv(Env):
        async def send_data(self, data, options=None):
            raise ValueError("transport failed")

    env = BrokenEnv()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    await receive(ext, env, "a", parent(100))
    with pytest.raises(ValueError, match="transport failed"):
        await ext.send_tts_audio_end("a", 0, 0)
    assert not spans.get_finished_spans()
    await ext._wrapper_on_deinit(env)
    synthesis = spans.get_finished_spans()[0]
    assert synthesis.attributes["tts.request.outcome"] == "interrupted"
    assert [event.name for event in synthesis.events] == ["tts.request.received"]


@pytest.mark.asyncio
async def test_usage_after_synthesis_end_is_recorded_on_connection(spans):
    env = Env()
    ext = TTS("tts")
    await ext._wrapper_on_init(env)
    await ext.on_connected()
    await receive(ext, env, "a", parent(100))
    await ext.send_tts_audio_end("a", 0, 0)
    await ext.send_usage_metrics("a")
    await ext.finish_request("a")
    await ext.on_disconnected(code=1000)
    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == [
        "tts.synthesis", "tts.websocket.connection",
    ]
    assert [event.name for event in finished[1].events] == ["tts.metrics"]
    assert finished[1].events[0].attributes["tts.request_id"] == "a"
    await ext.on_deinit(env)


@pytest.mark.asyncio
async def test_transport_exception_is_not_hidden_by_instrumentation():
    class BrokenEnv(Env):
        async def send_data(self, data, options=None):
            raise ValueError("transport failed")

    with pytest.raises(ValueError, match="transport failed"):
        await InstrumentedTenEnv(BrokenEnv()).send_data(Data.create("message"))


@pytest.mark.asyncio
async def test_root_span_failure_does_not_prevent_callback_delivery(monkeypatch):
    from ten_ai_base.otel import InstrumentedExtension

    class BrokenTracer:
        def start_span(self, *args, **kwargs):
            raise RuntimeError("tracer failed")

    class Extension(InstrumentedExtension):
        async def on_data(self, env, data):
            self.start_root_span("root")
            await env.send_data(data)
            self.end_root_span()

    monkeypatch.setattr(trace, "get_tracer", lambda *args, **kwargs: BrokenTracer())
    env = Env()
    data = Data.create("message")
    await Extension("test").on_data(InstrumentedTenEnv(env), data)
    assert env.sent == [data]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    ["send_cmd", "send_data", "send_audio_frame", "send_video_frame", "return_result"],
)
@pytest.mark.parametrize("failure", ["exception", "error_return"])
async def test_carrier_write_failure_still_calls_transport(operation, failure):
    class Message:
        def set_property_from_json(self, *args):
            if failure == "exception":
                raise RuntimeError("carrier write failed")
            return "carrier write failed"

    class Transport:
        def __init__(self):
            self.delivered = []

        async def send(self, message, *options):
            self.delivered.append(message)
            return "transport-result"

        send_cmd = send_data = send_audio_frame = send_video_frame = return_result = (
            send
        )

    transport = Transport()
    message = Message()
    with trace.use_span(parent(100)):
        result = await getattr(InstrumentedTenEnv(transport), operation)(message)
    assert result == "transport-result"
    assert transport.delivered == [message]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["read", "attach", "detach"])
async def test_context_failure_still_delivers_callback(monkeypatch, failure):
    from ten_ai_base.otel import InstrumentedExtension, propagation

    class Message:
        def get_property_to_json(self, key):
            if failure == "read":
                raise RuntimeError("property read failed")
            return "{}", None

    def fail(*args):
        raise RuntimeError("context failed")

    if failure == "attach":
        monkeypatch.setattr(propagation, "attach", fail)
    elif failure == "detach":
        detach = propagation.detach

        def detach_then_fail(token):
            detach(token)
            fail()

        monkeypatch.setattr(propagation, "detach", detach_then_fail)

    deliveries = []

    async def callback(env, data):
        deliveries.append(data)

    message = Message()
    ext = InstrumentedExtension("test")
    await ext._run_with_message_context(Env(), message, callback)
    assert deliveries == [message]


@pytest.mark.asyncio
async def test_application_exception_and_context_restoration():
    from ten_ai_base.otel import InstrumentedExtension

    data = Data.create("message")
    with trace.use_span(parent(100)):
        inject_otel_context(data)

    async def callback(env, message):
        assert trace.get_current_span().get_span_context().trace_id == 100
        raise ValueError("application failed")

    with trace.use_span(parent(200)):
        with pytest.raises(ValueError, match="application failed"):
            await InstrumentedExtension("test")._run_with_message_context(
                Env(), data, callback
            )
        assert trace.get_current_span().get_span_context().trace_id == 200
