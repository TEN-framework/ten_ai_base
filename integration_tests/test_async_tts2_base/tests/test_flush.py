#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

from ten_runtime import (
    AsyncExtensionTester,
    AsyncTenEnvTester,
    Cmd,
    CmdResult,
    StatusCode,
    Data,
    AudioFrame,
    AudioFrameDataFmt,
)

import pytest
import asyncio
import json
import math


class ExtensionTesterFlush(AsyncExtensionTester):
    def __init__(self, sample_rate) -> None:
        super().__init__()
        self.target_sample_rate = sample_rate
        self.received_frames = 0

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        text_data = Data.create("text_data")
        text_data.set_property_string("text", "How are you today?")
        await ten_env.send_data(text_data)


        await asyncio.sleep(1)  # Simulate async initialization delay

        flush_data = Data.create("flush")
        flush_data.set_property_from_json(
            None, json.dumps({"metadata": {"session_id": "test_session"}})
        )
        await ten_env.send_data(flush_data)

    async def on_audio_frame(
        self, ten_env: AsyncTenEnvTester, audio_frame: AudioFrame
    ) -> None:
        frame_name = audio_frame.get_name()
        if frame_name != "pcm_frame":
            return

        assert audio_frame.get_sample_rate() == self.target_sample_rate
        assert audio_frame.get_bytes_per_sample() == 2
        assert audio_frame.get_number_of_channels() == 1
        assert audio_frame.get_data_fmt() == AudioFrameDataFmt.INTERLEAVE
        assert audio_frame.get_samples_per_channel() > 0
        assert (
            len(audio_frame.get_buf())
            == audio_frame.get_samples_per_channel() * 2
        )

        self.received_frames += 1
        # should not receive any new audio frame after flush
        assert self.received_frames < 2

    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug(f"on_cmd: {cmd_name}")
        await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))

        if cmd_name != "flush":
            return

        # received flush cmd
        ten_env.stop_test()

    async def on_data(self, ten_env: AsyncTenEnvTester, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log_debug(f"on_data for tester: {data_name}")

        if data_name == "flush_result":
            # received flush result
            ten_env.log_info("Flush completed successfully.")
            ten_env.stop_test()
        


def test_flush():
    # TODO: fix later

    tester = ExtensionTesterFlush(16000)
    tester.set_test_mode_single("test_async_tts2_base")
    tester.run()
