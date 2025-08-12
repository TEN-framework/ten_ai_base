#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""ASR base class: connection, buffering, metrics and result helpers."""
from abc import abstractmethod
import asyncio
from functools import wraps
import json
import os
from typing import Any, final
import uuid

from ten_runtime import (
    AsyncExtension,
    AsyncTenEnv,
    Cmd,
    Data,
    AudioFrame,
    StatusCode,
    CmdResult,
)

from .const import (
    DATA_IN_ASR_FINALIZE,
    DATA_OUT_ASR_FINALIZE_END,
    DATA_OUT_METRICS,
    PROPERTY_KEY_DUMP,
    PROPERTY_KEY_DUMP_PATH,
    PROPERTY_KEY_METADATA,
    PROPERTY_KEY_SESSION_ID,
)
from .dumper import Dumper
from .message import (
    ModuleError,
    ModuleErrorCode,
    ModuleErrorVendorInfo,
    ModuleMetricKey,
    ModuleMetrics,
    ModuleType,
)
from .struct import ASRResult
from .timeline import AudioTimeline
from .types import ASRBufferConfig, ASRBufferConfigModeDiscard, ASRBufferConfigModeKeep


class AsyncASRBaseExtension(
    AsyncExtension
):  # pylint: disable=too-many-instance-attributes, too-many-public-methods
    """Asynchronous base class for ASR modules."""

    def __init__(self, name: str):
        super().__init__(name)

        self.stopped = False
        self.ten_env: AsyncTenEnv = None  # type: ignore
        self.session_id = None
        self.finalize_id = None
        self.sent_buffer_length = 0
        self.buffered_frames = asyncio.Queue[AudioFrame]()
        self.buffered_frames_size = 0
        self.audio_frames_queue = asyncio.Queue[AudioFrame]()
        self.audio_timeline = AudioTimeline()
        self.dumper: Dumper | None = None
        self.audio_actual_send_metrics_task: asyncio.Task[None] | None = None
        self.uuid = self._get_uuid()  # Unique identifier for the current final turn

        # States for TTFW calculation
        self.first_audio_time: float | None = (
            None  # Record the timestamp of the first audio send
        )
        self.ttfw_sent = False  # Track if TTFW has been sent

        # States for TTLW calculation
        self.last_finalize_time: float | None = None

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        self.ten_env = ten_env
        asyncio.create_task(self._audio_frame_consumer())

        enable_dump, err = await ten_env.get_property_bool(PROPERTY_KEY_DUMP)
        if err:
            ten_env.log_info(f"dump not set, disable dump: {err}")
        elif enable_dump:
            dump_path, err = await ten_env.get_property_string(PROPERTY_KEY_DUMP_PATH)
            if err:
                ten_env.log_warn(f"dump_path not set, use current directory: {err}")
                dump_path = "."

            dump_file_path = os.path.join(dump_path, self.dump_file_name())
            self.dumper = Dumper(dump_file_path, None)

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        if self.dumper:
            await self.dumper.close()

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_info("on_start")

        # Create a task to send audio actual send metrics
        self.audio_actual_send_metrics_task = asyncio.create_task(
            self._send_audio_actual_send_metrics_task()
        )

        await self.start_connection()

    async def on_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        await self.audio_frames_queue.put(audio_frame)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log_debug(f"on_data name: {data_name}")

        if data_name == DATA_IN_ASR_FINALIZE:
            if not self.is_connected():
                ten_env.log_warn("asr_finalize: service not connected.")

            finalize_id, err = data.get_property_string("finalize_id")
            if err:
                ten_env.log_error(f"asr_finalize: failed to get finalize_id: {err}")
                return

            self.finalize_id = finalize_id
            self.last_finalize_time = asyncio.get_event_loop().time()

            await self.finalize(self.session_id)

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_info("on_stop")

        self.stopped = True

        await self.stop_connection()

        if self.audio_actual_send_metrics_task:
            self.audio_actual_send_metrics_task.cancel()
            self.audio_actual_send_metrics_task = None

        await self._send_audio_actual_send_metrics()

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_info(f"on_cmd json: {cmd_name}")

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        cmd_result.set_property_string("detail", "success")
        await ten_env.return_result(cmd_result)

    @abstractmethod
    def vendor(self) -> str:
        """Get the name of the ASR vendor."""
        raise NotImplementedError("This method should be implemented in subclasses.")

    def dump_file_name(self) -> str:
        """Return the base dump filename."""
        return f"{self.vendor()}_{self.name}_out.pcm"

    @abstractmethod
    async def start_connection(self) -> None:
        """Start the connection to the ASR service."""
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

    # Automatically wrap subclass start_connection to update dumper session first
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        orig = cls.__dict__.get("start_connection")
        if orig is None:
            return

        # Only wrap coroutine functions
        @wraps(orig)
        async def wrapped(self: AsyncASRBaseExtension, *args, **kw):
            try:
                if self.dumper is not None:
                    await self.dumper.update_session()
            except Exception as e:  # pylint: disable=broad-exception-caught
                if self.ten_env is not None:
                    self.ten_env.log_error(f"auto update_session failed: {e}")
            return await orig(self, *args, **kw)

        setattr(cls, "start_connection", wrapped)

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
        if self.session_id is not None:
            asr_result.metadata[PROPERTY_KEY_SESSION_ID] = self.session_id

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

        model_json = asr_result.model_dump(exclude_none=True)

        stable_data.set_property_from_json(
            None,
            json.dumps(model_json),
        )

        await self.ten_env.send_data(stable_data)

        if asr_result.final:
            self.uuid = self._get_uuid()  # Reset UUID for the next final turn

    @final
    async def send_asr_error(
        self,
        code: ModuleErrorCode,
        message: str,
        vendor_info: ModuleErrorVendorInfo | None = None,
    ) -> None:
        """
        Send an error message related to ASR processing.
        """
        error_data = Data.create("error")

        module_error = ModuleError(
            id=self.uuid,
            module=ModuleType.ASR,
            code=code.value,
            message=message,
            metadata={
                PROPERTY_KEY_SESSION_ID: self.session_id or "",
            },
        )

        if vendor_info:
            module_error.vendor_info = ModuleErrorVendorInfo(
                vendor=self.vendor(),
                code=vendor_info.code,
                message=vendor_info.message,
            )

        error_data.set_property_from_json(
            None,
            module_error.model_dump_json(exclude_none=True),
        )

        await self.ten_env.send_data(error_data)

    @final
    async def send_asr_finalize_end(self) -> None:
        """
        Send a signal that the ASR service has finished processing all audio frames.
        """
        drain_data = Data.create(DATA_OUT_ASR_FINALIZE_END)
        drain_data.set_property_from_json(
            None,
            json.dumps(
                {
                    "finalize_id": self.finalize_id,
                    "metadata": (
                        {}
                        if self.session_id is None
                        else {PROPERTY_KEY_SESSION_ID: self.session_id}
                    ),
                }
            ),
        )

        await self.ten_env.send_data(drain_data)

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

        metrics = ModuleMetrics(
            module=ModuleType.ASR,
            vendor=self.vendor(),
            metrics={ModuleMetricKey.ASR_ACTUAL_SEND: actual_send},
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
                    "metadata": (
                        {}
                        if self.session_id is None
                        else {PROPERTY_KEY_SESSION_ID: self.session_id}
                    ),
                }
            ),
        )

        await self.ten_env.send_data(metrics_data)

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

    async def _handle_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        frame_buf = audio_frame.get_buf()
        if not frame_buf:
            ten_env.log_warn("send_frame: empty pcm_frame detected.")
            return

        if not self.is_connected():
            ten_env.log_verbose("send_frame: service not connected.")
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
            # return anyway if not connected
            return

        metadata, _ = audio_frame.get_property_to_json(PROPERTY_KEY_METADATA)
        if metadata:
            try:
                metadata_json = json.loads(metadata)
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
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.ten_env.log_error(f"Error consuming audio frame: {e}")

    async def _send_audio_actual_send_metrics_task(self) -> None:
        """
        Send audio actual send metrics periodically.
        """
        interval = max(1, self.audio_actual_send_metrics_interval())

        while not self.stopped:
            await asyncio.sleep(interval)
            await self._send_audio_actual_send_metrics()
