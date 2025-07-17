from pydantic import BaseModel

class TTSMetadata(BaseModel):
    session_id: str = ""
    turn_id: int = -1

class TTSWord(BaseModel):
    word: str = ""
    start_ms: int = -1  # start time of the word, milliseconds since epoch
    duration_ms: int = -1  # duration of the word, in milliseconds

class TTSTextInput(BaseModel):
    request_id: str
    text: str
    text_input_end: bool = False
    metadata: TTSMetadata | None = None  # additional metadata for the transcription

class TTSTextResult(BaseModel):
    request_id: str
    text: str
    start_ms: int
    duration_ms: int
    words: list[TTSWord] | None = None
    text_result_end: bool = False
    metadata: TTSMetadata | None = None  # additional metadata for the transcription

