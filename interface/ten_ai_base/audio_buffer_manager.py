#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import asyncio


class AudioBufferManager:
    """
    A minimal async audio buffer providing a producer-consumer queue:
    - Producer appends bytes via async `push_audio`
    - Consumer reads fixed-size bytes via async `pull_chunk` (size = threshold)

    Close behavior:
    - After `close()`, a waiting `pull_chunk` will return the remaining bytes if
      they are less than the threshold; if no bytes remain, it returns b"" (EOF).
    """

    def __init__(self, threshold: int = 1280, logger=None):
        if not isinstance(threshold, int) or threshold <= 0:
            raise ValueError("threshold must be a positive integer")

        self._buffer = bytearray()
        self._threshold = threshold
        self.logger = logger

        # Concurrency control
        self._cond = asyncio.Condition()
        self._closed = False

        if self.logger:
            self.logger.log_debug(
                f"AudioBufferManager initialized. threshold={self._threshold}"
            )

    # -------------------- Producer API --------------------
    async def push_audio(self, data: bytes) -> None:
        """Append audio bytes into the buffer asynchronously."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("data must be bytes or bytearray")
        async with self._cond:
            self._buffer.extend(data)
            if not self._closed:
                self._cond.notify_all()

    # -------------------- Consumer API --------------------
    async def pull_chunk(self) -> bytes:
        """
        Retrieve one chunk asynchronously:
        - If buffer size >= threshold, return exactly `threshold` bytes.
        - If closed and remaining bytes < threshold, return the remaining bytes
          (may be empty to indicate EOF).
        """
        async with self._cond:
            await self._cond.wait_for(
                lambda: len(self._buffer) >= self._threshold or self._closed
            )

            if self._closed:
                if self._buffer:
                    remaining = bytes(self._buffer)
                    self._buffer.clear()
                    if self.logger:
                        self.logger.log_debug(
                            f"pull_chunk: return tail {len(remaining)} bytes on close"
                        )
                    return remaining
                if self.logger:
                    self.logger.log_debug("pull_chunk: EOF (empty on close)")
                return b""

            if len(self._buffer) >= self._threshold:
                chunk = bytes(self._buffer[: self._threshold])
                del self._buffer[: self._threshold]
                return chunk

            return b""

    # -------------------- Utility API --------------------

    def close(self) -> None:
        """Mark as closed and wake up any waiting consumers."""

        # Non-async method for convenience in any context
        async def _close():
            async with self._cond:
                self._closed = True
                if self.logger:
                    self.logger.log_debug("AudioBufferManager closed")
                self._cond.notify_all()

        # If inside an event loop, schedule it; otherwise run a new loop to avoid blocking
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_close())
        except RuntimeError:
            asyncio.run(_close())
