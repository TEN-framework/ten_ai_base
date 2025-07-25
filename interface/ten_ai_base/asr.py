from abc import abstractmethod
from typing import final
import uuid

from .struct import ASRResult
from .types import ASRBufferConfig, ASRBufferConfigModeDiscard, ASRBufferConfigModeKeep

from .message import ModuleError, ModuleErrorVendorInfo, ModuleMetrics, ModuleType
from .const import (
    DATA_IN_ASR_FINALIZE,
    DATA_OUT_ASR_FINALIZE_END,
    DATA_OUT_METRICS,
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


class AsyncASRBaseExtension(AsyncExtension):
    def __init__(self, name: str):
        super().__init__(name)

        self.stopped = False
        self.ten_env: AsyncTenEnv = None  # type: ignore
        self.loop: asyncio.AbstractEventLoop | None = None
        self.session_id = None
        self.finalize_id = None
        self.sent_buffer_length = 0
        self.buffered_frames = asyncio.Queue[AudioFrame]()
        self.buffered_frames_size = 0
        self.audio_frames_queue = asyncio.Queue[AudioFrame]()
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
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self._audio_frame_consumer())

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_info("on_start")

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

    def buffer_strategy(self) -> ASRBufferConfig:
        """
        Get the buffer strategy for audio frames when not connected
        """
        return ASRBufferConfigModeDiscard()

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

        model_json = asr_result.model_dump()

        stable_data.set_property_from_json(
            None,
            json.dumps(model_json),
        )

        await self.ten_env.send_data(stable_data)

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

        error_data.set_property_from_json(
            None,
            json.dumps(
                {
                    "id": self.uuid,
                    "module": ModuleType.ASR,
                    "code": error.code,
                    "message": error.message,
                    "vendor_info": vendorInfo,
                    "metadata": {PROPERTY_KEY_SESSION_ID: self.session_id},
                }
            ),
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
                    "metadata": {PROPERTY_KEY_SESSION_ID: self.session_id},
                }
            ),
        )

        await self.ten_env.send_data(drain_data)

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
                    "metadata": {PROPERTY_KEY_SESSION_ID: self.session_id},
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
            metrics={"ttfw": ttfw},
        )

        await self._send_asr_metrics(metrics)

    async def _send_metrics_ttlw(self, ttlw: int) -> None:
        """
        Send metrics for time to last word.
        """
        metrics = ModuleMetrics(
            module=ModuleType.ASR,
            vendor=self.vendor(),
            metrics={"ttlw": ttlw},
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
            except Exception as e:
                self.ten_env.log_error(f"Error consuming audio frame: {e}")
