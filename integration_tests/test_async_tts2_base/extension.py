#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import json
from typing import AsyncGenerator
from ten_ai_base.struct import TTSTextInput, TTSTextResult
from ten_ai_base.tts2 import AsyncTTS2BaseExtension
from ten_ai_base.message import TTSAudioEndReason
from ten_runtime import (
    AsyncTenEnv,
    Data,
)
from ten_ai_base import (
    BaseConfig,
)
from dataclasses import dataclass
import asyncio


@dataclass
class TestAsyncTTS2Config(BaseConfig):
    sample_rate: int = 16000

    # TODO: add extra config fields here


class TestAsyncTTS2Extension(AsyncTTS2BaseExtension):
    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        await super().on_start(ten_env)

        # initialize configuration
        self.config = await TestAsyncTTS2Config.create_async(ten_env=ten_env)
        ten_env.log_info(f"config: {self.config}")

        """Implement this method to construct and start your resources."""
        ten_env.log_debug("TODO: on_start")


    async def request_tts(
        self, t: TTSTextInput
    ) -> None:
        """
        This method is called when the TTS request is made.
        It should yield audio data bytes.
        """
        # Send audio_start to set current_audio_request_id (required for metadata)
        await self.send_tts_audio_start(request_id=t.request_id)

        audio_data_bytes = [3, 100, 7]
        for b in audio_data_bytes:
            await self.send_tts_audio_data(bytearray(b))
            await asyncio.sleep(0.1)  # Simulate async delay

        await self.send_tts_text_result(
            t=TTSTextResult(
                request_id=t.request_id,
                text=t.text,
                text_result_end=True,
                start_ms=0,
                duration_ms=0,
                words=[],
                metadata=t.metadata,
            )
        )

        # For this simple test extension, finish request after processing each text chunk
        # In a real TTS extension, you would only finish when text_input_end is True
        if t.text_input_end:
            # Send audio_end event
            await self.send_tts_audio_end(
                request_id=t.request_id,
                request_event_interval_ms=300,  # 3 * 100ms sleep
                request_total_audio_duration_ms=0,  # No actual audio duration tracking in this test
                reason=TTSAudioEndReason.REQUEST_END,
            )

            # Complete the request state transition
            await self.finish_request(
                request_id=t.request_id,
                reason=TTSAudioEndReason.REQUEST_END,
            )

    def vendor(self):
        return "sample_vendor"

    def synthesize_audio_sample_rate(self):
        return self.config.sample_rate