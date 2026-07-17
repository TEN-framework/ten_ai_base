#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""TTS2 base-extension cache behavior tests.

A fake vendor extension (subclass of AsyncTTS2BaseExtension) is driven through
the public on_data boundary with real TEN Data messages. Redis is an in-memory
fake by default; the tests marked `external` run the same flows against a real
Redis instance (set TTS_CACHE_TEST_REDIS, e.g. redis://127.0.0.1:6379/0).
"""

import asyncio
import hashlib
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from ten_ai_base.message import TTSAudioEndReason
from ten_ai_base.struct import TTSFlush, TTSTextInput, TTSTextResult, TTSWord
from ten_ai_base.tts2 import AsyncTTS2BaseExtension
from ten_ai_base.tts2_cache import TTS2CacheConfig, TTSRedisCache
from ten_runtime import Data

from fake_redis import FakeRedisClient

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 1 * 2


def audio_for_text(text: str, duration_ms: int = 200) -> bytes:
    """Deterministic pseudo-PCM derived from the text."""
    pattern = hashlib.sha256(text.encode("utf-8")).digest()
    size = int(BYTES_PER_SECOND * duration_ms / 1000)
    size -= size % 2
    return (pattern * (size // len(pattern) + 1))[:size]


class FakeTTSExtension(AsyncTTS2BaseExtension):
    """Minimal vendor extension with a deterministic synthesizer.

    NOTE: the native AsyncExtension.__new__ only accepts the name argument,
    so per-test knobs (end_reason) are plain attributes set after creation.
    """

    def __init__(self, name: str = "fake_tts"):
        super().__init__(name)
        self.end_reason = TTSAudioEndReason.REQUEST_END
        self.vendor_calls = 0
        self._texts: dict[str, list[str]] = {}

    def vendor(self) -> str:
        return "fake_vendor"

    def synthesize_audio_sample_rate(self) -> int:
        return SAMPLE_RATE

    async def request_tts(self, t: TTSTextInput) -> None:
        self.vendor_calls += 1
        self._texts.setdefault(t.request_id, []).append(t.text)
        if not t.text_input_end:
            return

        full_text = "".join(self._texts.pop(t.request_id))
        audio = audio_for_text(full_text)
        duration_ms = int(len(audio) * 1000 / BYTES_PER_SECOND)
        base_ms = int(time.time() * 1000)  # epoch-based words, like minimax

        await self.send_tts_audio_start(t.request_id)
        await self.send_tts_audio_data(audio)
        words = [
            TTSWord(word=ch, start_ms=base_ms + i * 50, duration_ms=50)
            for i, ch in enumerate(full_text)
        ]
        await self.send_tts_text_result(
            TTSTextResult(
                request_id=t.request_id,
                text=full_text,
                start_ms=base_ms,
                duration_ms=duration_ms,
                words=words,
                text_result_end=True,
            ),
        )
        await self.send_tts_audio_end(
            t.request_id,
            request_event_interval_ms=1,
            request_total_audio_duration_ms=duration_ms,
            reason=self.end_reason,
        )
        await self.finish_request(t.request_id, reason=self.end_reason)


class ExtensionHarness:
    """Runs the base-class input loop with a mocked AsyncTenEnv."""

    def __init__(
        self,
        cache_config: TTS2CacheConfig | None,
        redis_client=None,
        end_reason: TTSAudioEndReason = TTSAudioEndReason.REQUEST_END,
    ):
        self.ext = FakeTTSExtension("fake_tts")
        self.ext.end_reason = end_reason
        self.sent_data: list[tuple[str, dict]] = []
        self.sent_audio: list[bytes] = []
        self.audio_frame_hook = None

        env = MagicMock()
        for level in ("log_debug", "log_info", "log_warn", "log_error"):
            setattr(env, level, MagicMock())
        env.get_property_to_json = AsyncMock(return_value=("{}", None))

        async def _send_data(data: Data):
            payload, _ = data.get_property_to_json("")
            self.sent_data.append((data.get_name(), json.loads(payload or "{}")))

        async def _send_audio_frame(frame):
            buf = frame.lock_buf()
            chunk = bytes(buf)
            frame.unlock_buf(buf)
            self.sent_audio.append(chunk)
            if self.audio_frame_hook:
                await self.audio_frame_hook(len(self.sent_audio))

        env.send_data = AsyncMock(side_effect=_send_data)
        env.send_audio_frame = AsyncMock(side_effect=_send_audio_frame)
        self.env = env

        self.ext.ten_env = env
        if cache_config is not None:
            self.ext._cache_config = cache_config
            self.ext._cache = TTSRedisCache(cache_config, client=redis_client)

    async def __aenter__(self):
        self.ext.loop_task = asyncio.create_task(
            self.ext._process_input_queue(self.env),
        )
        return self

    async def __aexit__(self, *exc):
        self.ext.loop_task.cancel()
        try:
            await self.ext.loop_task
        except asyncio.CancelledError:
            pass

    async def send_text(self, request_id: str, text: str, end: bool):
        t = TTSTextInput(request_id=request_id, text=text, text_input_end=end)
        data = Data.create("tts_text_input")
        data.set_property_from_json("", t.model_dump_json())
        await self.ext.on_data(self.env, data)

    async def send_flush(self, flush_id: str = "f1"):
        data = Data.create("tts_flush")
        data.set_property_from_json(
            "", TTSFlush(flush_id=flush_id).model_dump_json(),
        )
        await self.ext.on_data(self.env, data)

    def data_of(self, name: str) -> list[dict]:
        return [payload for n, payload in self.sent_data if n == name]

    async def wait_for(self, cond, timeout: float = 1.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if cond():
                return True
            await asyncio.sleep(0.005)
        return False

    async def wait_audio_end(self, timeout: float = 1.0) -> dict:
        assert await self.wait_for(
            lambda: self.data_of("tts_audio_end"), timeout,
        ), f"no tts_audio_end observed; data={self.sent_data}"
        return self.data_of("tts_audio_end")[-1]


def cache_config(
    read: bool = False, write: bool = False, **overrides,
) -> TTS2CacheConfig:
    return TTS2CacheConfig(
        enable_cache_read=read,
        enable_cache_write=write,
        cache_redis=overrides.pop("cache_redis", "localhost:6379"),
        **overrides,
    )


# ---------- config loading through the base class ----------


@pytest.mark.asyncio
async def test_load_cache_config_from_property_json():
    ext = FakeTTSExtension("fake_tts")
    env = MagicMock()
    env.log_info = MagicMock()
    env.log_warn = MagicMock()
    env.get_property_to_json = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "params": {"api_key": "secret"},
                    "enable_cache_read": True,
                    "enable_cache_write": True,
                    "cache_redis": "127.0.0.1:6379",
                },
            ),
            None,
        ),
    )
    await ext._load_cache_config(env)
    assert ext._cache is not None
    assert ext._cache_config is not None
    assert ext._cache_config.enable_cache_read


@pytest.mark.asyncio
async def test_load_cache_config_disabled_without_redis_address():
    ext = FakeTTSExtension("fake_tts")
    env = MagicMock()
    env.log_info = MagicMock()
    env.log_warn = MagicMock()
    env.get_property_to_json = AsyncMock(
        return_value=(json.dumps({"enable_cache_read": True}), None),
    )
    await ext._load_cache_config(env)
    assert ext._cache is None


# ---------- write path ----------


@pytest.mark.asyncio
async def test_cache_write_on_successful_request():
    client = FakeRedisClient()
    config = cache_config(write=True, cache_ttl_seconds=60)
    async with ExtensionHarness(config, client) as h:
        await h.send_text("r1", "你好,", end=False)
        await h.send_text("r1", "世界", end=True)
        assert await h.wait_for(lambda: client.store)

    key = next(iter(client.store))
    assert key.startswith("tts_cache:fake_vendor:")
    entry = await TTSRedisCache(config, client=client).get(key)
    assert entry is not None
    assert entry.audio == audio_for_text("你好,世界")
    assert entry.text == "你好,世界"
    assert entry.epoch_based
    # normalized: first word at 0, 50ms apart, one word per character
    assert [w.start_ms for w in entry.words] == [0, 50, 100, 150, 200]
    assert client.ttls[key] == 60


@pytest.mark.asyncio
async def test_no_cache_write_on_interrupted_request():
    client = FakeRedisClient()
    async with ExtensionHarness(
        cache_config(write=True),
        client,
        end_reason=TTSAudioEndReason.INTERRUPTED,
    ) as h:
        await h.send_text("r1", "hello", end=True)
        await h.wait_audio_end()
        await asyncio.sleep(0.02)
    assert client.store == {}


@pytest.mark.asyncio
async def test_cache_write_failure_does_not_break_request():
    client = FakeRedisClient()
    client.fail = True
    async with ExtensionHarness(cache_config(write=True), client) as h:
        await h.send_text("r1", "hello", end=True)
        end = await h.wait_audio_end()
        assert end["reason"] == TTSAudioEndReason.REQUEST_END.value
        assert h.sent_audio  # vendor audio still flowed
    assert client.store == {}


# ---------- read path ----------


async def prime_cache(client: FakeRedisClient, text: str) -> bytes:
    """Run a write-enabled request to populate the cache; returns the audio."""
    async with ExtensionHarness(cache_config(write=True), client) as h:
        await h.send_text("warmup", text, end=True)
        assert await h.wait_for(lambda: client.store)
    return audio_for_text(text)


@pytest.mark.asyncio
async def test_cache_read_hit_serves_without_vendor_request():
    client = FakeRedisClient()
    expected_audio = await prime_cache(client, "你好,世界")

    async with ExtensionHarness(cache_config(read=True), client) as h:
        await h.send_text("r2", "你好,世界", end=True)
        end = await h.wait_audio_end()

        assert h.ext.vendor_calls == 0
        assert end["reason"] == TTSAudioEndReason.REQUEST_END.value
        assert b"".join(h.sent_audio) == expected_audio
        assert h.data_of("tts_audio_start")

        results = h.data_of("tts_text_result")
        assert len(results) == 1
        result = TTSTextResult.model_validate(results[0])
        assert result.text == "你好,世界"
        assert result.text_result_end
        assert result.words is not None
        # epoch-based entry: words rebased onto the current clock, 50ms apart
        assert result.words[0].start_ms > 10**11
        assert (
            result.words[1].start_ms - result.words[0].start_ms == 50
        )

        metrics = h.data_of("metrics")
        assert any(
            m.get("metadata", {}).get("tts_cache_hit") for m in metrics
        )


@pytest.mark.asyncio
async def test_cache_read_miss_falls_back_to_vendor():
    client = FakeRedisClient()
    async with ExtensionHarness(cache_config(read=True, write=True), client) as h:
        await h.send_text("r1", "uncached text", end=True)
        end = await h.wait_audio_end()
        assert h.ext.vendor_calls == 1
        assert end["reason"] == TTSAudioEndReason.REQUEST_END.value
        # the miss was recorded, so the entry is now cached
        assert await h.wait_for(lambda: client.store)


@pytest.mark.asyncio
async def test_multi_chunk_request_bypasses_cache_read():
    client = FakeRedisClient()
    await prime_cache(client, "你好,世界")

    async with ExtensionHarness(cache_config(read=True), client) as h:
        await h.send_text("r2", "你好,", end=False)
        await h.send_text("r2", "世界", end=True)
        await h.wait_audio_end()
        assert h.ext.vendor_calls == 2  # both chunks went to the vendor


@pytest.mark.asyncio
async def test_cache_read_error_degrades_to_vendor():
    client = FakeRedisClient()
    await prime_cache(client, "hello")
    client.fail = True

    async with ExtensionHarness(cache_config(read=True), client) as h:
        await h.send_text("r2", "hello", end=True)
        end = await h.wait_audio_end()
        assert h.ext.vendor_calls == 1
        assert end["reason"] == TTSAudioEndReason.REQUEST_END.value


@pytest.mark.asyncio
async def test_flush_interrupts_cache_replay():
    client = FakeRedisClient()
    # ~2s of audio => many replay chunks
    async with ExtensionHarness(cache_config(write=True), client) as h:
        h.ext._texts.clear()
        await h.send_text("warmup", "long" * 50, end=True)
        assert await h.wait_for(lambda: client.store)

    async with ExtensionHarness(cache_config(read=True), client) as h:
        replay_started = asyncio.Event()
        hold = asyncio.Event()

        async def hook(frame_count: int):
            if frame_count == 1:
                replay_started.set()
                await hold.wait()  # keep the replay in-flight

        h.audio_frame_hook = hook
        await h.send_text("r2", "long" * 50, end=True)
        await asyncio.wait_for(replay_started.wait(), timeout=1.0)
        h.audio_frame_hook = None

        await h.send_flush()
        assert await h.wait_for(
            lambda: any(
                p.get("reason") == TTSAudioEndReason.INTERRUPTED.value
                for p in h.data_of("tts_audio_end")
            ),
        )
        assert h.data_of("tts_flush_end")
        assert h.ext.vendor_calls == 0


# ---------- end-to-end against a real Redis ----------

REAL_REDIS_URL = os.getenv("TTS_CACHE_TEST_REDIS", "")

pytestmark_real = pytest.mark.skipif(
    not REAL_REDIS_URL,
    reason="set TTS_CACHE_TEST_REDIS (e.g. redis://127.0.0.1:6379/0) to run",
)


@pytest.mark.external
@pytestmark_real
@pytest.mark.asyncio
async def test_e2e_write_then_read_with_real_redis():
    text = f"实时语音缓存端到端验证 {os.getpid()} {time.time_ns()}"
    write_config = cache_config(
        write=True, cache_redis=REAL_REDIS_URL, cache_ttl_seconds=120,
    )

    async with ExtensionHarness(write_config, redis_client=None) as h:
        await h.send_text("w1", text, end=True)
        await h.wait_audio_end()
        assert h.ext.vendor_calls == 1
        vendor_audio = b"".join(h.sent_audio)
        # wait until the background write landed
        probe = TTSRedisCache(write_config)
        key = h.ext._build_tts_cache_key(text)
        assert await _poll_entry(probe, key)
        await h.ext._cache.close()
        await probe.close()

    read_config = cache_config(read=True, cache_redis=REAL_REDIS_URL)
    async with ExtensionHarness(read_config, redis_client=None) as h:
        await h.send_text("r1", text, end=True)
        end = await h.wait_audio_end()
        assert h.ext.vendor_calls == 0
        assert end["reason"] == TTSAudioEndReason.REQUEST_END.value
        assert b"".join(h.sent_audio) == vendor_audio
        results = h.data_of("tts_text_result")
        assert len(results) == 1
        result = TTSTextResult.model_validate(results[0])
        assert result.text == text
        assert result.words and len(result.words) == len(text)
        await h.ext._cache.close()


async def _poll_entry(cache: TTSRedisCache, key: str, timeout: float = 1.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if await cache.get(key) is not None:
            return True
        await asyncio.sleep(0.01)
    return False


@pytest.mark.external
@pytestmark_real
@pytest.mark.asyncio
async def test_e2e_real_redis_miss_for_different_params():
    text = f"参数不同不可命中 {time.time_ns()}"
    config_a = cache_config(
        write=True,
        cache_redis=REAL_REDIS_URL,
        cache_key_params={"voice": "a"},
        cache_ttl_seconds=120,
    )
    async with ExtensionHarness(config_a, redis_client=None) as h:
        await h.send_text("w1", text, end=True)
        await h.wait_audio_end()
        probe = TTSRedisCache(config_a)
        assert await _poll_entry(probe, h.ext._build_tts_cache_key(text))
        await probe.close()
        await h.ext._cache.close()

    config_b = cache_config(
        read=True, cache_redis=REAL_REDIS_URL, cache_key_params={"voice": "b"},
    )
    async with ExtensionHarness(config_b, redis_client=None) as h:
        await h.send_text("r1", text, end=True)
        await h.wait_audio_end()
        assert h.ext.vendor_calls == 1  # different voice params -> miss
        await h.ext._cache.close()
