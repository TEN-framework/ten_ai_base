from abc import abstractmethod
import uuid

from .types import ASRBufferConfig, ASRBufferConfigModeDiscard, ASRBufferConfigModeKeep

from .message import ErrorMessage, ErrorMessageVendorInfo
from .transcription import UserTranscription
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
        self.ten_env: AsyncTenEnv = None
        self.loop = None
        self.session_id = None
        self.sent_buffer_length = 0
        self.buffered_frames = asyncio.Queue[AudioFrame]()
        self.buffered_frames_size = 0
        self.uuid = self.get_uuid()  # Unique identifier for the current final turn

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_info("on_start")
        self.loop = asyncio.get_event_loop()
        self.ten_env = ten_env

        self.loop.create_task(self.start_connection())

    async def on_audio_frame(
        self, ten_env: AsyncTenEnv, frame: AudioFrame
    ) -> None:
        frame_buf = frame.get_buf()
        if not frame_buf:
            ten_env.log_warn("send_frame: empty pcm_frame detected.")
            return

        if not self.is_connected():
            ten_env.log_debug("send_frame: service not connected.")
            buffer_strategy = self.buffer_strategy()
            if isinstance(buffer_strategy, ASRBufferConfigModeKeep):
                byte_limit = buffer_strategy.byte_limit
                while self.buffered_frames_size + len(frame_buf) > byte_limit:
                    if self.buffered_frames.empty():
                        break
                    discard_frame = await self.buffered_frames.get()
                    self.buffered_frames_size -= len(discard_frame.get_buf())
                self.buffered_frames.put_nowait(frame)
                self.buffered_frames_size += len(frame_buf)
            # return anyway if not connected
            return


        metadata, _ = frame.get_property_to_json("metadata")
        if metadata:
            try:
                metadata_json = json.loads(metadata)
                self.session_id = metadata_json.get("session_id", self.session_id)
            except json.JSONDecodeError as e:
                ten_env.log_warn(f"send_frame: invalid metadata json - {e}")

        if self.buffered_frames.qsize() > 0:
            ten_env.log_debug(f"send_frame: flushing {self.buffered_frames.qsize()} buffered frames.")
            while True:
                try:
                    buffered_frame = self.buffered_frames.get_nowait()
                    await self.send_audio(buffered_frame, self.session_id)
                except asyncio.QueueEmpty:
                    break
            self.buffered_frames_size = 0

        success = await self.send_audio(frame, self.session_id)

        if success:
            self.sent_buffer_length += len(frame_buf)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log_debug(f"on_data name: {data_name}")

        if data_name == "finalize":
            if not self.is_connected():
                ten_env.log_warn("finalize: service not connected.")
            await self.finalize(self.session_id)

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_info("on_stop")

        self.stopped = True

        await self.stop_connection()

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_json = cmd.to_json()
        ten_env.log_info(f"on_cmd json: {cmd_json}")

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        cmd_result.set_property_string("detail", "success")
        await ten_env.return_result(cmd_result)

    @abstractmethod
    async def start_connection(self) -> None:
        """Start the connection to the ASR service."""
        raise NotImplementedError(
            "This method should be implemented in subclasses."
        )

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the ASR service is connected."""
        raise NotImplementedError(
            "This method should be implemented in subclasses."
        )

    @abstractmethod
    async def stop_connection(self) -> None:
        """Stop the connection to the ASR service."""
        raise NotImplementedError(
            "This method should be implemented in subclasses."
        )

    @abstractmethod
    def input_audio_sample_rate(self) -> int:
        """
        Get the input audio sample rate in Hz.
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses."
        )

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
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses."
        )

    @abstractmethod
    async def finalize(self, session_id: str | None) -> None:
        """
        Drain the ASR service to ensure all audio frames are processed.
        """
        raise NotImplementedError(
            "This method should be implemented in subclasses."
        )

    async def send_asr_transcription(
        self, transcription: UserTranscription
    ) -> None:
        """
        Send a transcription result as output.
        """
        stable_data = Data.create("asr_result")

        model_json = transcription.model_dump()
        sent_duration = self.calculate_audio_duration(
            self.sent_buffer_length,
            self.input_audio_sample_rate(),
            self.input_audio_channels(),
            self.input_audio_sample_width(),
        )

        stable_data.set_property_from_json(
            None,
            json.dumps(
                {
                    "id": self.uuid,
                    "text": transcription.text,
                    "final": transcription.final,
                    "start_ms": sent_duration + transcription.start_ms,
                    "duration_ms": transcription.duration_ms,
                    "language": transcription.language,
                    "words": model_json.get("words", []),
                    "metadata": {"session_id": self.session_id},
                }
            ),
        )

        await self.ten_env.send_data(stable_data)

        if transcription.final:
            self.uuid = self.get_uuid()  # Reset UUID for the next final turn

    
    async def send_asr_error(
        self, error: ErrorMessage, vendor_info: ErrorMessageVendorInfo | None = None
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
                    "id": "user.transcription",
                    "code": error.code,
                    "message": error.message,
                    "vendor_info": vendorInfo,
                    "metadata": {"session_id": self.session_id},
                }
            ),
        )

        await self.ten_env.send_data(error_data)

    async def send_asr_finalize_end(self, latency_ms: int) -> None:
        """
        Send a signal that the ASR service has finished processing all audio frames.
        """
        drain_data = Data.create("asr_finalize_end")
        drain_data.set_property_from_json(
            None,
            json.dumps(
                {
                    "id": "user.transcription",
                    "latency_ms": latency_ms,
                    "metadata": {"session_id": self.session_id},
                }
            ),
        )

        await self.ten_env.send_data(drain_data)

    def calculate_audio_duration(
        self,
        bytes_length: int,
        sample_rate: int,
        channels: int = 1,
        sample_width: int = 2,
    ) -> float:
        """
        Calculate audio duration in seconds.

        Parameters:
        - bytes_length: Length of the audio data in bytes
        - sample_rate: Sample rate in Hz (e.g., 16000)
        - channels: Number of audio channels (default: 1 for mono)
        - sample_width: Number of bytes per sample (default: 2 for 16-bit PCM)

        Returns:
        - Duration in seconds
        """
        bytes_per_second = sample_rate * channels * sample_width
        return bytes_length / bytes_per_second


    def get_uuid(self) -> str:
        """
        Get a unique identifier
        """
        return uuid.uuid4().hex