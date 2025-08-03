#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from abc import ABC, abstractmethod
import traceback
from typing import AsyncGenerator

from .struct import LLMInput, LLMResponse
from ten_runtime import (
    AsyncExtension,
)
from ten_runtime.async_ten_env import AsyncTenEnv
from ten_runtime.cmd import Cmd
from ten_runtime.cmd_result import CmdResult, StatusCode


class AsyncLLM2BaseExtension(AsyncExtension, ABC):
    """
    Base class for implementing a Language Model Extension.
    This class provides a basic implementation for processing chat completions.
    It automatically handles the registration of tools and the processing of chat completions.
    Use queue_input_item to queue input items for processing.
    Use flush_input_items to flush the queue and cancel the current task.
    Override on_call_chat_completion and on_data_chat_completion to implement the chat completion logic.
    """

    # Create the queue for message processing

    def __init__(self, name: str):
        super().__init__(name)
        self.ten_env: AsyncTenEnv = None

    async def on_init(self, async_ten_env: AsyncTenEnv) -> None:
        await super().on_init(async_ten_env)

    async def on_start(self, async_ten_env: AsyncTenEnv) -> None:
        await super().on_start(async_ten_env)
        self.ten_env = async_ten_env

    async def on_stop(self, async_ten_env: AsyncTenEnv) -> None:
        await super().on_stop(async_ten_env)

    async def on_deinit(self, async_ten_env: AsyncTenEnv) -> None:
        await super().on_deinit(async_ten_env)

    async def on_cmd(self, async_ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        """
        handle default commands
        return True if the command is handled, False otherwise
        """
        cmd_name = cmd.get_name()
        async_ten_env.log_debug(f"on_cmd name22 {cmd_name}")
        try:
            if cmd_name == "chat_completion":
                payload, err = cmd.get_property_to_json(None)
                if err:
                    raise RuntimeError(f"Failed  to get payload: {err}")
                args = LLMInput.model_validate_json(
                    payload
                )
                response = self.on_call_chat_completion(
                    async_ten_env, args
                )

                async for llm_choice in response:
                    # If the response is a final output, we can return it directly
                    cmd_result = CmdResult.create(StatusCode.OK, cmd)
                    cmd_result.set_property_from_json(
                        None, llm_choice.model_dump_json()
                    )
                    cmd_result.set_final(False)
                    await async_ten_env.return_result(cmd_result)

                cmd_result = CmdResult.create(StatusCode.OK, cmd)
                cmd_result.set_final(True)
                await async_ten_env.return_result(cmd_result)
            else:
                await async_ten_env.return_result(
                    CmdResult.create(StatusCode.OK, cmd)
                )
        except Exception as e:
            async_ten_env.log_error(f"on_cmd error: {traceback.format_exc()}")
            await async_ten_env.return_result(
                CmdResult.create(StatusCode.ERROR, cmd)
            )

    @abstractmethod
    def on_call_chat_completion(
        self, async_ten_env: AsyncTenEnv, input: LLMInput
    ) -> AsyncGenerator[LLMResponse, None]:
        """Called when a chat completion is requested by cmd call. Implement this method to process the chat completion."""
        raise NotImplementedError(
            "on_call_chat_completion must be implemented in the subclass"
        )