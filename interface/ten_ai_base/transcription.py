from pydantic import BaseModel
from enum import IntEnum


class TurnStatus(IntEnum):
    IN_PROGRESS = 0
    END = 1             # End gracefully
    INTERRUPTED = 2     # End by interrupt


class Word(BaseModel):
    word: str = ""
    start_ms: int = 0    # start time of the word, milliseconds since epoch
    stable: bool = True  # whether 'word' won't change anymore


class UserTranscription(BaseModel):
    object: str = "user.transcription"  # [required] name of the object
    text: str = ""      # [required] text for display
    final: bool = True  # whether 'text' won't change anymore
    start_ms: int = 0   # start time of the text, milliseconds since epoch
    language: str = ""  # IETF BCP 47(RFC 4646), such as 'en-US' or 'zh-CN'

    turn_id: int = 0

    # which stream/user the text belongs to
    stream_id: int = 0
    user_id: str = ""

    words: list[Word] | None = None


class AssistantTranscription(BaseModel):
    object: str = "assistant.transcription"  # [required] name of the object
    text: str = ""      # [required] text for display
    start_ms: int = 0   # start time of the text, milliseconds since epoch
    language: str = ""  # IETF BCP 47(RFC 4646), such as 'en-US' or 'zh-CN'

    quiet: bool = False  # expect to pronounce or not

    turn_id: int = 0
    turn_seq_id: int = 0

    # 0: in-progress, 1: end gracefully, 2: interrupted, otherwise undefined
    turn_status: int = 0

    # which stream/user the text belongs to
    stream_id: int = 0
    user_id: str = ""

    words: list[Word] | None = None
