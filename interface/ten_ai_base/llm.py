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
from ten_runtime.cmd import Cmd
from ten_runtime.cmd_result import CmdResult, StatusCode
from .const import (
    CMD_PROPERTY_TOOL,
    CMD_TOOL_REGISTER,
    DATA_OUT_NAME,
    DATA_OUT_PROPERTY_END_OF_SEGMENT,
    DATA_OUT_PROPERTY_TEXT,
    CMD_CHAT_COMPLETION_CALL,
)
from .types import LLMCallCompletionArgs, LLMDataCompletionArgs, LLMToolMetadata
from .helper import AsyncQueue
import json

DATA_LLM_IN_SET_PROMPT = "llm_client_set_prompt"


class AsyncLLMBaseExtension(AsyncExtension, ABC):
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
        self.queue = AsyncQueue()
        self.available_tools: list[LLMToolMetadata] = []
        self.available_tools_lock = (
            asyncio.Lock()
        )  # Lock to ensure thread-safe access
        self.current_task = None
        self.hit_default_cmd = False
        self.loop_task = None
        self.loop = None
        self.dynamic_prompt: str | None = None  # Dynamic prompt set by prompt_template extension
        self.ten_env: AsyncTenEnv = None  # type: ignore

    async def on_init(self, async_ten_env: AsyncTenEnv) -> None:
        await super().on_init(async_ten_env)
        self.ten_env = async_ten_env

    async def on_start(self, async_ten_env: AsyncTenEnv) -> None:
        await super().on_start(async_ten_env)

        if self.loop_task is None:
            self.loop = asyncio.get_event_loop()
            self.loop_task = self.loop.create_task(
                self._process_queue(async_ten_env)
            )

    async def on_stop(self, async_ten_env: AsyncTenEnv) -> None:
        await super().on_stop(async_ten_env)
        await self.queue.put(None)

    async def on_deinit(self, async_ten_env: AsyncTenEnv) -> None:
        await super().on_deinit(async_ten_env)

    async def on_data(self, async_ten_env: AsyncTenEnv, data: Data) -> None:
        """Handle incoming data messages."""
        data_name = data.get_name()
        async_ten_env.log_debug(f"on_data name: {data_name}")
        if data_name == DATA_LLM_IN_SET_PROMPT:
            prompt_json, _ = data.get_property_to_json(None)
            prompt_data = json.loads(prompt_json)
            new_prompt = prompt_data.get("prompt", "")
            self.dynamic_prompt = new_prompt
            async_ten_env.log_info(f"Dynamic prompt set: {new_prompt[:100]}...")
            await self.on_prompt_update(new_prompt)

    async def on_prompt_update(self, prompt: str) -> None:
        """
        Called when a dynamic prompt is set by the prompt_template extension.
        Subclasses can override this method to apply the new prompt.
        Default implementation does nothing - subclass should update conversation context if needed.
        """
        pass

    def get_prompt(self, config_prompt: str) -> str:
        """
        Get the effective prompt to use.
        Returns dynamic_prompt if set by prompt_template extension,
        otherwise returns the config_prompt from property.json.
        """
        if self.dynamic_prompt is not None:
            return self.dynamic_prompt
        return config_prompt

    async def on_cmd(self, async_ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        """
        handle default commands
        return True if the command is handled, False otherwise
        """
        cmd_name = cmd.get_name()
        async_ten_env.log_debug(f"on_cmd name {cmd_name}")
        if cmd_name == CMD_TOOL_REGISTER:
            try:
                tool_metadata_json, err = cmd.get_property_to_json(
                    CMD_PROPERTY_TOOL
                )
                if err:
                    raise RuntimeError(f"Failed to  get tool metadata: {err}")
                async_ten_env.log_info(f"register tool: {tool_metadata_json}")
                tool_metadata = LLMToolMetadata.model_validate_json(
                    tool_metadata_json
                )
                async with self.available_tools_lock:
                    self.available_tools.append(tool_metadata)
                await self.on_tools_update(async_ten_env, tool_metadata)
                await async_ten_env.return_result(
                    CmdResult.create(StatusCode.OK, cmd)
                )
            except Exception:
                async_ten_env.log_warn(
                    f"on_cmd failed: {traceback.format_exc()}"
                )
                await async_ten_env.return_result(
                    CmdResult.create(StatusCode.ERROR, cmd)
                )
        elif cmd_name == CMD_CHAT_COMPLETION_CALL:
            try:
                arguments_str, err = cmd.get_property_to_json("arguments")
                if err:
                    raise RuntimeError(f"Failed  to get arguments: {err}")
                args = json.loads(arguments_str)
                response = await self.on_call_chat_completion(
                    async_ten_env, **args
                )
                cmd_result = CmdResult.create(StatusCode.OK, cmd)
                cmd_result.set_property_from_json("response", response)
                await async_ten_env.return_result(cmd_result)
            except Exception as err:
                async_ten_env.log_warn(f"on_cmd failed: {err}")
                await async_ten_env.return_result(
                    CmdResult.create(StatusCode.ERROR, cmd)
                )
        else:
            await async_ten_env.return_result(
                CmdResult.create(StatusCode.OK, cmd)
            )

    async def queue_input_item(
        self, prepend: bool = False, **kargs: LLMDataCompletionArgs
    ):
        """Queues an input item for processing."""
        await self.queue.put(kargs, prepend)

    async def flush_input_items(self, async_ten_env: AsyncTenEnv):
        """Flushes the self.queue and cancels the current task."""
        # Flush the queue using the new flush method
        await self.queue.flush()

        # Cancel the current task if one is running
        if self.current_task:
            async_ten_env.log_info("Cancelling the current task during flush.")
            self.current_task.cancel()

    def send_text_output(
        self, async_ten_env: AsyncTenEnv, sentence: str, end_of_segment: bool
    ):
        try:
            output_data = Data.create(DATA_OUT_NAME)
            output_data.set_property_string(DATA_OUT_PROPERTY_TEXT, sentence)
            output_data.set_property_bool(
                DATA_OUT_PROPERTY_END_OF_SEGMENT, end_of_segment
            )
            asyncio.create_task(async_ten_env.send_data(output_data))
            async_ten_env.log_info(
                f"{'end of segment ' if end_of_segment else ''}sent sentence [{sentence}]"
            )
        except Exception as err:
            async_ten_env.log_warn(
                f"send sentence [{sentence}] failed, err: {err}"
            )

    @abstractmethod
    async def on_call_chat_completion(
        self, async_ten_env: AsyncTenEnv, **kargs: LLMCallCompletionArgs
    ) -> any:
        """Called when a chat completion is requested by cmd call. Implement this method to process the chat completion."""

    @abstractmethod
    async def on_data_chat_completion(
        self, async_ten_env: AsyncTenEnv, **kargs: LLMDataCompletionArgs
    ) -> None:
        """
        Called when a chat completion is requested by data input. Implement this method to process the chat completion.
        Note that this method is stream-based, and it should consider supporting local context caching.
        """

    @abstractmethod
    async def on_tools_update(
        self, async_ten_env: AsyncTenEnv, tool: LLMToolMetadata
    ) -> None:
        """Called when a new tool is registered. Implement this method to process the new tool."""

    async def _process_queue(self, async_ten_env: AsyncTenEnv):
        """Asynchronously process queue items one by one."""
        while True:
            # Wait for an item to be available in the queue
            args = await self.queue.get()
            args = {} if args is None else args
            try:
                async_ten_env.log_info(f"Processing queue item: {args}")
                self.current_task = asyncio.create_task(
                    self.on_data_chat_completion(async_ten_env, **args)
                )
                await self.current_task  # Wait for the current task to finish or be cancelled
            except asyncio.CancelledError:
                async_ten_env.log_info(f"Task cancelled: {args}")
            except Exception:
                async_ten_env.log_error(
                    f"Task failed: {args}, err: {traceback.format_exc()}"
                )
