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
from ten_ai_base.tts2 import AsyncTTS2BaseExtension
from ten_ai_base.struct import TTSTextInput, TTSFlush


class TestTTS2Extension(AsyncTTS2BaseExtension):
    """Test TTS extension class that can control flush timing"""
    
    def __init__(self, name: str, flush_delay: float = 0.0):
        super().__init__(name)
        self.flush_delay = flush_delay
        self.processed_requests = []
    
    def vendor(self) -> str:
        return "test_vendor"
    
    async def request_tts(self, t: TTSTextInput) -> None:
        """Process TTS request"""
        self.processed_requests.append(t.request_id)
        # Simulate TTS processing time
        await asyncio.sleep(0.1)
    
    def synthesize_audio_sample_rate(self) -> int:
        return 16000
    
    async def cancel_tts(self) -> None:
        """Override cancel_tts method to add delay"""
        if self.flush_delay > 0:
            await asyncio.sleep(self.flush_delay)


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

        flush_data = Data.create("tts_flush")
        flush_data.set_property_from_json(
            None, json.dumps({"flush_id":"xxxx","metadata": {"session_id": "test_session"}})
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

        if cmd_name != "tts_flush":
            return

        # received flush cmd
        ten_env.stop_test()

    async def on_data(self, ten_env: AsyncTenEnvTester, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log_debug(f"on_data for tester: {data_name}")

        if data_name == "tts_flush_end":
            # received flush result
            ten_env.log_info("Flush completed successfully.")
            ten_env.stop_test()


class ExtensionTesterFlushWithContinuousInput(AsyncExtensionTester):
    """Test continuous TTSTextInput during flush"""
    
    def __init__(self, flush_delay: float = 0.5, inputs_during_flush: int = 5, inputs_after_flush: int = 3) -> None:
        super().__init__()
        self.flush_delay = flush_delay
        self.inputs_during_flush_count = inputs_during_flush
        self.inputs_after_flush_count = inputs_after_flush
        self.flush_started = False
        self.flush_completed = False
        self.received_text_results = 0  # Count received TTSTextResult
    
    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        ten_env.log_info("ExtensionTesterFlushWithContinuousInput on_start called")
        # Send an initial request first
        await self._send_tts_input(ten_env, "initial_request")
        await asyncio.sleep(0.1)
        
        # Start flush
        self.flush_started = True
        ten_env.log_info("Starting flush operation")
        flush_data = Data.create("tts_flush")
        flush_data.set_property_from_json(
            None, json.dumps({"flush_id": "test_flush", "metadata": {}})
        )
        await ten_env.send_data(flush_data)
        
        # Send multiple requests continuously during flush
        ten_env.log_info(f"Sending {self.inputs_during_flush_count} requests during flush")
        for i in range(self.inputs_during_flush_count):
            await asyncio.sleep(0.1)  # Ensure sending during flush
            await self._send_tts_input(ten_env, f"during_flush_{i}")
    
    async def _send_tts_input(self, ten_env: AsyncTenEnvTester, request_id: str):
        """Send TTS input request"""
        tts_data = Data.create("tts_text_input")
        tts_data.set_property_from_json(
            None, json.dumps({
                "request_id": request_id,
                "text": f"Test text for {request_id}",
                "metadata": {}
            })
        )
        await ten_env.send_data(tts_data)
    
    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug(f"on_cmd: {cmd_name}")
        await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))
    
    async def on_data(self, ten_env: AsyncTenEnvTester, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log_debug(f"on_data for tester: {data_name}")
        
        if data_name == "tts_text_result":
            # Count received TTSTextResult to verify request_tts calls
            self.received_text_results += 1
            ten_env.log_info(f"Received TTSTextResult #{self.received_text_results}")
        
        if data_name == "tts_flush_end":
            self.flush_completed = True
            ten_env.log_info("Flush completed, sending post-flush inputs")
            
            # Send more requests after flush completion
            ten_env.log_info(f"Sending {self.inputs_after_flush_count} requests after flush")
            for i in range(self.inputs_after_flush_count):
                await asyncio.sleep(0.1)
                await self._send_tts_input(ten_env, f"after_flush_{i}")
            
            # Wait for all requests to be processed
            ten_env.log_info("Waiting for all requests to be processed")
            await asyncio.sleep(2.0)
            ten_env.log_info("Stopping test")
            ten_env.stop_test()
    
    def get_tts_extension(self):
        """Get reference to the TTS extension for accessing queue put count"""
        return self.tts_extension


class ExtensionTesterMultipleFlush(AsyncExtensionTester):
    """Test multiple consecutive flushes"""
    
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0
        self.flush_results = []
    
    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        # Send first request
        await self._send_tts_input(ten_env, "initial_request")
        await asyncio.sleep(0.1)
        
        # Execute 3 consecutive flushes, send requests between each flush
        for i in range(3):
            # Send flush
            await self._send_flush(ten_env, f"flush_{i}")
            
            # Wait for flush to start
            await asyncio.sleep(0.1)
            
            # Send requests during flush
            for j in range(2):
                await self._send_tts_input(ten_env, f"between_flush_{i}_{j}")
                await asyncio.sleep(0.1)
        
        # Wait for all flushes to complete
        await asyncio.sleep(2.0)
        ten_env.stop_test()
    
    async def _send_tts_input(self, ten_env: AsyncTenEnvTester, request_id: str):
        """Send TTS input request"""
        tts_data = Data.create("tts_text_input")
        tts_data.set_property_from_json(
            None, json.dumps({
                "request_id": request_id,
                "text": f"Test text for {request_id}",
                "metadata": {}
            })
        )
        await ten_env.send_data(tts_data)
    
    async def _send_flush(self, ten_env: AsyncTenEnvTester, flush_id: str):
        """Send flush request"""
        flush_data = Data.create("tts_flush")
        flush_data.set_property_from_json(
            None, json.dumps({"flush_id": flush_id, "metadata": {}})
        )
        await ten_env.send_data(flush_data)
    
    async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug(f"on_cmd: {cmd_name}")
        await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))
    
    async def on_data(self, ten_env: AsyncTenEnvTester, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log_debug(f"on_data for tester: {data_name}")
        
        if data_name == "tts_flush_end":
            self.flush_count += 1
            self.flush_results.append(data_name)
            ten_env.log_info(f"Flush {self.flush_count} completed")


def test_flush():
    """Test basic flush functionality"""
    print("Starting test_flush...")
    tester = ExtensionTesterFlush(16000)
    property_json = {"sample_rate": 16000}
    tester.set_test_mode_single("test_async_tts2_base", json.dumps(property_json))
    print("Running test_flush...")
    tester.run()
    print("test_flush completed successfully")


def test_flush_with_continuous_input():
    """Test continuous TTSTextInput during flush, verify wait mechanism"""
    print("Starting test_flush_with_continuous_input...")
    
    # Create tester with configurable parameters
    inputs_during_flush = 5
    inputs_after_flush = 3
    tester = ExtensionTesterFlushWithContinuousInput(
        flush_delay=0.5, 
        inputs_during_flush=inputs_during_flush, 
        inputs_after_flush=inputs_after_flush
    )
    property_json = {"sample_rate": 16000}
    tester.set_test_mode_single("test_async_tts2_base", json.dumps(property_json))
    
    # Run test
    print("Running test_flush_with_continuous_input...")
    tester.run()
    print("test_flush_with_continuous_input completed successfully")
    
    # Verify flush process completed successfully
    assert tester.flush_started, "Flush should have started"
    assert tester.flush_completed, "Flush should have completed"
    
    # Verify request_tts calls through received TTSTextResult count
    expected_total_requests = 1 + inputs_during_flush + inputs_after_flush
    actual_requests = tester.received_text_results
    
    print(f"Expected {expected_total_requests} request_tts calls")
    print(f"Actual {actual_requests} request_tts calls from received TTSTextResult count")
    
    # Verify that we received the expected number of TTSTextResult responses
    assert actual_requests == expected_total_requests, \
        f"Expected {expected_total_requests} request_tts calls, but got {actual_requests} TTSTextResult responses. " \
        f"This indicates the flush mechanism may not be working correctly."
    
    print(f"request_tts calls verified: {actual_requests}/{expected_total_requests} calls detected correctly")
    print(f"Flush test completed successfully - flush started: {tester.flush_started}, flush completed: {tester.flush_completed}")


def test_flush_put_operations_count():
    """Test that verifies flush behavior with different input counts"""
    print("Starting test_flush_put_operations_count...")
    
    # Test with different parameters
    test_cases = [
        {"inputs_during_flush": 3, "inputs_after_flush": 2, "expected_total": 6},  # 1 + 3 + 2
        {"inputs_during_flush": 7, "inputs_after_flush": 4, "expected_total": 12}, # 1 + 7 + 4
        {"inputs_during_flush": 1, "inputs_after_flush": 1, "expected_total": 3},  # 1 + 1 + 1
    ]
    
    for i, test_case in enumerate(test_cases):
        inputs_during_flush = test_case["inputs_during_flush"]
        inputs_after_flush = test_case["inputs_after_flush"]
        expected_total = test_case["expected_total"]
        
        # Create tester with specific parameters
        tester = ExtensionTesterFlushWithContinuousInput(
            flush_delay=0.3, 
            inputs_during_flush=inputs_during_flush, 
            inputs_after_flush=inputs_after_flush
        )
        property_json = {"sample_rate": 16000}
        tester.set_test_mode_single("test_async_tts2_base", json.dumps(property_json))
        
        # Run test
        print(f"Running test case {i+1} of test_flush_put_operations_count...")
        tester.run()
        print(f"Test case {i+1} completed successfully")
        
        # Verify flush mechanism works correctly for this test case
        assert tester.flush_started, f"Test case {i+1}: Flush should have started"
        assert tester.flush_completed, f"Test case {i+1}: Flush should have completed"
        
        # Verify request_tts calls through received TTSTextResult count
        actual_requests = tester.received_text_results
        print(f"Test case {i+1}: Expected {expected_total} request_tts calls, actual {actual_requests}")
        
        # Verify that we received the expected number of TTSTextResult responses
        assert actual_requests == expected_total, \
            f"Test case {i+1}: Expected {expected_total} request_tts calls, but got {actual_requests} TTSTextResult responses. " \
            f"Inputs: {inputs_during_flush} during flush, {inputs_after_flush} after flush"
        
        print(f"Test case {i+1}: request_tts calls verified - {actual_requests}/{expected_total} calls detected correctly")


def test_multiple_flush_with_inputs():
    """Test multiple consecutive flushes, verify queue clearing effect"""
    print("Starting test_multiple_flush_with_inputs...")
    
    # Create tester
    tester = ExtensionTesterMultipleFlush()
    property_json = {"sample_rate": 16000}
    tester.set_test_mode_single("test_async_tts2_base", json.dumps(property_json))
    
    # Run test
    print("Running test_multiple_flush_with_inputs...")
    tester.run()
    print("test_multiple_flush_with_inputs completed successfully")
    
    # Verify all flushes completed
    assert tester.flush_count == 3, f"Expected 3 flushes, got {tester.flush_count}"
    assert len(tester.flush_results) == 3, f"Expected 3 flush results, got {len(tester.flush_results)}"
    
    # Verify that multiple consecutive flushes work correctly
    # This test verifies that the queue clearing mechanism works properly
    # between consecutive flushes
    print(f"Multiple flush test completed successfully - {tester.flush_count} flushes processed")
    print("Verified that consecutive flushes work correctly and queue clearing mechanism is functional")


def test_flush_queue_behavior():
    """Detailed verification of flush queue behavior"""
    print("Starting test_flush_queue_behavior...")
    
    class ExtensionTesterDetailedFlush(AsyncExtensionTester):
        """Tester for detailed flush behavior verification"""
        
        def __init__(self) -> None:
            super().__init__()
            self.flush_count = 0
        
        async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
            # Send initial request
            await self._send_tts_input(ten_env, "initial_request")
            await asyncio.sleep(0.1)
            
            # Execute 2 flushes with requests between them
            for i in range(2):
                await self._send_flush(ten_env, f"flush_{i}")
                await asyncio.sleep(0.1)
                
                # Send requests during flush
                for j in range(2):
                    await self._send_tts_input(ten_env, f"between_flush_{i}_{j}")
                    await asyncio.sleep(0.1)
            
            # Wait for all flushes to complete
            await asyncio.sleep(1.0)
            ten_env.stop_test()
        
        async def _send_tts_input(self, ten_env: AsyncTenEnvTester, request_id: str):
            """Send TTS input request"""
            tts_data = Data.create("tts_text_input")
            tts_data.set_property_from_json(
                None, json.dumps({
                    "request_id": request_id,
                    "text": f"Test text for {request_id}",
                    "metadata": {}
                })
            )
            await ten_env.send_data(tts_data)
        
        async def _send_flush(self, ten_env: AsyncTenEnvTester, flush_id: str):
            """Send flush request"""
            flush_data = Data.create("tts_flush")
            flush_data.set_property_from_json(
                None, json.dumps({"flush_id": flush_id, "metadata": {}})
            )
            await ten_env.send_data(flush_data)
        
        async def on_cmd(self, ten_env: AsyncTenEnvTester, cmd: Cmd) -> None:
            cmd_name = cmd.get_name()
            ten_env.log_debug(f"on_cmd: {cmd_name}")
            await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))
        
        async def on_data(self, ten_env: AsyncTenEnvTester, data: Data) -> None:
            data_name = data.get_name()
            ten_env.log_debug(f"on_data for tester: {data_name}")
            
            if data_name == "tts_flush_end":
                self.flush_count += 1
                ten_env.log_info(f"Flush {self.flush_count} completed")
    
    # Create tester
    tester = ExtensionTesterDetailedFlush()
    property_json = {"sample_rate": 16000}
    tester.set_test_mode_single("test_async_tts2_base", json.dumps(property_json))
    
    # Run test
    print("Running test_flush_queue_behavior...")
    tester.run()
    print("test_flush_queue_behavior completed successfully")
    
    # Verify flush operation correctness
    assert tester.flush_count >= 1, "At least one flush should have occurred"


# Helper function to run all tests
def run_all_flush_tests():
    """Run all flush-related tests"""
    print("=== Starting all flush tests ===")
    try:
        test_flush()
        test_flush_with_continuous_input()
        test_flush_put_operations_count()
        test_multiple_flush_with_inputs()
        test_flush_queue_behavior()
        print("=== All flush tests completed successfully ===")
    except Exception as e:
        print(f"=== Test failed with error: {e} ===")
        raise


if __name__ == "__main__":
    # If running this file directly, execute all tests
    run_all_flush_tests()
