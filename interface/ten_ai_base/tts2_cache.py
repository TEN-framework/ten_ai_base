#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""Redis-backed cache for TTS2 results (audio + word-level subtitles).

Used by AsyncTTS2BaseExtension (tts2.py). The cache key encodes
vendor / hash(params) / hash(content); the value stores the raw PCM audio and
the per-word subtitle timeline so a repeated request can be replayed without
issuing a real vendor TTS request.
"""

import hashlib
import json
import time
from typing import Any

from pydantic import BaseModel, Field

from .struct import TTSTextResult, TTSWord

CACHE_ENTRY_VERSION = 1

# Word start_ms values above this are treated as absolute epoch-based
# timestamps (vendors like minimax use wall-clock ms); smaller values are
# treated as stream-relative offsets.
_EPOCH_MS_THRESHOLD = 10**11


class TTS2CacheConfig(BaseModel):
    """Cache-related switches read from the extension property JSON.

    These are top-level extension properties so any TTS2 extension can enable
    caching purely via graph config, with no vendor extension code changes.
    """

    enable_cache_read: bool = False
    enable_cache_write: bool = False
    cache_redis: str = ""
    cache_key_prefix: str = "tts_cache"
    cache_key_params: dict[str, Any] = Field(default_factory=dict)
    cache_ttl_seconds: int = 86400

    @property
    def cache_enabled(self) -> bool:
        return bool(self.cache_redis) and (
            self.enable_cache_read or self.enable_cache_write
        )

    def redis_url(self) -> str:
        if "://" in self.cache_redis:
            return self.cache_redis
        return f"redis://{self.cache_redis}"


def _hash32(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:32]


def build_tts_cache_key(
    prefix: str, vendor: str, params: dict[str, Any], text: str,
) -> str:
    """Encode the cache key as {prefix}:{vendor}:{hash(params)}:{hash(content)}.

    Params are serialized as canonical JSON (sorted keys, compact separators)
    so the hash is independent of dict insertion order.
    """
    params_json = json.dumps(
        params, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return f"{prefix}:{vendor}:{_hash32(params_json)}:{_hash32(text)}"


class TTSCacheEntry(BaseModel):
    """A complete cached TTS result.

    Word timestamps are stored relative to the first word; `epoch_based`
    records whether the original stream used absolute wall-clock timestamps,
    so replay can rebase onto the current clock only when needed.
    """

    audio: bytes
    words: list[TTSWord] = Field(default_factory=list)
    text: str = ""
    sample_rate: int = 0
    channels: int = 1
    sample_width: int = 2
    epoch_based: bool = False
    has_text_result: bool = False
    duration_ms: int = 0

    def to_redis_mapping(self) -> dict[bytes | str, bytes | str]:
        meta = {
            "version": CACHE_ENTRY_VERSION,
            "text": self.text,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width": self.sample_width,
            "epoch_based": self.epoch_based,
            "has_text_result": self.has_text_result,
            "duration_ms": self.duration_ms,
        }
        words = [w.model_dump() for w in self.words]
        return {
            "audio": self.audio,
            "words": json.dumps(words, ensure_ascii=False),
            "meta": json.dumps(meta, ensure_ascii=False),
        }

    @classmethod
    def from_redis_mapping(cls, mapping: dict[bytes, bytes]) -> "TTSCacheEntry | None":
        """Deserialize a Redis hash; returns None for missing/invalid data."""
        audio = mapping.get(b"audio")
        raw_meta = mapping.get(b"meta")
        raw_words = mapping.get(b"words")
        if not audio or raw_meta is None:
            return None
        try:
            meta = json.loads(raw_meta)
            if meta.get("version") != CACHE_ENTRY_VERSION:
                return None
            words = [TTSWord.model_validate(w) for w in json.loads(raw_words or b"[]")]
            return cls(
                audio=audio,
                words=words,
                text=meta.get("text", ""),
                sample_rate=int(meta.get("sample_rate", 0)),
                channels=int(meta.get("channels", 1)),
                sample_width=int(meta.get("sample_width", 2)),
                epoch_based=bool(meta.get("epoch_based", False)),
                has_text_result=bool(meta.get("has_text_result", False)),
                duration_ms=int(meta.get("duration_ms", 0)),
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def rebased_words(self, base_ms: int) -> list[TTSWord]:
        return [
            TTSWord(
                word=w.word,
                start_ms=w.start_ms + base_ms,
                duration_ms=w.duration_ms,
            )
            for w in self.words
        ]

    def replay_base_ms(self) -> int:
        """Base timestamp for replayed words.

        Epoch-based vendors stamp words with wall-clock ms, so replay rebases
        onto "now"; relative vendors keep offsets starting at 0.
        """
        if self.epoch_based:
            return int(time.time() * 1000)
        return 0


class TTSCacheRecorder:
    """Accumulates one request's text, audio and words for a cache write."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.text_parts: list[str] = []
        self.audio = bytearray()
        self.words: list[TTSWord] = []
        self.has_text_result = False
        self.text_input_end = False

    def add_text(self, text: str, text_input_end: bool) -> None:
        if text:
            self.text_parts.append(text)
        if text_input_end:
            self.text_input_end = True

    def add_audio(self, data: bytes) -> None:
        if data:
            self.audio.extend(data)

    def add_text_result(self, t: TTSTextResult) -> None:
        self.has_text_result = True
        if t.words:
            self.words.extend(t.words)

    def full_text(self) -> str:
        return "".join(self.text_parts)

    def to_entry(
        self, sample_rate: int, channels: int, sample_width: int,
    ) -> TTSCacheEntry | None:
        """Build a cache entry; None when there is nothing worth caching."""
        if not self.audio or not self.text_input_end:
            return None

        epoch_based = False
        normalized: list[TTSWord] = []
        if self.words:
            base = self.words[0].start_ms
            epoch_based = base > _EPOCH_MS_THRESHOLD
            if not epoch_based:
                base = 0
            normalized = [
                TTSWord(
                    word=w.word,
                    start_ms=max(w.start_ms - base, 0),
                    duration_ms=w.duration_ms,
                )
                for w in self.words
            ]

        bytes_per_second = sample_rate * channels * sample_width
        duration_ms = (
            int(len(self.audio) * 1000 / bytes_per_second)
            if bytes_per_second > 0
            else 0
        )
        return TTSCacheEntry(
            audio=bytes(self.audio),
            words=normalized,
            text=self.full_text(),
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
            epoch_based=epoch_based,
            has_text_result=self.has_text_result,
            duration_ms=duration_ms,
        )


class TTSRedisCache:
    """Thin async Redis accessor for TTS cache entries.

    The redis package is imported lazily so deployments that never enable the
    cache do not need it installed. IO errors propagate to the caller, which
    treats them as cache misses / skipped writes.
    """

    def __init__(self, config: TTS2CacheConfig, client: Any = None):
        self._config = config
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(
                self._config.redis_url(),
                decode_responses=False,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )
        return self._client

    async def get(self, key: str) -> TTSCacheEntry | None:
        client = self._ensure_client()
        mapping = await client.hgetall(key)
        if not mapping:
            return None
        return TTSCacheEntry.from_redis_mapping(mapping)

    async def put(self, key: str, entry: TTSCacheEntry) -> None:
        client = self._ensure_client()
        await client.hset(key, mapping=entry.to_redis_mapping())
        if self._config.cache_ttl_seconds > 0:
            await client.expire(key, self._config.cache_ttl_seconds)

    async def close(self) -> None:
        if self._client is not None:
            client = self._client
            self._client = None
            await client.aclose()
