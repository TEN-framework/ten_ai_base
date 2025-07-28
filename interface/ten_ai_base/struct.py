#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from typing import Any
from pydantic import BaseModel


class TTSWord(BaseModel):
    word: str = ""
    start_ms: int = -1  # start time of the word, milliseconds since epoch
    duration_ms: int = -1  # duration of the word, in milliseconds


class TTSTextInput(BaseModel):
    request_id: str
    text: str
    text_input_end: bool = False
    metadata: dict[str, Any] = {}  # additional metadata for the transcription


class TTSTextResult(BaseModel):
    request_id: str
    text: str
    start_ms: int
    duration_ms: int
    words: list[TTSWord] | None = None
    text_result_end: bool = False
    metadata: dict[str, Any] = {}  # additional metadata for the transcription


class TTSFlush(BaseModel):
    flush_id: str
    metadata: dict[str, Any] = {}  # additional metadata for the flush operation


class ASRWord(BaseModel):
    word: str
    start_ms: int
    duration_ms: int
    stable: bool


class ASRResult(BaseModel):
    id: str | None = None
    text: str
    final: bool
    start_ms: int
    duration_ms: int
    language: str
    words: list[ASRWord] | None = None
    metadata: dict[str, Any] = {}  # additional metadata for the transcription
