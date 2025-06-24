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

        await self.send_audio(frame)

    async def on_data(self, ten_env: AsyncTenEnvTester, data: Data) -> None:
        json_data, _ = data.get_property_to_json("asr_result")

        ten_env.log_info(
            f"on_data json: {json_data}"
        )

        # assert stream_id == 123
        # assert user_id == "123"

        ten_env.stop_test()

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
    async def send_audio(
        self, frame: AudioFrame
    ) -> None:
        """
        Send an audio frame to the ASR service.
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

        stable_data.set_property_from_json(None, json.dumps({
            "id": "user.transcription",
            "text": transcription.text,
            "final": transcription.final,
            "start_ms": transcription.start_ms,
            "duration_ms": transcription.duration_ms,
            "language": transcription.language,
            "words": model_json.get("words", []),
            "metadata": {
                "session_id": self.session_id
            }
        }))

        asyncio.create_task(self.ten_env.send_data(stable_data))

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

        asyncio.create_task(self.ten_env.send_data(error_data))


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

        asyncio.create_task(self.ten_env.send_data(drain_data))