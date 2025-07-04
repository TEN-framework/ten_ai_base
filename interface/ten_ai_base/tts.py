#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from abc import ABC, abstractmethod
import asyncio
import traceback

from ten_runtime import (
    AsyncExtension,
    Data,
)
from ten_runtime.async_ten_env import AsyncTenEnv
from ten_runtime.audio_frame import AudioFrame, AudioFrameDataFmt
from ten_runtime.cmd import Cmd
from ten_runtime.cmd_result import CmdResult, StatusCode
from .const import (
    CMD_IN_FLUSH,
    CMD_OUT_FLUSH,
    DATA_IN_PROPERTY_END_OF_SEGMENT,
    DATA_IN_PROPERTY_TEXT,
    DATA_IN_PROPERTY_QUIET,
)
from .types import TTSPcmOptions
from .helper import AsyncQueue
from .transcription import AssistantTranscription, Word

DATA_TRANSCRIPT = "text_data"


class AsyncTTSBaseExtension(AsyncExtension, ABC):
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
        self.queue = AsyncQueue()
        self.current_task = None
        self.loop_task = None
        self.leftover_bytes = b""

        self.enable_words = False

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        await super().on_init(ten_env)

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        await super().on_start(ten_env)

        if self.loop_task is None:
            self.loop = asyncio.get_event_loop()
            self.loop_task = self.loop.create_task(self._process_queue(ten_env))

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        await super().on_stop(ten_env)
        self.loop_task.cancel()

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        await super().on_deinit(ten_env)

    async def on_cmd(self, async_ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        async_ten_env.log_debug(f"on_cmd name: {cmd_name}")

        if cmd_name == CMD_IN_FLUSH:
            await self.on_cancel_tts(async_ten_env)
            await self.flush_input_items(async_ten_env)
            await async_ten_env.send_cmd(Cmd.create(CMD_OUT_FLUSH))
            async_ten_env.log_debug("on_cmd sent flush")
            status_code, detail = StatusCode.OK, "success"
            cmd_result = CmdResult.create(status_code, cmd)
            cmd_result.set_property_string("detail", detail)
            await async_ten_env.return_result(cmd_result)
        else:
            status_code, detail = StatusCode.OK, "success"
            cmd_result = CmdResult.create(status_code, cmd)
            cmd_result.set_property_string("detail", detail)
            await async_ten_env.return_result(cmd_result)

    async def on_data(self, async_ten_env: AsyncTenEnv, data: Data) -> None:
        # Get the necessary properties
        data_name = data.get_name()
        async_ten_env.log_debug(f"on_data:{data_name}")

        if data.get_name() == DATA_TRANSCRIPT:
            data_payload, err = data.get_property_to_json("")
            if err:
                raise RuntimeError(f"Failed to get data payload: {err}")
            async_ten_env.log_debug(
                f"on_data {data_name}, payload {data_payload}"
            )

            try:
                t = AssistantTranscription.model_validate_json(data_payload)
            except Exception as e:
                async_ten_env.log_warn(
                    f"invalid data {data_name} payload, err {e}"
                )
                return

            if t.object != "assistant.transcription":
                async_ten_env.log_warn(
                    f"invalid data {data_name} payload, object {t.object}"
                )
                return

            t.source = "tts"
            if t.quiet:
                if self.enable_words and not t.words:
                    t.words = [
                        Word(
                            word=t.text,
                            start_ms=t.start_ms,
                            duration_ms=0,
                            stable=True,
                        )
                    ]
                data = Data.create(DATA_TRANSCRIPT)
                data.set_property_from_json("", t.model_dump_json())
                await async_ten_env.send_data(data)
                async_ten_env.log_debug("ignore quiet text")
                return

            # Start an asynchronous task for handling tts
            await self.queue.put(t)

    async def flush_input_items(self, ten_env: AsyncTenEnv):
        """Flushes the self.queue and cancels the current task."""
        # Flush the queue using the new flush method
        await self.queue.flush()

        # Cancel the current task if one is running
        if self.current_task:
            ten_env.log_info("Cancelling the current task during flush.")
            self.current_task.cancel()

    async def send_audio_out(
        self, ten_env: AsyncTenEnv, audio_data: bytes, **args: TTSPcmOptions
    ) -> None:
        """End sending audio out."""
        sample_rate = args.get("sample_rate", 16000)
        bytes_per_sample = args.get("bytes_per_sample", 2)
        number_of_channels = args.get("number_of_channels", 1)
        try:
            # Combine leftover bytes with new audio data
            combined_data = self.leftover_bytes + audio_data

            # Check if combined_data length is odd
            if (
                len(combined_data) % (bytes_per_sample * number_of_channels)
                != 0
            ):
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
                    len(combined_data)
                    // (bytes_per_sample * number_of_channels)
                )
                f.alloc_buf(len(combined_data))
                buff = f.lock_buf()
                buff[:] = combined_data
                f.unlock_buf(buff)
                await ten_env.send_audio_frame(f)
        except Exception as e:
            ten_env.log_error(
                f"error send audio frame, {traceback.format_exc()}"
            )

    async def send_transcript_out(
        self, ten_env: AsyncTenEnv, t: AssistantTranscription
    ) -> None:
        data = Data.create(DATA_TRANSCRIPT)
        data.set_property_from_json("", t.model_dump_json())
        await ten_env.send_data(data)

    @abstractmethod
    async def on_request_tts(
        self, ten_env: AsyncTenEnv, t: AssistantTranscription
    ) -> None:
        """
        Called when a new input item is available in the queue. Override this method to implement the TTS request logic.
        Use send_audio_out to send the audio data to the output when the audio data is ready.
        """
        pass

    @abstractmethod
    async def on_cancel_tts(self, ten_env: AsyncTenEnv) -> None:
        """Called when the TTS request is cancelled."""
        pass

    async def _process_queue(self, ten_env: AsyncTenEnv):
        """Asynchronously process queue items one by one."""
        while True:
            # Wait for an item to be available in the queue
            t: AssistantTranscription = await self.queue.get()
            if t is None:
                break

            try:
                self.current_task = asyncio.create_task(
                    self.on_request_tts(ten_env, t)
                )
                await self.current_task  # Wait for the current task to finish or be cancelled
                self.current_task = None
            except asyncio.CancelledError:
                ten_env.log_info(f"Task cancelled: {t.text}")
            except Exception as err:
                ten_env.log_error(
                    f"Task failed: {t.text}, err: {traceback.format_exc()}"
                )
