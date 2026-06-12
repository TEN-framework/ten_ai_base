import asyncio
import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path


def _install_fake_ten_runtime() -> None:
    if "ten_runtime" in sys.modules:
        return

    ten_runtime = types.ModuleType("ten_runtime")

    class AsyncTenEnv:
        pass

    class AsyncExtension:
        def __init__(self, name: str) -> None:
            self.name = name

        async def on_init(self, ten_env) -> None:
            return None

        async def on_start(self, ten_env) -> None:
            return None

        async def on_stop(self, ten_env) -> None:
            return None

        async def on_deinit(self, ten_env) -> None:
            return None

    class Data:
        @staticmethod
        def create(name: str):
            return types.SimpleNamespace(name=name)

    class AudioFrame:
        @staticmethod
        def create(name: str):
            return types.SimpleNamespace(name=name)

    class AudioFrameDataFmt:
        INTERLEAVE = "interleave"

    class Cmd:
        pass

    class CmdResult:
        @staticmethod
        def create(status_code, cmd):
            return types.SimpleNamespace(status_code=status_code, cmd=cmd)

    class StatusCode:
        OK = "ok"
        ERROR = "error"

    ten_runtime.AsyncTenEnv = AsyncTenEnv
    ten_runtime.AsyncExtension = AsyncExtension
    ten_runtime.Data = Data
    ten_runtime.AudioFrame = AudioFrame
    ten_runtime.AudioFrameDataFmt = AudioFrameDataFmt
    ten_runtime.Cmd = Cmd
    ten_runtime.CmdResult = CmdResult
    ten_runtime.StatusCode = StatusCode

    sys.modules["ten_runtime"] = ten_runtime

    async_ten_env_module = types.ModuleType("ten_runtime.async_ten_env")
    async_ten_env_module.AsyncTenEnv = AsyncTenEnv
    sys.modules["ten_runtime.async_ten_env"] = async_ten_env_module

    audio_frame_module = types.ModuleType("ten_runtime.audio_frame")
    audio_frame_module.AudioFrame = AudioFrame
    audio_frame_module.AudioFrameDataFmt = AudioFrameDataFmt
    sys.modules["ten_runtime.audio_frame"] = audio_frame_module

    cmd_module = types.ModuleType("ten_runtime.cmd")
    cmd_module.Cmd = Cmd
    sys.modules["ten_runtime.cmd"] = cmd_module

    cmd_result_module = types.ModuleType("ten_runtime.cmd_result")
    cmd_result_module.CmdResult = CmdResult
    cmd_result_module.StatusCode = StatusCode
    sys.modules["ten_runtime.cmd_result"] = cmd_result_module


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_tts2_http_symbols():
    try:
        from ten_ai_base.message import TTSAudioEndReason
        from ten_ai_base.struct import TTS2HttpResponseEventType, TTSTextInput
        from ten_ai_base.tts2 import RequestState
        from ten_ai_base.tts2_http import (
            AsyncTTS2HttpClient,
            AsyncTTS2HttpConfig,
            AsyncTTS2HttpExtension,
        )

        return {
            "AsyncTTS2HttpClient": AsyncTTS2HttpClient,
            "AsyncTTS2HttpConfig": AsyncTTS2HttpConfig,
            "AsyncTTS2HttpExtension": AsyncTTS2HttpExtension,
            "RequestState": RequestState,
            "TTSAudioEndReason": TTSAudioEndReason,
            "TTS2HttpResponseEventType": TTS2HttpResponseEventType,
            "TTSTextInput": TTSTextInput,
        }
    except ModuleNotFoundError:
        _install_fake_ten_runtime()

        package_root = (
            Path(__file__).resolve().parents[1] / "interface" / "ten_ai_base"
        )
        package_name = "ten_ai_base"

        if package_name not in sys.modules:
            package = types.ModuleType(package_name)
            package.__path__ = [str(package_root)]
            sys.modules[package_name] = package

        for module in ["types", "message", "struct", "helper", "const", "tts2", "tts2_http"]:
            full_name = f"{package_name}.{module}"
            if full_name not in sys.modules:
                _load_module(full_name, package_root / f"{module}.py")

        return {
            "AsyncTTS2HttpClient": sys.modules[
                "ten_ai_base.tts2_http"
            ].AsyncTTS2HttpClient,
            "AsyncTTS2HttpConfig": sys.modules[
                "ten_ai_base.tts2_http"
            ].AsyncTTS2HttpConfig,
            "AsyncTTS2HttpExtension": sys.modules[
                "ten_ai_base.tts2_http"
            ].AsyncTTS2HttpExtension,
            "RequestState": sys.modules["ten_ai_base.tts2"].RequestState,
            "TTSAudioEndReason": sys.modules[
                "ten_ai_base.message"
            ].TTSAudioEndReason,
            "TTS2HttpResponseEventType": sys.modules[
                "ten_ai_base.struct"
            ].TTS2HttpResponseEventType,
            "TTSTextInput": sys.modules["ten_ai_base.struct"].TTSTextInput,
        }


SYMBOLS = _load_tts2_http_symbols()
AsyncTTS2HttpClient = SYMBOLS["AsyncTTS2HttpClient"]
AsyncTTS2HttpConfig = SYMBOLS["AsyncTTS2HttpConfig"]
AsyncTTS2HttpExtension = SYMBOLS["AsyncTTS2HttpExtension"]
RequestState = SYMBOLS["RequestState"]
TTSAudioEndReason = SYMBOLS["TTSAudioEndReason"]
TTS2HttpResponseEventType = SYMBOLS["TTS2HttpResponseEventType"]
TTSTextInput = SYMBOLS["TTSTextInput"]


class FakeTenEnv:
    def log_info(self, *args, **kwargs) -> None:
        return None

    def log_debug(self, *args, **kwargs) -> None:
        return None

    def log_warn(self, *args, **kwargs) -> None:
        return None

    def log_error(self, *args, **kwargs) -> None:
        return None


class FakeConfig(AsyncTTS2HttpConfig):
    def update_params(self) -> None:
        return None

    def to_str(self, sensitive_handling: bool = True) -> str:
        return "test-config"

    def validate(self) -> None:
        return None


class FakeHttpClient(AsyncTTS2HttpClient):
    def __init__(self, responses, extra_metadata=None) -> None:
        self.responses = responses
        self.extra_metadata = extra_metadata or {"provider": "test"}
        self.cancelled = False

    async def clean(self) -> None:
        return None

    async def cancel(self) -> None:
        self.cancelled = True

    async def get(self, text: str, request_id: str):
        for response in self.responses:
            yield response

    def get_extra_metadata(self) -> dict[str, str]:
        return self.extra_metadata


class RecordingHttpExtension(AsyncTTS2HttpExtension):
    def __init__(self, responses) -> None:
        super().__init__("test-http-tts")
        self.ten_env = FakeTenEnv()
        self.config = FakeConfig(dump=False)
        self.client = FakeHttpClient(responses)
        self.audio_starts = []
        self.audio_chunks = []
        self.audio_ends = []
        self.ttfb_metrics = []
        self.usage_metric_request_ids = []

    async def create_config(self, config_json_str: str):
        return self.config

    async def create_client(self, config, ten_env):
        return self.client

    def vendor(self) -> str:
        return "test_vendor"

    def synthesize_audio_sample_rate(self) -> int:
        return 16000

    async def update_configs(self, configs: dict) -> None:
        return None

    async def send_tts_audio_start(
        self, request_id: str, turn_id: int = -1, extra_metadata=None
    ) -> None:
        self.current_audio_request_id = request_id
        self.audio_starts.append({"request_id": request_id})

    async def send_tts_audio_data(self, audio_data: bytes, timestamp: int = 0) -> None:
        self.audio_chunks.append(bytes(audio_data))

    async def send_tts_audio_end(
        self,
        request_id: str,
        request_event_interval_ms: int,
        request_total_audio_duration_ms: int,
        turn_id: int = -1,
        reason=TTSAudioEndReason.REQUEST_END,
        extra_metadata=None,
    ) -> None:
        self.audio_ends.append(
            {
                "request_id": request_id,
                "request_event_interval_ms": request_event_interval_ms,
                "request_total_audio_duration_ms": request_total_audio_duration_ms,
                "reason": reason,
            }
        )
        if self.current_audio_request_id == request_id:
            self.current_audio_request_id = None

    async def send_tts_ttfb_metrics(
        self,
        request_id: str,
        ttfb_ms: int,
        turn_id: int = -1,
        extra_metadata=None,
    ) -> None:
        self.ttfb_metrics.append(
            {
                "request_id": request_id,
                "ttfb_ms": ttfb_ms,
                "extra_metadata": extra_metadata,
            }
        )

    async def send_usage_metrics(
        self, request_id: str = "", extra_metadata=None
    ) -> None:
        self.usage_metric_request_ids.append(request_id)


def _mark_request_finalizing(
    extension: RecordingHttpExtension, request_id: str
) -> None:
    extension.request_states[request_id] = RequestState.FINALIZING
    extension._processing_request_id = request_id


def _run(coro):
    return asyncio.run(coro)


def test_zero_audio_end_finishes_without_audio_start():
    extension = RecordingHttpExtension(
        [(None, TTS2HttpResponseEventType.END)]
    )
    extension.request_ts = datetime(2000, 1, 1)
    _mark_request_finalizing(extension, "silent-final")

    _run(
        extension.request_tts(
            TTSTextInput(
                request_id="silent-final",
                text="",
                text_input_end=True,
                metadata={},
            )
        )
    )

    assert extension.audio_starts == []
    assert extension.audio_chunks == []
    assert len(extension.audio_ends) == 1
    assert extension.audio_ends[0]["request_id"] == "silent-final"
    assert extension.audio_ends[0]["request_total_audio_duration_ms"] == 0
    assert extension.audio_ends[0]["reason"] == TTSAudioEndReason.REQUEST_END
    assert 0 <= extension.audio_ends[0]["request_event_interval_ms"] < 5000
    assert extension.usage_metric_request_ids == ["silent-final"]
    assert extension.request_states["silent-final"] == RequestState.COMPLETED
    assert extension._processing_request_id is None


def test_zero_audio_end_releases_next_queued_request():
    extension = RecordingHttpExtension(
        [(None, TTS2HttpResponseEventType.END)]
    )
    next_request = TTSTextInput(
        request_id="next-request",
        text="queued",
        text_input_end=True,
        metadata={},
    )
    extension.request_states["next-request"] = RequestState.QUEUED
    extension._pending_messages["next-request"] = [next_request]
    _mark_request_finalizing(extension, "silent-final")

    _run(
        extension.request_tts(
            TTSTextInput(
                request_id="silent-final",
                text="hello",
                text_input_end=True,
                metadata={},
            )
        )
    )

    released = _run(extension.input_queue.get())

    assert len(extension.audio_ends) == 1
    assert released.request_id == "next-request"
    assert extension._processing_request_id == "next-request"


def test_duplicate_terminal_signals_send_audio_end_once():
    extension = RecordingHttpExtension(
        [
            (b"", TTS2HttpResponseEventType.RESPONSE),
            (None, TTS2HttpResponseEventType.END),
        ]
    )
    _mark_request_finalizing(extension, "duplicate-terminal")

    _run(
        extension.request_tts(
            TTSTextInput(
                request_id="duplicate-terminal",
                text=" ",
                text_input_end=True,
                metadata={},
            )
        )
    )

    assert extension.audio_starts == []
    assert extension.audio_chunks == []
    assert len(extension.audio_ends) == 1
    assert extension.request_states["duplicate-terminal"] == RequestState.COMPLETED


def test_stream_without_end_still_finishes_silent_request():
    extension = RecordingHttpExtension([])
    _mark_request_finalizing(extension, "missing-end")

    _run(
        extension.request_tts(
            TTSTextInput(
                request_id="missing-end",
                text="trailing",
                text_input_end=True,
                metadata={},
            )
        )
    )

    assert len(extension.audio_ends) == 1
    assert extension.audio_ends[0]["request_total_audio_duration_ms"] == 0
    assert extension.request_states["missing-end"] == RequestState.COMPLETED


def test_normal_audio_flow_still_emits_start_audio_and_end():
    extension = RecordingHttpExtension(
        [
            (b"\x00\x01\x02\x03", TTS2HttpResponseEventType.RESPONSE),
            (None, TTS2HttpResponseEventType.END),
        ]
    )
    _mark_request_finalizing(extension, "audio-request")

    _run(
        extension.request_tts(
            TTSTextInput(
                request_id="audio-request",
                text="hello world",
                text_input_end=True,
                metadata={},
            )
        )
    )

    assert extension.audio_starts == [{"request_id": "audio-request"}]
    assert extension.audio_chunks == [b"\x00\x01\x02\x03"]
    assert len(extension.ttfb_metrics) == 1
    assert extension.ttfb_metrics[0]["request_id"] == "audio-request"
    assert extension.ttfb_metrics[0]["extra_metadata"] == {"provider": "test"}
    assert len(extension.audio_ends) == 1
    assert extension.request_states["audio-request"] == RequestState.COMPLETED
