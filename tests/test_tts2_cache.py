#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""Unit tests for the tts2 Redis cache module (no extension, no real Redis)."""

import time

import pytest

from ten_ai_base.struct import TTSTextResult, TTSWord
from ten_ai_base.tts2_cache import (
    CACHE_ENTRY_VERSION,
    TTS2CacheConfig,
    TTSCacheEntry,
    TTSCacheRecorder,
    TTSRedisCache,
    build_tts_cache_key,
)

from fake_redis import FakeRedisClient


# ---------- key encoding ----------


def test_cache_key_shape_and_determinism():
    key1 = build_tts_cache_key("tts_cache", "minimax", {"voice": "a"}, "你好")
    key2 = build_tts_cache_key("tts_cache", "minimax", {"voice": "a"}, "你好")
    assert key1 == key2
    prefix, vendor, params_hash, content_hash = key1.split(":")
    assert prefix == "tts_cache"
    assert vendor == "minimax"
    assert len(params_hash) == 32
    assert len(content_hash) == 32


def test_cache_key_params_order_independent():
    key1 = build_tts_cache_key("p", "v", {"a": 1, "b": 2}, "t")
    key2 = build_tts_cache_key("p", "v", {"b": 2, "a": 1}, "t")
    assert key1 == key2


def test_cache_key_sensitive_to_vendor_params_and_content():
    base = build_tts_cache_key("p", "v", {"voice": "a"}, "hello")
    assert build_tts_cache_key("p", "v2", {"voice": "a"}, "hello") != base
    assert build_tts_cache_key("p", "v", {"voice": "b"}, "hello") != base
    assert build_tts_cache_key("p", "v", {"voice": "a"}, "hello!") != base


# ---------- config ----------


def test_cache_config_defaults_disabled():
    config = TTS2CacheConfig()
    assert not config.enable_cache_read
    assert not config.enable_cache_write
    assert not config.cache_enabled


def test_cache_config_requires_redis_address():
    config = TTS2CacheConfig(enable_cache_read=True)
    assert not config.cache_enabled
    config = TTS2CacheConfig(enable_cache_read=True, cache_redis="localhost:6379")
    assert config.cache_enabled


def test_cache_config_redis_url_forms():
    assert (
        TTS2CacheConfig(cache_redis="localhost:6379").redis_url()
        == "redis://localhost:6379"
    )
    assert (
        TTS2CacheConfig(cache_redis="redis://:pw@host:1/2").redis_url()
        == "redis://:pw@host:1/2"
    )


def test_cache_config_parses_from_extension_property_json():
    config = TTS2CacheConfig.model_validate_json(
        '{"params": {"api_key": "x"}, "enable_cache_read": true, '
        '"cache_redis": "127.0.0.1:6379", "cache_key_params": {"voice": "f1"}}',
    )
    assert config.enable_cache_read
    assert not config.enable_cache_write
    assert config.cache_key_params == {"voice": "f1"}
    assert config.cache_enabled


# ---------- recorder / normalization ----------


def _recorded_result(request_id: str, words: list[TTSWord]) -> TTSTextResult:
    return TTSTextResult(
        request_id=request_id,
        text="".join(w.word for w in words),
        start_ms=words[0].start_ms if words else 0,
        duration_ms=sum(w.duration_ms for w in words),
        words=words,
        text_result_end=True,
    )


def test_recorder_requires_audio_and_input_end():
    recorder = TTSCacheRecorder("r1")
    recorder.add_text("hi", text_input_end=True)
    assert recorder.to_entry(16000, 1, 2) is None  # no audio

    recorder = TTSCacheRecorder("r2")
    recorder.add_text("hi", text_input_end=False)
    recorder.add_audio(b"\x00\x01" * 100)
    assert recorder.to_entry(16000, 1, 2) is None  # no text_input_end


def test_recorder_normalizes_epoch_based_words():
    now_ms = int(time.time() * 1000)
    recorder = TTSCacheRecorder("r1")
    recorder.add_text("你好", text_input_end=True)
    recorder.add_audio(b"\x00\x01" * 1600)
    recorder.add_text_result(
        _recorded_result(
            "r1",
            [
                TTSWord(word="你", start_ms=now_ms, duration_ms=100),
                TTSWord(word="好", start_ms=now_ms + 120, duration_ms=100),
            ],
        ),
    )
    entry = recorder.to_entry(16000, 1, 2)
    assert entry is not None
    assert entry.epoch_based
    assert [w.start_ms for w in entry.words] == [0, 120]
    assert entry.duration_ms == 100  # 3200 bytes / 32000 Bps = 100ms


def test_recorder_keeps_relative_words_as_is():
    recorder = TTSCacheRecorder("r1")
    recorder.add_text("hey", text_input_end=True)
    recorder.add_audio(b"\x00\x01" * 100)
    recorder.add_text_result(
        _recorded_result(
            "r1",
            [
                TTSWord(word="hey", start_ms=40, duration_ms=200),
            ],
        ),
    )
    entry = recorder.to_entry(16000, 1, 2)
    assert entry is not None
    assert not entry.epoch_based
    assert [w.start_ms for w in entry.words] == [40]


def test_recorder_accumulates_multi_chunk_text():
    recorder = TTSCacheRecorder("r1")
    recorder.add_text("你好,", text_input_end=False)
    recorder.add_text("世界", text_input_end=True)
    recorder.add_audio(b"\x00\x01" * 10)
    entry = recorder.to_entry(16000, 1, 2)
    assert entry is not None
    assert entry.text == "你好,世界"


# ---------- entry serialization ----------


def _sample_entry() -> TTSCacheEntry:
    return TTSCacheEntry(
        audio=b"\x01\x02\x03\x04",
        words=[TTSWord(word="hi", start_ms=0, duration_ms=150)],
        text="hi",
        sample_rate=16000,
        channels=1,
        sample_width=2,
        epoch_based=True,
        has_text_result=True,
        duration_ms=150,
    )


def test_entry_redis_roundtrip():
    entry = _sample_entry()
    mapping = entry.to_redis_mapping()
    raw = {
        b"audio": mapping["audio"],
        b"words": mapping["words"].encode(),
        b"meta": mapping["meta"].encode(),
    }
    restored = TTSCacheEntry.from_redis_mapping(raw)
    assert restored is not None
    assert restored.audio == entry.audio
    assert restored.words == entry.words
    assert restored.text == entry.text
    assert restored.sample_rate == entry.sample_rate
    assert restored.epoch_based == entry.epoch_based
    assert restored.has_text_result == entry.has_text_result
    assert restored.duration_ms == entry.duration_ms


def test_entry_rejects_missing_or_corrupt_fields():
    assert TTSCacheEntry.from_redis_mapping({}) is None
    assert (
        TTSCacheEntry.from_redis_mapping({b"audio": b"", b"meta": b"{}"}) is None
    )
    assert (
        TTSCacheEntry.from_redis_mapping({b"audio": b"x", b"meta": b"not-json"})
        is None
    )
    wrong_version = (
        '{"version": %d, "sample_rate": 16000}' % (CACHE_ENTRY_VERSION + 1)
    ).encode()
    assert (
        TTSCacheEntry.from_redis_mapping({b"audio": b"x", b"meta": wrong_version})
        is None
    )


def test_entry_replay_rebase():
    entry = _sample_entry()
    base = entry.replay_base_ms()
    assert base > 10**11  # epoch-based entries rebase onto the current clock
    rebased = entry.rebased_words(base)
    assert rebased[0].start_ms == base

    entry.epoch_based = False
    assert entry.replay_base_ms() == 0
    assert entry.rebased_words(0)[0].start_ms == 0


# ---------- TTSRedisCache against fake client ----------


@pytest.mark.asyncio
async def test_redis_cache_put_get_roundtrip_and_ttl():
    config = TTS2CacheConfig(
        enable_cache_write=True,
        cache_redis="localhost:6379",
        cache_ttl_seconds=123,
    )
    client = FakeRedisClient()
    cache = TTSRedisCache(config, client=client)
    entry = _sample_entry()

    await cache.put("k1", entry)
    assert client.ttls["k1"] == 123

    restored = await cache.get("k1")
    assert restored is not None
    assert restored.audio == entry.audio
    assert restored.words == entry.words

    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_redis_cache_no_ttl_when_zero():
    config = TTS2CacheConfig(
        enable_cache_write=True, cache_redis="localhost:6379", cache_ttl_seconds=0,
    )
    client = FakeRedisClient()
    cache = TTSRedisCache(config, client=client)
    await cache.put("k1", _sample_entry())
    assert "k1" not in client.ttls
