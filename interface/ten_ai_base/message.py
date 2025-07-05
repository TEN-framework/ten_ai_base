from pydantic import BaseModel
from enum import Enum, IntEnum
from typing import Any

class MetadataKey(Enum, str):
    SESSION_ID = "session_id"
    TURN_ID = "turn_id"

class ModuleType(Enum, str):
    LLM = "llm"
    TTS = "tts"
    MLLM = "mllm"
    STT = "asr"
    TURN = "turn"
    AVATAR = "avatar"

class ModuleMetricKey(Enum, str):
    ASR_TTLW = "ttlw"
    TTS_TTFB = "ttfb"
    LLM_TTFB = "ttfb"
    LLM_TTFS = "ttfs"

class ModuleErrorCode(Enum, str):
    OK = 0

    # After a fatal error occurs, the module will stop all operations.
    FATAL_ERROR = -1000

    # After a non-fatal error occurs, the module itself will continue to retry.
    NON_FATAL_ERROR = 1000
    
class ModuleVendorError(BaseModel):
    vendor: str = ""    # vendor name
    code: str = ""      # vendor's original error code
    message: str = ""   # vendor's original error message

class ModuleError(BaseModel):
    id: str = ""        # uuid
    module: str = ""    # module type
    code: int = 0
    message: str = ""
    vendor_error: ModuleVendorError | None = None
    metadata: dict[str, Any] = {}

class ModuleMetrics(BaseModel):
    id: str = ""        # uuid
    module: str = ""    # module type
    vendor: str = ""    # vendor name
    metrics: dict[str, Any] = {}   # key-value pair metrics, e.g. {"ttfb": 100, "ttfs": 200}
    metadata: dict[str, Any] = {}

class ErrorMessage(BaseModel):
    object: str = "message.error"
    module: str = ""
    message: str = ""
    turn_id: int = 0
    code: int = 0

class ErrorMessageVendorInfo(BaseModel):
    object: str = "message.error.vendor_info"
    vendor: str = ""
    code: int = 0
    message: str = ""

class MetricsMessage(BaseModel):
    object: str = "message.metrics"
    module: str = ""
    metric_name: str = ""
    turn_id: int = 0
    latency_ms: int = 0
