from pydantic import BaseModel
from enum import Enum


class ModuleType(Enum):
    LLM = "llm"
    TTS = "tts"
    MLLM = "mllm"
    STT = "asr"


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
