#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#
import asyncio
import json

from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
    Data,
    TenError,
    TenErrorCode,
)


class ExtensionTesterInterleavedStateMachine(AsyncExtensionTester):
    """Verify buffered interleaved requests enter PROCESSING before finalizing."""

    def __init__(self) -> None:
        super().__init__()
        self.audio_end_request_ids: set[str] = set()

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        await asyncio.sleep(0.1)

        # req2 is intentionally sent while req1 is still processing. The base
        # class buffers req2, then releases it when req1 finishes.
        await self._send_tts_input(
            ten_env,
            request_id="req1",
            text="req1 first chunk",
            text_input_end=False,
        )
        await self._send_tts_input(
            ten_env,
            request_id="req2",
            text="req2 buffered chunk",
            text_input_end=False,
        )
        await self._send_tts_input(
            ten_env,
            request_id="req2",
            text="req2 final chunk",
            text_input_end=True,
        )
        await self._send_tts_input(
            ten_env,
            request_id="req1",
            text="req1 final chunk",
            text_input_end=True,
        )

    async def _send_tts_input(
        self,
        ten_env: AsyncTenEnvTester,
        request_id: str,
        text: str,
        text_input_end: bool,
    ) -> None:
        tts_data = Data.create("tts_text_input")
        tts_data.set_property_from_json(
            None,
            json.dumps(
                {
                    "request_id": request_id,
                    "text": text,
                    "text_input_end": text_input_end,
                    "metadata": {},
                }
            ),
        )
        await ten_env.send_data(tts_data)

    async def on_data(self, ten_env: AsyncTenEnvTester, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log_debug(f"on_data for tester: {data_name}")

        if data_name == "state_check_failed":
            payload, _ = data.get_property_to_json(None)
            ten_env.stop_test(
                TenError.create(
                    TenErrorCode.ErrorCodeGeneric,
                    f"Buffered request did not reach FINALIZING: {payload}",
                )
            )
            return

        if data_name != "tts_audio_end":
            return

        payload, _ = data.get_property_to_json(None)
        audio_end = json.loads(payload)
        self.audio_end_request_ids.add(audio_end["request_id"])

        if self.audio_end_request_ids == {"req1", "req2"}:
            ten_env.stop_test()


def test_interleaved_buffered_request_reaches_processing_before_finalizing():
    property_json = {
        "sample_rate": 16000,
        "require_finalizing_before_end": True,
    }
    tester = ExtensionTesterInterleavedStateMachine()
    tester.set_test_mode_single(
        "test_async_tts2_base", json.dumps(property_json)
    )
    error = tester.run()

    assert (
        error is None
    ), f"Test failed: {error.error_message() if error else 'Unknown error'}"
