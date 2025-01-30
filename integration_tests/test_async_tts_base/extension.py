#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten import (
    TenEnv,
    AsyncTenEnv,
)
from ten_ai_base import (
    AsyncTTSBaseExtension, BaseConfig
)
from dataclasses import dataclass


@dataclass
class TestAsyncTTSConfig(BaseConfig):
    # TODO: add extra config fields here
    pass


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

    async def on_request_tts(self, ten_env: AsyncTenEnv, input_text: str, end_of_segment: bool) -> None:
        ten_env.log_debug("on_request_tts")

    async def on_cancel_tts(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_cancel_tts")
