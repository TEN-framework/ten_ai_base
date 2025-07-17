#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import json
from typing import AsyncGenerator
from ten_ai_base.struct import TTSTextInput, TTSTextResult
from ten_ai_base.tts2 import AsyncTTS2BaseExtension
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
    ) -> AsyncGenerator[bytes, None]:
        """
        This method is called when the TTS request is made.
        It should yield audio data bytes.
        """
        audio_data_bytes = [3, 100, 7]
        for b in audio_data_bytes:
            yield bytearray(b)
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


    def synthesize_audio_sample_rate(self):
        return self.config.sample_rate