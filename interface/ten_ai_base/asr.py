from abc import abstractmethod

from .types import VendorError
from .transcription import UserTranscription
from ten_runtime import (
    AsyncExtension,
    AsyncTenEnv,
    AsyncTenEnvTester,
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

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_info("on_start")
        self.loop = asyncio.get_event_loop()
        self.ten_env = ten_env

        self.loop.create_task(self.start_connection())

    async def on_audio_frame(self, ten_env: AsyncTenEnv, frame: AudioFrame) -> None:
        frame_buf = frame.get_buf()
        if not frame_buf:
            ten_env.log_warn("send_frame: empty pcm_frame detected.")
            return

        if not self.is_connected():
            ten_env.log_debug("send_frame: service not connected.")
            return

        self.session_id, _ = frame.get_property_int("session_id")

        success = await self.send_audio(frame)

        if success:
            self.sent_buffer_length += len(frame_buf)

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

    @abstractmethod
    async def send_audio(
        self, frame: AudioFrame
    ) -> bool:
        """
        Send an audio frame to the ASR service, returning True if successful.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    @abstractmethod
    async def drain(self) -> None:
        """
        Drain the ASR service to ensure all audio frames are processed.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

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
            self.input_audio_sample_width()
        )


        stable_data.set_property_from_json(None, json.dumps({
            "id": "user.transcription",
            "text": transcription.text,
            "final": transcription.final,
            "start_ms": sent_duration + transcription.start_ms,
            "duration_ms":  transcription.duration_ms,
            "language": transcription.language,
            "words": model_json.get("words", []),
            "metadata": {
                "session_id": self.session_id
            }
        }))

        await self.ten_env.send_data(stable_data)

    async def send_asr_error(self, code: int, message: str, error: VendorError) -> None:
        """
        Send an error message related to ASR processing.
        """
        error_data = Data.create("asr_error")
        error_data.set_property_from_json(None, json.dumps({
            "id": "user.transcription",
            "code": code,
            "message": message,
            "vendor_info": error.model_dump(),
            "metadata": {
                "session_id": self.session_id
            }
        }))

        await self.ten_env.send_data(error_data)


    async def send_asr_drain_end(self, latency_ms: int) -> None:
        """
        Send a signal that the ASR service has finished processing all audio frames.
        """
        drain_data = Data.create("asr_drain_end")
        drain_data.set_property_from_json(None, json.dumps({
            "id": "user.transcription",
            "latency_ms": latency_ms,
            "metadata": {
                "session_id": self.session_id
            }
        }))

        await self.ten_env.send_data(drain_data)

    def calculate_audio_duration(self, bytes_length: int, sample_rate: int, channels: int = 1, sample_width: int = 2) -> float:
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
