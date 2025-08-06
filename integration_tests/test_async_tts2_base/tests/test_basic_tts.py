#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

from ten_ai_base.struct import TTSTextResult
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


class ExtensionTesterBasicTextToSpeech(AsyncExtensionTester):
    def __init__(self, sample_rate) -> None:
        super().__init__()
        self.target_sample_rate = sample_rate
        self.received_frames = 0
        self.received_text_result:TTSTextResult = None

    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        await asyncio.sleep(0.1)
        text_data = Data.create("tts_text_input")
        text_data.set_property_from_json(
            None, json.dumps({
                "request_id": "test_request",
                "text": "Hello, this is a test.",
                "text_input_end": True,
                "metadata": {
                    "session_id": "test_session",
                    "turn_id": 1
                }
            })
        )
        await ten_env.send_data(text_data)

    async def on_data(self, ten_env, data):
        data_name = data.get_name()
        ten_env.log_debug(f"on_data for tester: {data_name}")

        if data_name == "tts_text_result":
            ten_env.log_info("Received TTS text result.")
            
            tts_text_result, _ = data.get_property_to_json(None)
            ten_env.log_info(f"TTS Text Result: {tts_text_result}")
            self.received_text_result = TTSTextResult.model_validate_json(tts_text_result)
        self.check_received(ten_env)

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

        ten_env.log_info(
            f"Received audio frame: {frame_name}, "
            f"Sample Rate: {audio_frame.get_sample_rate()}, "
            f"Bytes Per Sample: {audio_frame.get_bytes_per_sample()}, "
            f"Number of Channels: {audio_frame.get_number_of_channels()}"
            f"Received Frames: {self.received_frames}"
        )
        
        self.check_received(ten_env)

    def check_received(self, ten_env: AsyncTenEnvTester):
        if self.received_frames == 3 and self.received_text_result:
            ten_env.stop_test()

def test_basic_text_to_speech_16k():
    property_json = {"sample_rate": 16000}
    tester = ExtensionTesterBasicTextToSpeech(16000)
    tester.set_test_mode_single(
        "test_async_tts2_base", json.dumps(property_json)
    )
    tester.run()


def test_basic_text_to_speech_32k():
    property_json = {"sample_rate": 32000}
    tester = ExtensionTesterBasicTextToSpeech(32000)
    tester.set_test_mode_single(
        "test_async_tts2_base", json.dumps(property_json)
    )
    tester.run()


def test_basic_text_to_speech_48k():
    property_json = {"sample_rate": 48000}
    tester = ExtensionTesterBasicTextToSpeech(48000)
    tester.set_test_mode_single(
        "test_async_tts2_base", json.dumps(property_json)
    )
    tester.run()
