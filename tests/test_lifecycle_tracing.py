# ABOUTME: Verifies ASR and TTS lifecycle span boundaries and status handling.
# ABOUTME: Exercises the public extension lifecycle hooks with an in-memory exporter.

import json
import time

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from ten_ai_base import AsyncASRBaseExtension
from ten_ai_base.message import ModuleError, ModuleMetrics, ModuleType
from ten_ai_base.tts2 import AsyncTTS2BaseExtension
from ten_runtime import AudioFrame, Data


class _Env:
    def __init__(self):
        self.sent = []

    async def send_data(self, data, options=None):
        self.sent.append(data)

    def log_info(self, *args, **kwargs):
        return None

    log_debug = log_warn = log_error = log_info


class _ASR(AsyncASRBaseExtension):
    def __init__(self, name):
        super().__init__(name)
        self.connected = False

    def vendor(self):
        return "test"

    async def start_connection(self):
        return None

    def is_connected(self):
        return self.connected

    async def stop_connection(self):
        self.connected = False

    def input_audio_sample_rate(self):
        return 16000

    async def send_audio(self, frame, session_id):
        return True

    async def finalize(self, session_id):
        return None


class _TTS(AsyncTTS2BaseExtension):
    def vendor(self):
        return "test"

    def synthesize_audio_sample_rate(self):
        return 16000

    async def request_tts(self, text):
        return None


@pytest.fixture
def spans(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer_provider", lambda: provider)
    yield exporter
    provider.shutdown()


@pytest.mark.asyncio
async def test_asr_segments_end_at_finalize_end_without_rotating_connection(spans):
    env = _Env()
    extension = _ASR("asr")
    extension.ten_env = env
    extension.auto_connect = False
    await extension.on_start(env)
    extension.connected = True
    await extension.on_connected()
    before_audio = time.time_ns()
    await extension.on_audio_frame(env, AudioFrame.create("pcm_frame"))

    finalize = Data.create("asr_finalize")
    finalize.set_property_string("finalize_id", "final-1")
    await extension.on_data(env, finalize)
    assert not spans.get_finished_spans()
    await extension.send_asr_finalize_end()

    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == ["asr.segment"]
    first = finished[0]
    assert first.start_time >= before_audio
    assert [event.name for event in first.events] == [
        "asr.finalize",
        "asr.finalize_end",
    ]
    assert first.events[0].attributes["finalize_id"] == "final-1"
    assert first.events[1].attributes["finalize_id"] == "final-1"

    finalize.set_property_string("finalize_id", "final-2")
    await extension.on_data(env, finalize)
    await extension.send_asr_finalize_end()
    second = spans.get_finished_spans()[1]
    assert second.name == "asr.segment"
    assert first.end_time <= second.start_time
    assert [event.name for event in second.events] == [
        "asr.finalize",
        "asr.finalize_end",
    ]
    assert second.events[1].attributes["finalize_id"] == "final-2"

    await extension.on_disconnected(code=1006, message="abnormal")
    await extension.on_stop(env)

    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == [
        "asr.segment",
        "asr.segment",
        "asr.websocket.connection",
        "asr.segment",
        "asr.session",
    ]
    session = finished[-1]
    assert session.attributes["ten.span.long_running"] is True
    connection = finished[2]
    assert connection.status.status_code == trace.StatusCode.ERROR
    assert connection.parent.span_id == session.context.span_id
    assert (
        connection.start_time
        <= first.start_time
        < second.end_time
        <= connection.end_time
    )
    assert first.parent.span_id == second.parent.span_id == session.context.span_id


@pytest.mark.asyncio
async def test_asr_segment_survives_reconnection(spans):
    env = _Env()
    extension = _ASR("asr")
    extension.ten_env = env
    await extension.on_connected()
    await extension.on_audio_frame(env, AudioFrame.create("pcm_frame"))
    await extension.on_disconnected(code=1006)
    assert [span.name for span in spans.get_finished_spans()] == [
        "asr.websocket.connection",
    ]
    await extension.on_connected()
    await extension.send_asr_finalize_end()
    await extension.on_disconnected(code=1000)
    await extension.on_deinit(env)
    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == [
        "asr.websocket.connection",
        "asr.segment",
        "asr.websocket.connection",
        "asr.segment",
        "asr.session",
    ]
    assert finished[0].status.status_code == trace.StatusCode.ERROR
    assert finished[2].status.status_code == trace.StatusCode.UNSET
    assert finished[1].start_time < finished[0].end_time
    assert finished[1].end_time > finished[2].start_time


@pytest.mark.asyncio
async def test_asr_failed_connection_attempt_ends_span(spans):
    class FailingASR(_ASR):
        async def start_connection(self):
            raise ValueError("handshake failed")

    extension = FailingASR("asr")
    extension.ten_env = _Env()
    with pytest.raises(ValueError, match="handshake failed"):
        await extension.start_connection()
    finished = spans.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].name == "asr.websocket.connection"
    assert finished[0].status.status_code == trace.StatusCode.ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["asr", "tts"])
async def test_connection_before_start_is_parented_by_session(spans, kind):
    env = _Env()
    extension = _ASR("asr") if kind == "asr" else _TTS("tts")
    extension.ten_env = env
    await extension.on_connected()
    await extension.on_disconnected(code=1000)
    await extension.on_deinit(env)
    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == [
        f"{kind}.websocket.connection",
        f"{kind}.session",
    ]
    assert finished[0].parent.span_id == finished[1].context.span_id
    assert finished[0].attributes["ten.span.long_running"] is True


@pytest.mark.asyncio
async def test_tts_requests_share_connection_span(spans):
    env = _Env()
    extension = _TTS("tts")
    await extension.on_init(env)
    await extension.on_start(env)
    await extension.on_connecting()
    await extension.on_connected()
    for request_id in ["request-1", "request-2"]:
        data = Data.create("tts_text_input")
        data.set_property_from_json(
            "",
            json.dumps({"request_id": request_id, "text": "hello"}),
        )
        await extension.on_data(env, data)
        await extension.send_tts_audio_end(request_id, 0, 0)
        await extension.finish_request(request_id)
    assert [span.name for span in spans.get_finished_spans()] == [
        "tts.synthesis",
        "tts.synthesis",
    ]
    assert all(
        span.name != "tts.websocket.connection" for span in spans.get_finished_spans()
    )

    await extension.on_disconnected(code=1006, message="abnormal")
    await extension.on_stop(env)
    finished = spans.get_finished_spans()
    connections = [span for span in finished if span.name == "tts.websocket.connection"]
    assert len(connections) == 1
    assert connections[0].parent.span_id == finished[-1].context.span_id
    assert connections[0].start_time <= finished[0].start_time
    assert finished[1].end_time <= connections[0].end_time
    assert finished[-1].attributes["ten.span.long_running"] is True
    assert connections[0].status.status_code == trace.StatusCode.ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [0, 1000, 1006])
async def test_tts_failed_connection_and_reconnect_have_separate_spans(spans, code):
    extension = _TTS("tts")
    await extension.on_init(_Env())
    await extension.on_connecting()
    await extension.on_disconnected(code=code)
    await extension.on_connecting()
    await extension.on_connected()
    await extension.on_disconnected(code=1000)
    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == [
        "tts.websocket.connection",
        "tts.websocket.connection",
    ]
    assert finished[0].context.span_id != finished[1].context.span_id
    assert finished[0].status.status_code == (
        trace.StatusCode.ERROR if code == 1006 else trace.StatusCode.UNSET
    )
    assert finished[1].status.status_code == trace.StatusCode.UNSET


@pytest.mark.asyncio
async def test_tts_disconnect_closes_span_even_if_status_delivery_fails(spans):
    class BrokenEnv(_Env):
        async def send_data(self, data, options=None):
            raise ValueError("transport failed")

    extension = _TTS("tts")
    await extension.on_init(_Env())
    await extension.on_connecting()
    extension.ten_env = BrokenEnv()
    with pytest.raises(ValueError, match="transport failed"):
        await extension.on_disconnected(code=1006)
    finished = spans.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].name == "tts.websocket.connection"
    assert finished[0].status.status_code == trace.StatusCode.ERROR


@pytest.mark.asyncio
async def test_asr_error_and_metrics_become_connection_span_events(spans):
    env = _Env()
    extension = _ASR("asr")
    extension.ten_env = env
    extension.connected = True
    await extension.on_connected()

    await extension.send_asr_error(ModuleError(code=17, message="vendor failed"))
    await extension._send_asr_metrics(
        ModuleMetrics(
            module=ModuleType.ASR,
            vendor="test",
            metrics={"ttfw": 42},
        )
    )
    await extension.on_disconnected(code=1006, message="abnormal")

    connection = spans.get_finished_spans()[0]
    assert [event.name for event in connection.events] == [
        "asr.error",
        "asr.metrics",
    ]
    assert connection.events[0].attributes["code"] == 17
    assert connection.events[0].attributes["message"] == "vendor failed"
    assert json.loads(connection.events[1].attributes["metrics"]) == {"ttfw": 42}


@pytest.mark.asyncio
async def test_asr_segment_receives_operation_events_before_finalize_end(spans):
    env = _Env()
    extension = _ASR("asr")
    extension.ten_env = env
    await extension.on_connected()
    await extension.on_audio_frame(env, AudioFrame.create("pcm_frame"))
    await extension.send_asr_error(ModuleError(code=17, message="vendor failed"))
    await extension.send_vendor_metrics({"latency": 42})
    await extension.send_asr_finalize_end()
    segment = spans.get_finished_spans()[0]
    assert segment.name == "asr.segment"
    assert [event.name for event in segment.events] == [
        "asr.error",
        "asr.metrics",
        "asr.finalize_end",
    ]
    assert json.loads(segment.events[1].attributes["metrics"]) == {
        "vendor_metrics": {"latency": 42},
    }
    await extension.on_deinit(env)


@pytest.mark.asyncio
async def test_asr_finalize_end_delivery_failure_keeps_segment_open(spans):
    class BrokenEnv(_Env):
        async def send_data(self, data, options=None):
            raise ValueError("transport failed")

    extension = _ASR("asr")
    extension.ten_env = BrokenEnv()
    await extension.on_audio_frame(extension.ten_env, AudioFrame.create("pcm_frame"))
    with pytest.raises(ValueError, match="transport failed"):
        await extension.send_asr_finalize_end()
    assert not spans.get_finished_spans()
    extension.ten_env = _Env()
    await extension.send_asr_finalize_end()
    assert [span.name for span in spans.get_finished_spans()] == ["asr.segment"]
    await extension.on_deinit(extension.ten_env)


@pytest.mark.asyncio
async def test_tts_error_and_metrics_become_request_span_events(spans):
    env = _Env()
    extension = _TTS("tts")
    await extension.on_init(env)
    extension._begin_request_trace("request-1")

    await extension.send_tts_error(
        "request-1",
        ModuleError(code=17, message="vendor failed"),
    )
    await extension.send_metrics(
        ModuleMetrics(
            module=ModuleType.TTS,
            vendor="test",
            metrics={"ttfb": 42},
        ),
        "request-1",
    )
    await extension.send_tts_audio_end("request-1", 0, 0)
    await extension.finish_request("request-1")

    request = spans.get_finished_spans()[0]
    assert [event.name for event in request.events] == [
        "tts.request.received",
        "tts.error",
        "tts.metrics",
        "tts.result.end",
    ]
    assert request.events[1].attributes["code"] == 17
    assert json.loads(request.events[2].attributes["metrics"]) == {"ttfb": 42}
