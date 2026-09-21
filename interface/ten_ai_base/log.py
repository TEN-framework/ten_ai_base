#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from typing import Protocol

from .const import LOG_CATEGORY_TRANSCRIPTS


class _DebugLogger(Protocol):
    def log_debug(self, message: str, category: str | None = None) -> None: ...


def log_transcript_debug(
    logger: _DebugLogger,
    message: str,
    *,
    opt_out: bool,
) -> None:
    """Log transcript details under the filtered category for opt-out sessions."""
    logger.log_debug(
        message,
        category=LOG_CATEGORY_TRANSCRIPTS if opt_out else None,
    )
