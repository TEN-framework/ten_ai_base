#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

from ten_runtime import AsyncExtensionTester, AsyncTenEnvTester, Cmd, CmdResult, StatusCode, Data, AudioFrame, AudioFrameDataFmt

import pytest
import asyncio
import json
import math


class ExtensionTesterBasicTextToSpeech(AsyncExtensionTester):
    def __init__(self, sample_rate) -> None:
        super().__init__()
        self.target_sample_rate = sample_rate
        self.received_frames = 0

    async def on_start(self, ten_env_tester: AsyncTenEnvTester) -> None:
        text_data = Data.create("text_data")
        text_data.set_property_string("text", "How are you today?")
        await ten_env_tester.send_data(text_data)

    async def on_audio_frame(
        self, ten_env_tester: AsyncTenEnvTester, audio_frame: AudioFrame
    ) -> None:
        frame_name = audio_frame.get_name()
        if frame_name != "pcm_frame":
            return

        assert audio_frame.get_sample_rate() == self.target_sample_rate
        assert audio_frame.get_bytes_per_sample() == 2
        assert audio_frame.get_number_of_channels() == 1
        assert audio_frame.get_data_fmt() == AudioFrameDataFmt.INTERLEAVE
        assert audio_frame.get_samples_per_channel() > 0
        assert len(audio_frame.get_buf()
                   ) == audio_frame.get_samples_per_channel() * 2

        self.received_frames += 1
        if self.received_frames == 3:
            ten_env_tester.stop_test()


def test_basic_text_to_speech_16k():
    property_json = {
        "sample_rate": 16000
    }
    tester = ExtensionTesterBasicTextToSpeech(16000)
    tester.set_test_mode_single(
        "test_async_tts_base", json.dumps(property_json))
    tester.run()


def test_basic_text_to_speech_32k():
    property_json = {
        "sample_rate": 32000
    }
    tester = ExtensionTesterBasicTextToSpeech(32000)
    tester.set_test_mode_single(
        "test_async_tts_base", json.dumps(property_json))
    tester.run()


def test_basic_text_to_speech_48k():
    property_json = {
        "sample_rate": 48000
    }
    tester = ExtensionTesterBasicTextToSpeech(48000)
    tester.set_test_mode_single(
        "test_async_tts_base", json.dumps(property_json))
    tester.run()
