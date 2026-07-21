#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from abc import abstractmethod
from typing import Any, Callable, final
import functools
import uuid

from .struct import ASRResult
from .types import ASRBufferConfig, ASRBufferConfigModeDiscard, ASRBufferConfigModeKeep

from .message import (
    MetadataKey,
    ModuleConnectionStatus,
    ModuleConnectionStatusChanged,
    ModuleError,
    ModuleErrorVendorInfo,
    ModuleMetricKey,
    ModuleMetrics,
    ModuleType,
    VENDOR_METADATA_KEY,
)
from .connection_status import ConnectionStatusMachine, ConnectionStatusTransition
from .features import send_provide_features
from .timeline import AudioTimeline
from .utils import redact_json
from .const import (
    DATA_IN_ASR_FINALIZE,
    DATA_IN_TRIGGER_CONNECT,
    DATA_OUT_ASR_FINALIZE_END,
    DATA_OUT_CONNECTION_STATUS_CHANGED,
    DATA_OUT_METRICS,
    LOG_CATEGORY_KEY_POINT,
    PROPERTY_KEY_METADATA,
    PROPERTY_KEY_SESSION_ID,
)
from ten_runtime import (
    AsyncExtension,
    AsyncTenEnv,
    Cmd,
    Data,
    AudioFrame,
    StatusCode,
    CmdResult,
)
import asyncio
import json


def _connecting_before_start_connection(
    method: Callable[..., Any],
) -> Callable[..., Any]:
    @functools.wraps(method)
    async def wrapper(
        self: "AsyncASRBaseExtension", *args: Any, **kwargs: Any
    ) -> Any:
        await self._emit_connection_transition(
            self._connection_machine.try_connecting(),
            already_done="start_connection: already connecting, skip.",
        )
        return await method(self, *args, **kwargs)

    return wrapper


class AsyncASRBaseExtension(AsyncExtension):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if impl := cls.__dict__.get("start_connection"):
            cls.start_connection = _connecting_before_start_connection(impl)  # type: ignore[method-assign]

    def __init__(self, name: str):
        super().__init__(name)

        self.stopped = False
        self.ten_env: AsyncTenEnv = None  # type: ignore
        self.session_id = None
        self.metadata: dict | None = None
        self.finalize_id = None
        self.sent_buffer_length = 0
        self.buffered_frames = asyncio.Queue[AudioFrame]()
        self.buffered_frames_size = 0
        self.audio_frames_queue = asyncio.Queue[AudioFrame]()
        self.audio_timeline = AudioTimeline(self._handle_error_in_audio_timeline)
        self.audio_actual_send_metrics_task: asyncio.Task[None] | None = None
        self.uuid = self._get_uuid()  # Unique identifier for the current final turn
        self.last_reported_audio_duration = 0  # Track audio duration at last report

        # States for TTFW calculation
        self.first_audio_time: float | None = (
            None  # Record the timestamp of the first audio send
        )
        self.ttfw_sent = False  # Track if TTFW has been sent

        # States for TTLW calculation
        self.last_finalize_time: float | None = None

        self.auto_connect: bool = True
        self._connection_lock = asyncio.Lock()
        self._connection_machine = ConnectionStatusMachine()

    @property
    def connection_status(self) -> ModuleConnectionStatus:
        """Return the connection state maintained by the base class."""
        return self._connection_machine.status

    def _get_masked_vendor_metadata(self) -> dict[str, Any]:
        return redact_json(self.vendor_metadata() or {})

    def _build_report_metadata(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if self.metadata is not None:
            metadata.update(self.metadata)
        if self.session_id is not None:
            metadata[MetadataKey.SESSION_ID] = self.session_id
        if extra:
            metadata.update(
                {
                    key: value
                    for key, value in extra.items()
                    if key != VENDOR_METADATA_KEY
                }
            )
        metadata[VENDOR_METADATA_KEY] = self._get_masked_vendor_metadata()
        return metadata

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        self.ten_env = ten_env

        val, err = await ten_env.get_property_bool("auto_connect")
        self.auto_connect = True if err else val

        asyncio.create_task(self._audio_frame_consumer())

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_info("on_start")

        features = {"asr.vendor": self.vendor()}
        model = self._get_masked_vendor_metadata().get("model")
        if isinstance(model, str) and model:
            features["asr.model"] = model

        await send_provide_features(
            ten_env,
            features,
        )

        # Create a task to send audio actual send metrics
        self.audio_actual_send_metrics_task = asyncio.create_task(
            self._send_audio_actual_send_metrics_task()
        )

        if self.auto_connect:
            await self._ensure_connection()

    async def on_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        await self.audio_frames_queue.put(audio_frame)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log_debug(f"on_data name: {data_name}")

        if data_name == DATA_IN_ASR_FINALIZE:
            if not self._safe_is_connected():
                ten_env.log_warn(
                    "asr_finalize: service not connected.",
                    category=LOG_CATEGORY_KEY_POINT,
                )

            finalize_id, err = data.get_property_string("finalize_id")
            if err:
                ten_env.log_error(
                    f"asr_finalize: failed to get finalize_id: {err}",
                    category=LOG_CATEGORY_KEY_POINT,
                )
                return

            self.finalize_id = finalize_id
            self.last_finalize_time = asyncio.get_event_loop().time()

            ten_env.log_info(
                f"asr_finalize: finalize_id: {self.finalize_id}",
                category=LOG_CATEGORY_KEY_POINT,
            )

            await self.finalize(self.session_id)

        elif data_name == DATA_IN_TRIGGER_CONNECT:
            ten_env.log_info(
                "trigger_connect: initiating connection.",
                category=LOG_CATEGORY_KEY_POINT,
            )
            await self._ensure_connection()

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        if self.ten_env is None:
            self.ten_env = ten_env

        ten_env.log_info("on_stop")

        self.stopped = True

        await self.stop_connection()

        await self._emit_connection_transition(
            self._connection_machine.try_disconnected(code=0, message="stopped"),
            already_done="on_stop: already disconnected, skip.",
        )

        if self.audio_actual_send_metrics_task:
            self.audio_actual_send_metrics_task.cancel()
            self.audio_actual_send_metrics_task = None

        await self._send_audio_actual_send_metrics()

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_info(f"on_cmd json: {cmd_name}")

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)

    def vendor_metadata(self) -> dict[str, Any]:
        """
        Return the current vendor configuration snapshot for reporting.
        Should include key/url/model/region/mode (empty string when unavailable).
        The base class redacts sensitive fields before sending events.

        Subclasses may override to supply vendor-specific values; the default
        empty snapshot keeps the ASR main path working without changes.
        """
        return {}

    @abstractmethod
    def vendor(self) -> str:
        """Get the name of the ASR vendor."""
        raise NotImplementedError("This method should be implemented in subclasses.")

    @abstractmethod
    async def start_connection(self) -> None:
        """
        Start the connection to the ASR service.

        Subclasses override this hook only; the base class emits CONNECTING
        before the override runs. Call on_connected() / on_disconnected() for
        later state transitions — do not emit connecting manually.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the ASR service is connected."""
        raise NotImplementedError("This method should be implemented in subclasses.")

    @abstractmethod
    async def stop_connection(self) -> None:
        """Stop the connection to the ASR service."""
        raise NotImplementedError("This method should be implemented in subclasses.")

    @abstractmethod
    def input_audio_sample_rate(self) -> int:
        """
        Get the input audio sample rate in Hz.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    def input_audio_channels(self) -> int:
        """
        Get the number of audio channels for input.
        Default is 1 (mono).
        """
        return 1

    def input_audio_sample_width(self) -> int:
        """
        Get the sample width in bytes for input audio.
        Default is 2 (16-bit PCM).
        """
        return 2

    def buffer_strategy(self) -> ASRBufferConfig:
        """
        Get the buffer strategy for audio frames when not connected
        """
        return ASRBufferConfigModeDiscard()

    def audio_actual_send_metrics_interval(self) -> int:
        """
        Get the interval in seconds for sending audio actual send metrics.
        """
        return 5

    @abstractmethod
    async def send_audio(self, frame: AudioFrame, session_id: str | None) -> bool:
        """
        Send an audio frame to the ASR service, returning True if successful.
        Note: The first successful send_audio call will be timestamped for TTFW calculation.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    @abstractmethod
    async def finalize(self, session_id: str | None) -> None:
        """
        Drain the ASR service to ensure all audio frames are processed.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    @final
    async def send_asr_result(self, asr_result: ASRResult) -> None:
        """
        Send a transcription result as output.
        """
        asr_result.id = self.uuid
        # Only set metadata if asr_result doesn't already have metadata and self.metadata is available
        if self.metadata is not None:
            if not asr_result.metadata:
                asr_result.metadata = self.metadata
            else:
                asr_result.metadata.update(self.metadata)

        # If this is the first result and there is a timestamp for the first
        # audio sent, calculate and send TTFW.
        if not self.ttfw_sent and self.first_audio_time is not None:
            current_time = asyncio.get_event_loop().time()
            ttfw = int((current_time - self.first_audio_time) * 1000)
            await self._send_metrics_ttfw(ttfw)
            self.ttfw_sent = True

        # If last_finalize_time is not None, calculate and send TTLW.
        if asr_result.final and self.last_finalize_time is not None:
            current_time = asyncio.get_event_loop().time()
            ttlw = int((current_time - self.last_finalize_time) * 1000)
            await self._send_metrics_ttlw(ttlw)
            self.last_finalize_time = None

        stable_data = Data.create("asr_result")

        model_json = asr_result.model_dump()

        stable_data.set_property_from_json(
            None,
            json.dumps(model_json),
        )

        await self.ten_env.send_data(stable_data)

        self.ten_env.log_info(
            f"send_asr_result: {model_json}", category=LOG_CATEGORY_KEY_POINT
        )

        if asr_result.final:
            self.uuid = self._get_uuid()  # Reset UUID for the next final turn

    @final
    async def send_asr_error(
        self, error: ModuleError, vendor_info: ModuleErrorVendorInfo | None = None
    ) -> None:
        """
        Send an error message related to ASR processing.
        """
        error_data = Data.create("error")

        vendorInfo = None
        if vendor_info:
            vendorInfo = {
                "vendor": vendor_info.vendor,
                "code": vendor_info.code,
                "message": vendor_info.message,
            }
        elif error.vendor_info:
            vendorInfo = {
                "vendor": error.vendor_info.vendor,
                "code": error.vendor_info.code,
                "message": error.vendor_info.message,
            }

        property_json = json.dumps(
            {
                "id": self.uuid,
                "module": ModuleType.ASR,
                "code": error.code,
                "message": error.message,
                "vendor_info": vendorInfo or {},
                "metadata": self._build_report_metadata(error.metadata or None),
            }
        )

        error_data.set_property_from_json(
            None,
            property_json,
        )

        await self.ten_env.send_data(error_data)

        self.ten_env.log_info(
            f"send asr_error: {property_json}", category=LOG_CATEGORY_KEY_POINT
        )

    @final
    async def send_asr_finalize_end(self) -> None:
        """
        Send a signal that the ASR service has finished processing all audio frames.
        """
        asr_finalize_end_data = Data.create(DATA_OUT_ASR_FINALIZE_END)
        asr_finalize_end_data.set_property_from_json(
            None,
            json.dumps(
                {
                    "finalize_id": self.finalize_id,
                    "metadata": ({} if self.metadata is None else self.metadata),
                }
            ),
        )

        await self.ten_env.send_data(asr_finalize_end_data)
        self.ten_env.log_info(
            f"send asr_finalize_end, finalize_id: {self.finalize_id}",
            category=LOG_CATEGORY_KEY_POINT,
        )

    @final
    async def send_connect_delay_metrics(self, connect_delay: int) -> None:
        """
        Send metrics for time to connect to ASR server.
        """
        metrics = ModuleMetrics(
            module=ModuleType.ASR,
            vendor=self.vendor(),
            metrics={ModuleMetricKey.ASR_CONNECT_DELAY: connect_delay},
        )
        await self._send_asr_metrics(metrics)

    @final
    async def send_vendor_metrics(self, vendor_metrics: dict[str, Any]) -> None:
        """
        Send vendor specific metrics.
        """
        metrics = ModuleMetrics(
            module=ModuleType.ASR,
            vendor=self.vendor(),
            metrics={ModuleMetricKey.ASR_VENDOR_METRICS: vendor_metrics},
        )
        await self._send_asr_metrics(metrics)

    async def _send_audio_actual_send_metrics(self) -> None:
        """
        Send audio actual send metrics.
        """
        actual_send = (
            self.audio_timeline.total_user_audio_duration
            + self.audio_timeline.total_silence_audio_duration
        )

        # Calculate the audio duration since last report
        duration_since_last_report = actual_send - self.last_reported_audio_duration
        self.last_reported_audio_duration = actual_send

        metrics = ModuleMetrics(
            module=ModuleType.ASR,
            vendor=self.vendor(),
            metrics={
                ModuleMetricKey.ASR_ACTUAL_SEND: actual_send,
                ModuleMetricKey.ASR_ACTUAL_SEND_DELTA: duration_since_last_report,
            },
        )
        await self._send_asr_metrics(metrics)

    async def _send_asr_metrics(self, metrics: ModuleMetrics) -> None:
        """
        Send metrics related to the ASR module.
        """
        metrics_data = Data.create(DATA_OUT_METRICS)

        metrics_data.set_property_from_json(
            None,
            json.dumps(
                {
                    "id": self.uuid,
                    "module": metrics.module,
                    "vendor": metrics.vendor,
                    "metrics": metrics.metrics,
                    "metadata": self._build_report_metadata(metrics.metadata or None),
                }
            ),
        )

        await self.ten_env.send_data(metrics_data)
        self.ten_env.log_info(
            f"send asr_metrics: {metrics}", category=LOG_CATEGORY_KEY_POINT
        )

    async def _send_metrics_ttfw(self, ttfw: int) -> None:
        """
        Send metrics for time to first word.
        """
        metrics = ModuleMetrics(
            module=ModuleType.ASR,
            vendor=self.vendor(),
            metrics={ModuleMetricKey.ASR_TTFW: ttfw},
        )

        await self._send_asr_metrics(metrics)

    async def _send_metrics_ttlw(self, ttlw: int) -> None:
        """
        Send metrics for time to last word.
        """
        metrics = ModuleMetrics(
            module=ModuleType.ASR,
            vendor=self.vendor(),
            metrics={ModuleMetricKey.ASR_TTLW: ttlw},
        )

        await self._send_asr_metrics(metrics)

    def _get_uuid(self) -> str:
        """
        Get a unique identifier
        """
        return uuid.uuid4().hex

    def _safe_is_connected(self) -> bool:
        """
        Check connection state without letting provider exceptions break the base loop.
        """
        try:
            return self.is_connected()
        except Exception as e:
            if self.ten_env is not None:
                self.ten_env.log_warn(f"is_connected check failed: {e}")
            return False

    @final
    async def on_connected(self) -> None:
        """
        Vendor callback: connection is ready.
        The base class validates the state machine and emits CONNECTED.
        """
        await self._emit_connection_transition(
            self._connection_machine.try_connected(),
            already_done="on_connected: already connected, skip.",
        )

    @final
    async def on_disconnected(
        self,
        *,
        code: int = 0,
        message: str = "closed",
        vendor_info: ModuleErrorVendorInfo | None = None,
    ) -> None:
        """
        Vendor notification: connection closed (including connect failure).
        The base class checks the state machine and emits DISCONNECTED.
        """
        await self._emit_connection_transition(
            self._connection_machine.try_disconnected(code=code, message=message),
            already_done="on_disconnected: already disconnected, skip.",
            vendor_info=vendor_info,
        )

    async def _emit_connection_transition(
        self,
        transition: ConnectionStatusTransition | None,
        *,
        already_done: str,
        vendor_info: ModuleErrorVendorInfo | None = None,
    ) -> None:
        if transition is None:
            if self.ten_env is not None:
                self.ten_env.log_debug(already_done)
            return

        if not transition.valid and self.ten_env is not None:
            self.ten_env.log_warn(
                f"invalid connection transition: {transition.last} -> {transition.current}"
            )

        await self._send_connection_status_changed(
            transition, vendor_info=vendor_info
        )

    async def _send_connection_status_changed(
        self,
        transition: ConnectionStatusTransition,
        *,
        vendor_info: ModuleErrorVendorInfo | None = None,
    ) -> None:
        if self.ten_env is None:
            return

        event = ModuleConnectionStatusChanged(
            id=self.uuid,
            module=ModuleType.ASR,
            vendor_info=vendor_info or ModuleErrorVendorInfo(vendor=self.vendor()),
            current=transition.current,
            last=transition.last,
            code=transition.code,
            message=transition.message,
            metadata=self._build_report_metadata(),
        )

        connection_data = Data.create(DATA_OUT_CONNECTION_STATUS_CHANGED)
        connection_data.set_property_from_json(None, event.model_dump_json())
        await self.ten_env.send_data(connection_data)
        self.ten_env.log_info(
            f"send connection_status_changed: {event.model_dump(mode='json')}",
            category=LOG_CATEGORY_KEY_POINT,
        )

    async def _ensure_connection(self) -> None:
        """
        Establish connection if not already connected.
        """
        async with self._connection_lock:
            if self._safe_is_connected():
                if self.ten_env is not None:
                    self.ten_env.log_debug(
                        "ensure_connection: already connected, skip."
                    )
                return

            await self.start_connection()

    async def _handle_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        frame_buf = audio_frame.get_buf()
        if not frame_buf:
            ten_env.log_warn("send_frame: empty pcm_frame detected.")
            return

        if not self._safe_is_connected():
            ten_env.log_debug("send_frame: service not connected.")
            buffer_strategy = self.buffer_strategy()
            if isinstance(buffer_strategy, ASRBufferConfigModeKeep):
                byte_limit = buffer_strategy.byte_limit
                while self.buffered_frames_size + len(frame_buf) > byte_limit:
                    if self.buffered_frames.empty():
                        break
                    discard_frame = await self.buffered_frames.get()
                    self.buffered_frames_size -= len(discard_frame.get_buf())
                self.buffered_frames.put_nowait(audio_frame)
                self.buffered_frames_size += len(frame_buf)
            else:
                # Discard mode
                self.audio_timeline.add_dropped_audio(len(frame_buf))

            return

        metadata, _ = audio_frame.get_property_to_json(PROPERTY_KEY_METADATA)
        if metadata:
            try:
                metadata_json = json.loads(metadata)
                self.metadata = metadata_json
                self.session_id = metadata_json.get(
                    PROPERTY_KEY_SESSION_ID, self.session_id
                )
            except json.JSONDecodeError as e:
                ten_env.log_warn(f"send_frame: invalid metadata json - {e}")

        if self.buffered_frames.qsize() > 0:
            ten_env.log_debug(
                f"send_frame: flushing {self.buffered_frames.qsize()} buffered frames."
            )
            while True:
                try:
                    buffered_frame = self.buffered_frames.get_nowait()
                    await self.send_audio(buffered_frame, self.session_id)
                except asyncio.QueueEmpty:
                    break
            self.buffered_frames_size = 0

        success = await self.send_audio(audio_frame, self.session_id)

        if success:
            self.sent_buffer_length += len(frame_buf)

            # Record the timestamp of the first successful send_audio call for TTFW calculation.
            if self.first_audio_time is None:
                self.first_audio_time = asyncio.get_event_loop().time()

    async def _audio_frame_consumer(self) -> None:
        while not self.stopped:
            try:
                audio_frame = await self.audio_frames_queue.get()
                await self._handle_audio_frame(self.ten_env, audio_frame)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.ten_env.log_error(f"Error consuming audio frame: {e}")

    async def _send_audio_actual_send_metrics_task(self) -> None:
        """
        Send audio actual send metrics periodically.
        """
        interval = max(1, self.audio_actual_send_metrics_interval())

        while not self.stopped:
            await asyncio.sleep(interval)
            await self._send_audio_actual_send_metrics()

    def _handle_error_in_audio_timeline(self, error: str) -> None:
        """
        Handle error in audio timeline.
        """
        self.ten_env.log_error(error)
