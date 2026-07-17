#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""In-memory stand-in for redis.asyncio used by the tts2 cache tests.

Implements only the commands TTSRedisCache uses (hgetall/hset/expire/aclose),
with redis-py semantics: hgetall returns {} for a missing key and bytes
keys/values for an existing one.
"""


class FakeRedisClient:
    def __init__(self):
        self.store: dict[str, dict[bytes, bytes]] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False

    def _check(self):
        if self.fail:
            raise ConnectionError("fake redis is down")

    async def hgetall(self, key: str) -> dict[bytes, bytes]:
        self._check()
        return dict(self.store.get(key, {}))

    async def hset(self, key: str, mapping: dict) -> int:
        self._check()
        encoded = {
            (k.encode() if isinstance(k, str) else k): (
                v.encode() if isinstance(v, str) else v
            )
            for k, v in mapping.items()
        }
        self.store.setdefault(key, {}).update(encoded)
        return len(encoded)

    async def expire(self, key: str, ttl: int) -> bool:
        self._check()
        self.ttls[key] = ttl
        return True

    async def aclose(self) -> None:
        pass
