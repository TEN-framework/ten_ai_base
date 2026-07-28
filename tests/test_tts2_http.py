import asyncio
import importlib.util
import json
import sys
import types
from datetime import datetime
from pathlib import Path


def _create_fake_ten_runtime_modules() -> dict[str, types.ModuleType]:
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

    class FakeData:
        def __init__(self, name: str) -> None:
            self.name = name
            self.properties = {}

        def set_property_from_json(self, path, value) -> None:
            self.properties[path] = value

    class Data:
        @staticmethod
        def create(name: str):
            return FakeData(name)

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

    async_ten_env_module = types.ModuleType("ten_runtime.async_ten_env")
    async_ten_env_module.AsyncTenEnv = AsyncTenEnv

    audio_frame_module = types.ModuleType("ten_runtime.audio_frame")
    audio_frame_module.AudioFrame = AudioFrame
    audio_frame_module.AudioFrameDataFmt = AudioFrameDataFmt

    cmd_module = types.ModuleType("ten_runtime.cmd")
    cmd_module.Cmd = Cmd

    cmd_result_module = types.ModuleType("ten_runtime.cmd_result")
    cmd_result_module.CmdResult = CmdResult
    cmd_result_module.StatusCode = StatusCode

    return {
        "ten_runtime": ten_runtime,
        "ten_runtime.async_ten_env": async_ten_env_module,
        "ten_runtime.audio_frame": audio_frame_module,
        "ten_runtime.cmd": cmd_module,
        "ten_runtime.cmd_result": cmd_result_module,
    }


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_tts2_http_symbols():
    fake_runtime_modules = _create_fake_ten_runtime_modules()
    original_runtime_modules = {
        name: sys.modules.get(name) for name in fake_runtime_modules
    }
    sys.modules.update(fake_runtime_modules)

    package_root = Path(__file__).resolve().parents[1] / "interface" / "ten_ai_base"
    package_name = "ten_ai_base"
    package_module_names = [
        package_name,
        f"{package_name}.types",
        f"{package_name}.message",
        f"{package_name}.struct",
        f"{package_name}.helper",
        f"{package_name}.const",
        f"{package_name}.utils",
        f"{package_name}.tts2",
        f"{package_name}.tts2_http",
    ]
    original_package_modules = {
        name: sys.modules.get(name) for name in package_module_names
    }
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_root)]
    sys.modules[package_name] = package

    try:
        for module in [
            "types",
            "message",
            "struct",
            "helper",
            "const",
            "utils",
            "tts2",
            "tts2_http",
        ]:
            _load_module(f"{package_name}.{module}", package_root / f"{module}.py")

        return {
            "AsyncTTS2HttpClient": sys.modules[
                f"{package_name}.tts2_http"
            ].AsyncTTS2HttpClient,
            "AsyncTTS2HttpConfig": sys.modules[
                f"{package_name}.tts2_http"
            ].AsyncTTS2HttpConfig,
            "AsyncTTS2HttpExtension": sys.modules[
                f"{package_name}.tts2_http"
            ].AsyncTTS2HttpExtension,
            "RequestState": sys.modules[f"{package_name}.tts2"].RequestState,
            "ModuleConnectionStatus": sys.modules[
                f"{package_name}.message"
            ].ModuleConnectionStatus,
            "ModuleError": sys.modules[f"{package_name}.message"].ModuleError,
            "TTSAudioEndReason": sys.modules[
                f"{package_name}.message"
            ].TTSAudioEndReason,
            "TTS2HttpResponseEventType": sys.modules[
                f"{package_name}.struct"
            ].TTS2HttpResponseEventType,
            "TTSTextInput": sys.modules[f"{package_name}.struct"].TTSTextInput,
            "mask_secret": sys.modules[f"{package_name}.utils"].mask_secret,
        }
    finally:
        for name, module in original_package_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        for name, module in original_runtime_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


SYMBOLS = _load_tts2_http_symbols()
AsyncTTS2HttpClient = SYMBOLS["AsyncTTS2HttpClient"]
AsyncTTS2HttpConfig = SYMBOLS["AsyncTTS2HttpConfig"]
AsyncTTS2HttpExtension = SYMBOLS["AsyncTTS2HttpExtension"]
RequestState = SYMBOLS["RequestState"]
ModuleConnectionStatus = SYMBOLS["ModuleConnectionStatus"]
TTSAudioEndReason = SYMBOLS["TTSAudioEndReason"]
TTS2HttpResponseEventType = SYMBOLS["TTS2HttpResponseEventType"]
TTSTextInput = SYMBOLS["TTSTextInput"]
mask_secret = SYMBOLS["mask_secret"]


class FakeTenEnv:
    def __init__(self) -> None:
        self.sent_data = []

    def log_info(self, *args, **kwargs) -> None:
        return None

    def log_debug(self, *args, **kwargs) -> None:
        return None

    def log_warn(self, *args, **kwargs) -> None:
        return None

    def log_error(self, *args, **kwargs) -> None:
        return None

    async def send_data(self, data) -> None:
        self.sent_data.append(data)


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


class FailingHttpClient(FakeHttpClient):
    async def get(self, text: str, request_id: str):
        if False:
            yield None
        raise RuntimeError("vendor request failed")


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

    def vendor_metadata(self) -> dict:
        return {"key": "sk-test-secret-1234", "url": "wss://tts.example"}

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


def _data_payload(data):
    return json.loads(data.properties[None])


def test_connection_status_events_are_sent_by_base():
    extension = RecordingHttpExtension([])

    _run(extension.on_connecting())
    _run(extension.on_connected())
    _run(extension.on_disconnected(code=3001, message="websocket closed"))

    assert extension.connection_status == ModuleConnectionStatus.DISCONNECTED
    assert [data.name for data in extension.ten_env.sent_data] == [
        "connection_status_changed",
        "connection_status_changed",
        "connection_status_changed",
    ]
    payloads = [_data_payload(data) for data in extension.ten_env.sent_data]
    assert [payload["current"] for payload in payloads] == [
        "connecting",
        "connected",
        "disconnected",
    ]
    assert payloads[0]["last"] == "disconnected"
    assert payloads[2]["code"] == 3001
    assert payloads[2]["message"] == "websocket closed"
    assert payloads[2]["metadata"]["vendor_metadata"] == {
        "key": mask_secret("sk-test-secret-1234"),
        "url": "wss://tts.example",
    }
    assert payloads[2]["vendor_info"] == {
        "vendor": "test_vendor",
        "code": "",
        "message": "",
    }


def test_vendor_metadata_is_added_to_metrics_and_errors():
    extension = RecordingHttpExtension([])
    extension.metadatas["req"] = {
        "session_id": "session-1",
        "vendor_metadata": {
            "region": "us",
            "api_key": "existing-secret-5678",
        },
    }

    _run(extension.metrics_connect_delay(42, request_id="req"))
    _run(
        extension.send_tts_error(
            request_id="req",
            error=SYMBOLS["ModuleError"](
                code=1000,
                message="failed",
                metadata={"turn_id": 7},
            ),
        )
    )

    metrics_payload = _data_payload(extension.ten_env.sent_data[0])
    error_payload = _data_payload(extension.ten_env.sent_data[1])

    assert metrics_payload["metadata"] == {
        "session_id": "session-1",
        "vendor_metadata": {
            "region": "us",
            "api_key": mask_secret("existing-secret-5678"),
            "key": mask_secret("sk-test-secret-1234"),
            "url": "wss://tts.example",
        },
    }
    assert error_payload["metadata"] == {
        "session_id": "session-1",
        "turn_id": 7,
        "vendor_metadata": {
            "region": "us",
            "api_key": mask_secret("existing-secret-5678"),
            "key": mask_secret("sk-test-secret-1234"),
            "url": "wss://tts.example",
        },
    }


def test_http_vendor_attempt_emits_request_metrics():
    extension = RecordingHttpExtension([(None, TTS2HttpResponseEventType.END)])
    _mark_request_finalizing(extension, "request-metrics")

    _run(
        extension.request_tts(
            TTSTextInput(
                request_id="request-metrics",
                text="hello",
                text_input_end=True,
                metadata={"session_id": "session-1", "turn_id": 7},
            )
        )
    )

    metrics_payloads = [
        _data_payload(data)
        for data in extension.ten_env.sent_data
        if data.name == "metrics"
    ]
    request_metrics = next(
        payload
        for payload in metrics_payloads
        if "request_time_ms" in payload["metrics"]
    )
    assert request_metrics["module"] == "tts"
    assert request_metrics["vendor"] == "test_vendor"
    assert request_metrics["metrics"]["request_time_ms"] > 0
    assert request_metrics["metrics"]["request_bytes"] == 5
    assert request_metrics["metrics"]["response_time_ms"] == 0
    assert request_metrics["metrics"]["response_bytes"] == 0
    assert request_metrics["metadata"]["request_id"] == "request-metrics"
    assert request_metrics["metadata"]["request_final"] is True


def test_final_marker_has_no_request_metric_values():
    extension = RecordingHttpExtension([])
    extension.metadatas["final-marker"] = {"session_id": "session-1"}

    _run(extension.send_tts_request_final_marker("final-marker"))

    payload = _data_payload(extension.ten_env.sent_data[0])
    assert payload["metrics"] == {}
    assert payload["metadata"]["request_id"] == "final-marker"
    assert payload["metadata"]["request_final"] is True


def test_empty_final_marker_is_sent_before_provider_processing():
    class MarkerOrderExtension(RecordingHttpExtension):
        def __init__(self) -> None:
            super().__init__([])
            self.events = []

        async def send_tts_request_final_marker(self, request_id: str) -> None:
            self.events.append(("marker", request_id))

        async def request_tts(self, t: TTSTextInput) -> None:
            self.events.append(("provider", t.request_id))

    extension = MarkerOrderExtension()
    extension.request_states["empty-final"] = RequestState.QUEUED

    async def process() -> None:
        await extension.input_queue.put(
            TTSTextInput(
                request_id="empty-final",
                text="",
                text_input_end=True,
                metadata={},
            )
        )
        await extension.input_queue.put(None)
        await extension._process_input_queue(extension.ten_env)

    _run(process())

    assert extension.events == [
        ("marker", "empty-final"),
        ("provider", "empty-final"),
    ]


def test_http_vendor_failure_still_emits_request_metrics():
    extension = RecordingHttpExtension([])
    extension.client = FailingHttpClient([])
    _mark_request_finalizing(extension, "failed-request")

    _run(
        extension.request_tts(
            TTSTextInput(
                request_id="failed-request",
                text="failed text",
                text_input_end=True,
                metadata={},
            )
        )
    )

    metrics_payloads = [
        _data_payload(data)
        for data in extension.ten_env.sent_data
        if data.name == "metrics"
    ]
    assert any(
        payload["metrics"].get("request_bytes") == 11 for payload in metrics_payloads
    )


def test_zero_audio_end_finishes_without_audio_start():
    extension = RecordingHttpExtension([(None, TTS2HttpResponseEventType.END)])
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
    extension = RecordingHttpExtension([(None, TTS2HttpResponseEventType.END)])
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
