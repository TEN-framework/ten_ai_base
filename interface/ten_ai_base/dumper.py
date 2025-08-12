#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""Simple async dumper for writing bytes to session-rotated files."""

import asyncio
from pathlib import Path
import aiofiles


class Dumper:
    """Asynchronous dumper that writes to files with session-based names."""

    def __init__(
        self,
        base_dump_file_path: str,
        session_name: str | None = None,
        delimiter: str = "_",
    ):
        self.base_dump_file_path: str = base_dump_file_path
        self.session_name: str | None = session_name
        self.delimiter: str = delimiter
        self._file: aiofiles.threadpool.binary.AsyncBufferedIOBase | None = None
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def dump_file_path(self) -> str:
        base_path = Path(self.base_dump_file_path)
        if not self.session_name:
            return str(base_path)

        stem = base_path.stem
        suffix = base_path.suffix
        new_name = f"{stem}{self.delimiter}{self.session_name}{suffix}"
        return str(base_path.with_name(new_name))

    async def close(self) -> None:
        async with self._lock:
            if self._file:
                await self._file.close()
                self._file = None

    async def update_session(self) -> None:
        """Rotate to a new session file and open it if needed.

        The session name is generated from current event-loop time
        to ensure uniqueness and ordering. If the generated name equals
        the current one, this function is a no-op.
        """
        async with self._lock:
            # Generate a new session name based on timestamp
            current_time = asyncio.get_event_loop().time()
            new_session_name = f"{current_time:.6f}"

            if new_session_name == self.session_name and self._file is not None:
                # Already opened on the same session
                return

            # Close previous file if any
            if self._file is not None:
                await self._file.close()
                self._file = None

            # Update session and open the new file
            self.session_name = new_session_name
            Path(self.dump_file_path).parent.mkdir(parents=True, exist_ok=True)
            self._file = await aiofiles.open(self.dump_file_path, mode="wb")

    async def push_bytes(self, data: bytes) -> int:
        async with self._lock:
            if not self._file:
                raise RuntimeError(
                    f"Dumper for {self.dump_file_path} is not opened. Call update_session() first."
                )
            return await self._file.write(data)
