#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from typing import Any, Optional, TypeAlias, Union
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

class LLMInputToolParameters(BaseModel):
    """
    Model for the parameters of a tool used in LLM operations.
    This model is used to define the structure of parameters for tools that can be invoked by the LLM.
    """
    name: str
    type: str
    description: str
    required: Optional[bool] = False

class LLMInputTool(BaseModel):
    """
    Model for a tool available to the LLM.
    This model is used to define the structure of tools that can be used in LLM operations.
    """
    name: str
    description: str
    parameters: list[LLMInputToolParameters]

class LLMInput(BaseModel):
    """
    Model for LLM input data.
    This model is used to define the structure of the input data for LLM operations.
    """
    model: str
    messages: list[LLMInputMessage]
    streaming: Optional[bool] = True
    tools: Optional[list[LLMInputTool]] = None


class LLMOutputChoiceDeltaToolCall(BaseModel):
    """
    Model for a tool call in the delta of LLM output choices.
    This model is used to define the structure of tool calls that may be part of the changes in choices returned by the LLM.
    """
    id: str
    type: str
    function: Optional[dict] = None
    index: int = None

class LLMOutputChoiceDelta(BaseModel):
    """
    Model for the delta of a choice in LLM output.
    This model is used to define the structure of changes in choices returned by the LLM.
    """
    role: Optional[str] = None
    content: Optional[str] = None
    refusal: Optional[str] = None
    tool_calls: Optional[list[LLMOutputChoiceDeltaToolCall]] = None

class LLMOutputChoice(BaseModel):
    """
    Model for a single choice in LLM output.
    This model is used to define the structure of choices returned by the LLM.
    """
    index: int
    logprobs: Optional[dict] = None
    finish_reason: Optional[str] = None
    delta: Optional[LLMOutputChoiceDelta] = None

class LLMOutput(BaseModel):
    """
    Model for LLM output data.
    This model is used to define the structure of the output data returned by LLM operations.
    """
    id: str
    model: str
    choices: list[LLMOutputChoice]
    service_tier: Optional[str] = None
    created: Optional[int] = None