"""Verify test async tts2 http timing TTFB at the public provider boundary."""

import pytest

import json
import threading
import time
import asyncio
import httpx
from types import SimpleNamespace
from unittest.mock import patch

from ten_runtime import Data, ExtensionTester, TenError, TenErrorCode


class TimingTester(ExtensionTester):
    def __init__(self):
        super().__init__()
        self.reported = []
        self.audio = False
        self.audio_end = False
        self.timer = None

    def on_start(self, env):
        self.timer = threading.Timer(
            0.8,
            lambda: env.stop_test(
                TenError.create(TenErrorCode.ErrorCodeGeneric, "Missing audio or TTFB"),
            ),
        )
        self.timer.start()
        data = Data.create("tts_text_input")
        data.set_property_from_json(
            "",
            json.dumps(
                {
                    "request_id": "sdk-first-audio",
                    "text": "Hello.",
                    "text_input_end": True,
                    "metadata": {"turn_id": 1},
                }
            ),
        )
        env.send_data(data)
        env.on_start_done()

    def on_data(self, env, data):
        raw, _ = data.get_property_to_json("")
        payload = json.loads(raw)
        if data.get_name() == "error":
            env.stop_test(
                TenError.create(TenErrorCode.ErrorCodeGeneric, "Provider error")
            )
        if data.get_name() == "metrics" and "ttfb" in payload.get("metrics", {}):
            self.reported.append(payload["metrics"]["ttfb"])
            self.complete(env)
        if data.get_name() == "tts_audio_end":
            self.audio_end = True
            self.complete(env)

    def on_audio_frame(self, env, frame):
        if frame.get_buf():
            self.audio = True
            self.complete(env)

    def complete(self, env):
        if self.audio and self.reported and self.audio_end:
            self.timer.cancel()
            env.stop_test()


@pytest.mark.parametrize(
    "response_format,audio_start_delay_ms",
    [("raw", 0), ("json", 0), ("raw", 80)],
)
def test_ttfb_excludes_tail_audio_and_audio_start_delivery_wait(
    response_format, audio_start_delay_ms
):
    times = {}

    class AudioStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if response_format == "json":
                yield b'{"status":"ready",'
            if not audio_start_delay_ms:
                await asyncio.sleep(0.03)
            times["received"] = time.monotonic_ns()
            if response_format == "json":
                yield b'"audio":"AQA="}'
                return
            yield b"\x01\x00" * 1600
            await asyncio.sleep(0.1)
            yield b"\x02\x00" * 1600

    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            times["sent"] = time.monotonic_ns()
            if not audio_start_delay_ms:
                await asyncio.sleep(0.15)
            trace = request.extensions.get("trace")
            if trace:
                await trace("http11.send_request_body.started", {})
            return httpx.Response(
                200,
                headers={
                    "content-type": (
                        "application/json" if response_format == "json" else "audio/pcm"
                    )
                },
                stream=AudioStream(),
            )

    real_client = httpx.AsyncClient
    with patch(
        "ten_packages.extension.test_async_tts2_http_timing.extension.httpx.AsyncClient",
        side_effect=lambda **kwargs: real_client(transport=Transport()),
    ):
        tester = TimingTester()
        try:
            tester.set_test_mode_single(
                "test_async_tts2_http_timing",
                json.dumps(
                    {
                        "url": "https://mock.example/tts",
                        "response_format": response_format,
                        "audio_start_delay_ms": audio_start_delay_ms,
                    }
                ),
            )
            error = tester.run()
            assert error is None, error.error_message()
            expected = (times["received"] - times["sent"]) / 1_000_000
            assert len(tester.reported) == 1
            assert abs(tester.reported[0] - expected) <= 5, (tester.reported, expected)
            if audio_start_delay_ms:
                assert tester.reported[0] < 50
        finally:
            if tester.timer:
                tester.timer.cancel()


pytestmark = pytest.mark.api
