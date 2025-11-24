#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import asyncio
from typing import Optional, Protocol


class Logger(Protocol):
    """Logger protocol for type hints."""

    def log_debug(self, msg: str) -> None: ...
    def log_error(self, msg: str) -> None: ...


class AudioBufferManager:
    """
    A minimal async audio buffer providing a producer-consumer queue:
    - Producer appends bytes via async `push_audio`
    - Consumer reads fixed-size bytes via async `pull_chunk` (size = threshold)

    Close behavior:
    - After `close()`, a waiting `pull_chunk` will return the remaining bytes if
      they are less than the threshold; if no bytes remain, it returns b"" (EOF).
    """

    def __init__(
        self,
        threshold: int = 1280,
        max_buffer_size: int = 1024 * 1024 * 100,  # 100 MB default
        logger: Optional[Logger] = None,
    ):
        if not isinstance(threshold, int) or threshold <= 0:
            raise ValueError("threshold must be a positive integer")
        if not isinstance(max_buffer_size, int) or max_buffer_size <= 0:
            raise ValueError("max_buffer_size must be a positive integer")

        self._buffer = bytearray()
        self._threshold = threshold
        self._max_buffer_size = max_buffer_size
        self.logger = logger

        # Concurrency control
        self._cond = asyncio.Condition()
        self._closed = False

        if self.logger:
            self.logger.log_debug(
                f"AudioBufferManager initialized. threshold={self._threshold}, "
                f"max_buffer_size={self._max_buffer_size}"
            )

    # -------------------- Producer API --------------------
    async def push_audio(self, data: bytes | bytearray) -> None:
        """
        Append audio bytes into the buffer asynchronously.

        Raises:
            ValueError: If adding data would exceed max_buffer_size
        """
        if not data:  # Skip empty data to avoid spurious wakeups
            return

        async with self._cond:
            if len(self._buffer) + len(data) > self._max_buffer_size:
                if self.logger:
                    self.logger.log_error(
                        f"Buffer overflow: current size {len(self._buffer)}, "
                        f"attempting to add {len(data)}, "
                        f"max size {self._max_buffer_size}"
                    )
                raise ValueError(
                    f"Buffer overflow: current size {len(self._buffer)}, "
                    f"attempting to add {len(data)}, "
                    f"max size {self._max_buffer_size}"
                )

            self._buffer.extend(data)
            if not self._closed:
                self._cond.notify()  # Use notify() for single consumer

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

            # Buffer size >= threshold
            chunk = bytes(self._buffer[: self._threshold])
            del self._buffer[: self._threshold]
            return chunk

    # -------------------- Utility API --------------------

    async def close(self) -> None:
        """Mark as closed and wake up any waiting consumers."""
        async with self._cond:
            self._closed = True
            if self.logger:
                self.logger.log_debug("AudioBufferManager closed")
            self._cond.notify()  # Use notify() for single consumer
