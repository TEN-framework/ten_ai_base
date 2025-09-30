#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from abc import ABC, abstractmethod
import asyncio
import json
import traceback
import uuid

from .helper import AsyncQueue
from .message import (
    ModuleError,
    ModuleMetricKey,
    ModuleMetrics,
    ModuleType,
    TTSAudioEndReason,
)

from .struct import TTSFlush, TTSTextInput, TTSTextResult
from ten_runtime import (
    AsyncExtension,
    Data,
)
from ten_runtime.async_ten_env import AsyncTenEnv
from ten_runtime.audio_frame import AudioFrame, AudioFrameDataFmt
from ten_runtime.cmd import Cmd
from ten_runtime.cmd_result import CmdResult, StatusCode
from ten_ai_base.const import LOG_CATEGORY_VENDOR
from ten_ai_base.const import LOG_CATEGORY_KEY_POINT

DATA_TTS_TEXT_INPUT = "tts_text_input"
DATA_TTS_TEXT_RESULT = "tts_text_result"
DATA_FLUSH = "tts_flush"
DATA_FLUSH_RESULT = "tts_flush_end"


class AsyncTTS2BaseExtension(AsyncExtension, ABC):
    """
    Base class for implementing a Text-to-Speech Extension.
    This class provides a basic implementation for converting text to speech.
    It automatically handles the processing of tts requests.
    Use begin_send_audio_out, send_audio_out, end_send_audio_out to send the audio data to the output.
    Override on_request_tts to implement the TTS logic.
    """

    # Create the queue for message processing
    def __init__(self, name: str):
        super().__init__(name)
        self.ten_env: AsyncTenEnv = None  # type: ignore
        self.input_queue = AsyncQueue()
        self.current_task = None
        self.loop_task = None
        self.leftover_bytes = b""
        self.session_id = None

        # metrics every 5 seconds
        self.output_characters = 0
        self.input_characters = 0
        self.recv_audio_duration = 0
        self.recv_audio_chunks_len = 0
        # metrics for request level
        self.total_output_characters = 0
        self.total_input_characters = 0
        self.total_recv_audio_duration = 0
        self.total_recv_audio_chunks_len = 0

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        await super().on_init(ten_env)
        self.ten_env = ten_env

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        await super().on_start(ten_env)
        if self.loop_task is None:
            self.loop = asyncio.get_event_loop()
            self.loop_task = self.loop.create_task(self._process_input_queue(ten_env))

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        # send laster time before stop
        await self.send_usage_metrics()
        await super().on_stop(ten_env)
        await self._flush_input_items()
        if self.loop_task:
            self.loop_task.cancel()
        await self.input_queue.put(None)  # Signal the loop to stop processing

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        await super().on_deinit(ten_env)

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_info(f"on_cmd json: {cmd_name}")

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        # Get the necessary properties
        data_name = data.get_name()
        ten_env.log_debug(f"on_data:{data_name}")

        if data.get_name() == DATA_TTS_TEXT_INPUT:
            data_payload, err = data.get_property_to_json("")
            if err:
                raise RuntimeError(f"Failed to get data payload: {err}")

            try:
                t = TTSTextInput.model_validate_json(data_payload)
            except Exception as e:
                ten_env.log_warn(f"invalid data {data_name} payload, err {e}")
                return
            self.ten_env.log_info(
                f"on_data tts_text_input:  {json.dumps(json.loads(data_payload), ensure_ascii=False)}",
                category=LOG_CATEGORY_KEY_POINT,
            )
            # Start an asynchronous task for handling tts
            await self.input_queue.put(t)
        if data.get_name() == DATA_FLUSH:
            data_payload, err = data.get_property_to_json("")
            if err:
                raise RuntimeError(f"Failed to get data payload: {err}")

            try:
                t = TTSFlush.model_validate_json(data_payload)
            except Exception as e:
                ten_env.log_warn(f"invalid data {data_name} payload, err {e}")
                return
            ten_env.log_info(
                f"receive tts_flush {data_payload} ",
                category=LOG_CATEGORY_KEY_POINT,
            )
            await self._flush_input_items()
            flush_result = Data.create(DATA_FLUSH_RESULT)
            json_data = json.dumps(
                {
                    "flush_id": t.flush_id,
                    "metadata": t.metadata,
                }
            )
            flush_result.set_property_from_json(None, json_data)

            ten_env.log_info(
                f"send tts_flush_end {json_data}",
                category=LOG_CATEGORY_KEY_POINT,
            )
            await ten_env.send_data(flush_result)
            ten_env.log_debug("on_data sent flush result")

    async def _flush_input_items(self):
        """Flushes the self.queue and cancels the current task."""
        # Flush the queue using the new flush method
        await self.input_queue.flush()

        # Cancel the current task if one is running
        await self._cancel_current_task()

    async def _cancel_current_task(self) -> None:
        """Called when the TTS request is cancelled."""
        if self.current_task:
            self.current_task.cancel()
            self.current_task = None
        self.leftover_bytes = b""

    async def _process_input_queue(self, ten_env: AsyncTenEnv) -> None:
        """Asynchronously process queue items one by one."""
        while True:
            # Wait for an item to be available in the queue
            t: TTSTextInput = await self.input_queue.get()
            if t is None:
                break

            try:
                await self.request_tts(t)
            except asyncio.CancelledError:
                ten_env.log_info(f"Task cancelled: {t.text}")
            except Exception as err:
                ten_env.log_error(
                    f"Task failed: {t.text}, err: {traceback.format_exc()}"
                )

    async def send_tts_audio_data(self, audio_data: bytes, timestamp: int = 0) -> None:
        """End sending audio out."""
        try:
            sample_rate = self.synthesize_audio_sample_rate()
            bytes_per_sample = self.synthesize_audio_sample_width()
            number_of_channels = self.synthesize_audio_channels()
            # Combine leftover bytes with new audio data
            combined_data = self.leftover_bytes + audio_data

            # Check if combined_data length is odd
            if len(combined_data) % (bytes_per_sample * number_of_channels) != 0:
                # Save the last incomplete frame
                valid_length = len(combined_data) - (
                    len(combined_data) % (bytes_per_sample * number_of_channels)
                )
                self.leftover_bytes = combined_data[valid_length:]
                combined_data = combined_data[:valid_length]
            else:
                self.leftover_bytes = b""

            if combined_data:
                f = AudioFrame.create("pcm_frame")
                f.set_sample_rate(sample_rate)
                f.set_bytes_per_sample(bytes_per_sample)
                f.set_number_of_channels(number_of_channels)
                f.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
                f.set_samples_per_channel(
                    len(combined_data) // (bytes_per_sample * number_of_channels)
                )
                f.alloc_buf(len(combined_data))
                f.set_timestamp(timestamp)
                buff = f.lock_buf()
                buff[:] = combined_data
                f.unlock_buf(buff)
                await self.ten_env.send_audio_frame(f)
        except Exception as e:
            self.ten_env.log_error(f"error send audio frame, {traceback.format_exc()}")

    async def send_tts_text_result(self, t: TTSTextResult) -> None:
        data = Data.create(DATA_TTS_TEXT_RESULT)
        data.set_property_from_json("", t.model_dump_json())
        await self.ten_env.send_data(data)

    async def send_tts_ttfb_metrics(
        self,
        request_id: str,
        ttfb_ms: int,
        turn_id: int = -1,
        extra_metadata: dict = None,
    ) -> None:
        # basic metadata
        metadata = {
            "session_id": self.session_id or "",
            "turn_id": turn_id,
        }

        # if there is extra metadata, add it to the basic metadata
        if extra_metadata:
            metadata.update(extra_metadata)

        metrics = ModuleMetrics(
            id=self.get_uuid(),
            module=ModuleType.TTS,
            vendor=self.vendor(),
            metrics={ModuleMetricKey.TTS_TTFB: ttfb_ms},
            metadata=metadata,
        )
        self.ten_env.log_info(
            f"tts_ttfb:  {ttfb_ms} of request_id: {request_id}",
            category=LOG_CATEGORY_KEY_POINT,
        )
        await self.send_metrics(metrics, request_id)

    async def send_tts_audio_start(self, request_id: str, turn_id: int = -1) -> None:
        data = Data.create("tts_audio_start")
        json_data = json.dumps(
            {
                "request_id": request_id,
                "metadata": {
                    "session_id": self.session_id or "",
                    "turn_id": turn_id,
                },
            }
        )
        data.set_property_from_json(None, json_data)
        self.ten_env.log_info(
            f"tts_audio_start:  {json_data} of request_id: {request_id}",
            category=LOG_CATEGORY_KEY_POINT,
        )
        await self.ten_env.send_data(data)

    async def send_tts_audio_end(
        self,
        request_id: str,
        request_event_interval_ms: int,
        request_total_audio_duration_ms: int,
        turn_id: int = -1,
        reason: TTSAudioEndReason = TTSAudioEndReason.REQUEST_END,
    ) -> None:
        data = Data.create("tts_audio_end")
        json_data = json.dumps(
            {
                "request_id": request_id,
                "request_event_interval_ms": request_event_interval_ms,
                "request_total_audio_duration_ms": request_total_audio_duration_ms,
                "reason": reason.value,
                "metadata": {
                    "session_id": self.session_id or "",
                    "turn_id": turn_id,
                },
            }
        )
        data.set_property_from_json(None, json_data)
        self.ten_env.log_info(
            f"tts_audio_end:  {json_data} of request_id: {request_id}",
            category=LOG_CATEGORY_KEY_POINT,
        )
        await self.ten_env.send_data(data)

    async def send_tts_error(self, request_id: str | None, error: ModuleError) -> None:
        """
        Send an error message related to ASR processing.
        """
        error_data = Data.create("error")

        vendor_info = error.vendor_info
        vendorInfo = None
        if vendor_info:
            vendorInfo = {
                "vendor": vendor_info.vendor,
                "code": vendor_info.code,
                "message": vendor_info.message,
            }
        json_data = json.dumps(
            {
                "id": request_id or "",
                "code": error.code,
                "module": ModuleType.TTS,
                "message": error.message,
                "vendor_info": vendorInfo or {},
                "metadata": {"session_id": self.session_id or ""},
            }
        )
        error_data.set_property_from_json(
            None,
            json_data,
        )
        self.ten_env.log_error(
            f"tts_error:  msg: 	{json_data}",
            category=LOG_CATEGORY_KEY_POINT,
        )
        await self.ten_env.send_data(error_data)

    async def send_char_audio_metrics(self, request_id: str = ""):
        await self.send_usage_metrics(request_id)

    # send when tts audio end
    async def send_usage_metrics(self, request_id: str = ""):
        await self.metrics_calculate_duration()
        metrics = ModuleMetrics(
            id=self.get_uuid(),
            module=ModuleType.TTS,
            vendor=self.vendor(),
            metrics={
                "output_characters": self.output_characters,
                "input_characters": self.input_characters,
                "recv_audio_duration": self.recv_audio_duration,
                "total_output_characters": self.total_output_characters,
                "total_input_characters": self.total_input_characters,
                "total_recv_audio_duration": self.total_recv_audio_duration,
            },
        )
        await self.send_metrics(metrics, request_id)
        self.metrics_reset()

    async def send_metrics(self, metrics: ModuleMetrics, request_id: str = ""):
        data = Data.create("metrics")
        self.ten_env.log_info(
            f"tts_metrics:  {metrics} of request_id: {request_id}",
            category=LOG_CATEGORY_KEY_POINT,
        )
        data.set_property_from_json(None, metrics.model_dump_json())
        await self.ten_env.send_data(data)

    async def metrics_calculate_duration(self) -> None:
        self.recv_audio_duration = (
            self.recv_audio_chunks_len
            / self.synthesize_audio_channels()
            * 1000
            / self.synthesize_audio_sample_width()
        ) / self.synthesize_audio_sample_rate()
        self.total_recv_audio_duration = (
            self.total_recv_audio_chunks_len
            / self.synthesize_audio_channels()
            * 1000
            / self.synthesize_audio_sample_width()
        ) / self.synthesize_audio_sample_rate()

    def metrics_add_output_characters(self, characters: int) -> None:
        self.output_characters += characters
        self.total_output_characters += characters

    def metrics_add_input_characters(self, characters: int) -> None:
        self.input_characters += characters
        self.total_input_characters += characters

    def metrics_add_recv_audio_chunks(self, chunks: bytes) -> None:
        self.total_recv_audio_chunks_len += len(chunks)
        self.recv_audio_chunks_len += len(chunks)

    def metrics_reset(self) -> None:
        self.output_characters = 0
        self.input_characters = 0
        self.recv_audio_duration = 0
        self.recv_audio_chunks_len = 0

    async def metrics_connect_delay(self, connect_delay_ms: int):
        data = Data.create("metrics")
        metrics = ModuleMetrics(
            id=self.get_uuid(),
            module=ModuleType.TTS,
            vendor=self.vendor(),
            metrics={
                "connect_delay": connect_delay_ms,
            },
        )
        self.ten_env.log_debug(f"metrics_connect_delay: {metrics}")
        data.set_property_from_json(None, metrics.model_dump_json())
        await self.ten_env.send_data(data)

    @abstractmethod
    def vendor(self) -> str:
        """
        Get the vendor name of the TTS implementation.
        This is used for metrics and error reporting.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    @abstractmethod
    async def request_tts(self, t: TTSTextInput) -> None:
        """
        Called when a new input item is available in the queue. Override this method to implement the TTS request logic.
        Use send_audio_out to send the audio data to the output when the audio data is ready.
        """
        raise NotImplementedError("request_tts must be implemented in the subclass")

    @abstractmethod
    def synthesize_audio_sample_rate(self) -> int:
        """
        Get the input audio sample rate in Hz.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    def synthesize_audio_channels(self) -> int:
        """
        Get the number of audio channels for input.
        Default is 1 (mono).
        """
        return 1

    def synthesize_audio_sample_width(self) -> int:
        """
        Get the sample width in bytes for input audio.
        Default is 2 (16-bit PCM).
        """
        return 2

    def get_uuid(self) -> str:
        """
        Get a unique identifier
        """
        return uuid.uuid4().hex
