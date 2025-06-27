#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten_runtime import (
    AsyncTenEnv,
)
from ten_ai_base import (
    AsyncTTSBaseExtension,
    BaseConfig,
    AssistantTranscription,
)
from dataclasses import dataclass
import asyncio


@dataclass
class TestAsyncTTSConfig(BaseConfig):
    sample_rate: int = 16000

    # TODO: add extra config fields here


class TestAsyncTTSExtension(AsyncTTSBaseExtension):
    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        await super().on_start(ten_env)

        # initialize configuration
        self.config = await TestAsyncTTSConfig.create_async(ten_env=ten_env)
        ten_env.log_info(f"config: {self.config}")

        """Implement this method to construct and start your resources."""
        ten_env.log_debug("TODO: on_start")

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        await super().on_stop(ten_env)

        """Implement this method to stop and destruct your resources."""
        ten_env.log_debug("TODO: on_stop")

    async def on_request_tts(
        self, ten_env: AsyncTenEnv, t: AssistantTranscription
    ) -> None:
        ten_env.log_debug(f"on_request_tts, text [{t.text}]")

        # mock text-to-speech
        audio_data_bytes = [3, 100, 7]
        for b in audio_data_bytes:
            audio_data = bytearray(b)
            await self.send_audio_out(
                ten_env=ten_env,
                audio_data=audio_data,
                sample_rate=self.config.sample_rate,
            )
            await asyncio.sleep(0.1)

    async def on_cancel_tts(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_cancel_tts")
