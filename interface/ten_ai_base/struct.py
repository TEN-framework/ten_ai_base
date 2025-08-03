#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from enum import Enum
import json
from typing import Any, Optional, TypeAlias, Union
from pydantic import BaseModel

from .types import LLMToolMetadata


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


"""
===========LLM Input and Output Models================
"""

class LLMInputMessageContentPart(BaseModel):
    """
    Model for a single part of the content in LLM input messages.
    This model is used to define the structure of content parts in messages sent to the LLM.
    """
    type: str
    text: Optional[str] = None
    image_url: Optional[str] = None

LLMInputMessageContent: TypeAlias = Union[list[LLMInputMessageContentPart], str]

class LLMInputMessage(BaseModel):
    """
    Model for a single message in LLM input.
    This model is used to define the structure of messages sent to the LLM.
    """
    role: str
    content: LLMInputMessageContent
    tool_call_id: Optional[str] = None

class LLMInput(BaseModel):
    """
    Model for LLM input data.
    This model is used to define the structure of the input data for LLM operations.
    """
    model: str
    messages: list[LLMInputMessage]
    streaming: Optional[bool] = True
    tools: Optional[list[LLMToolMetadata]] = None
    parameters: Optional[dict[str, Any]] = None


class EventType(str, Enum):
    MESSAGE_CONTENT = "message_content"
    TOOL_CALL_CONTENT = "tool_call_content"




class LLMResponse(BaseModel):
    """
    Model for LLM output data.
    This model is used to define the structure of the output data returned by LLM operations.
    """
    response_id: str
    created: Optional[int] = None

class LLMResponseMessage(LLMResponse):
    """
    Model for a single message in LLM output.
    This model is used to define the structure of messages returned by the LLM.
    """
    role: str
    content: Optional[str] = None
    type: EventType = EventType.MESSAGE_CONTENT

class LLMResponseToolCall(LLMResponse):
    """
    Model for a tool call in LLM output.
    This model is used to define the structure of tool calls returned by the LLM.
    """
    tool_call_id: str
    name: str
    type: EventType = EventType.TOOL_CALL_CONTENT
    arguments: Optional[dict[str, Any]] = None



def parse_llm_response(unparsed_string: str) -> LLMResponse:
    data = json.loads(unparsed_string)

    # Dynamically select the correct message class based on the `type` field, using from_dict
    if data["type"] == EventType.MESSAGE_CONTENT:
        return LLMResponseMessage.model_validate(data)
    elif data["type"] == EventType.TOOL_CALL_CONTENT:
        return LLMResponseToolCall.model_validate(data)

    raise ValueError(f"Unknown message type: {data['type']}")
