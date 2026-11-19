# ABOUTME: Verifies ASR and TTS lifecycle span boundaries and status handling.
# ABOUTME: Exercises the public extension lifecycle hooks with an in-memory exporter.

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from ten_ai_base import AsyncASRBaseExtension
from ten_ai_base.tts2 import AsyncTTS2BaseExtension
from ten_runtime import Data


class _Env:
    async def send_data(self, data, options=None):
        return None

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
async def test_asr_session_and_connection_spans_rotate_at_finalize(spans):
    env = _Env()
    extension = _ASR("asr")
    extension.ten_env = env
    extension.auto_connect = False
    await extension.on_start(env)
    extension.connected = True
    await extension.on_connected()

    finalize = Data.create("asr_finalize")
    finalize.set_property_string("finalize_id", "final-1")
    await extension.on_data(env, finalize)

    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == ["asr.websocket.connection"]
    assert extension._otel_connection_span is not None

    await extension.on_disconnected(code=1006, message="abnormal")
    await extension.on_stop(env)

    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == [
        "asr.websocket.connection",
        "asr.websocket.connection",
        "asr.session",
    ]
    session = finished[-1]
    assert session.attributes["ten.span.long_running"] is True
    assert finished[1].status.status_code == trace.StatusCode.ERROR


@pytest.mark.asyncio
async def test_tts_request_completion_rotates_connection_span(spans):
    env = _Env()
    extension = _TTS("tts")
    await extension.on_init(env)
    await extension.on_start(env)
    await extension.on_connecting()
    await extension.on_connected()
    extension._begin_request_trace("request-1")

    await extension.finish_request("request-1")

    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == [
        "tts.request",
        "tts.websocket.connection",
    ]
    assert extension._otel_connection_span is not None

    await extension.on_disconnected(code=1006, message="abnormal")
    await extension.on_stop(env)
    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == [
        "tts.request",
        "tts.websocket.connection",
        "tts.websocket.connection",
        "tts.session",
    ]
    assert finished[-1].attributes["ten.span.long_running"] is True
    assert finished[2].status.status_code == trace.StatusCode.ERROR

