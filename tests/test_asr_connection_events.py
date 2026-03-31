#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

import asyncio
import json

import pytest

pytest.importorskip("ten_runtime")

asr_module = pytest.importorskip("ten_ai_base.asr")
const_module = pytest.importorskip("ten_ai_base.const")
message_module = pytest.importorskip("ten_ai_base.message")

AsyncASRBaseExtension = asr_module.AsyncASRBaseExtension
DATA_OUT_CONNECTED = const_module.DATA_OUT_CONNECTED
DATA_OUT_DISCONNECTED = const_module.DATA_OUT_DISCONNECTED
ModuleType = message_module.ModuleType


class FakeTenEnv:
    def __init__(self):
        self.sent_data = []

    async def send_data(self, data):
        self.sent_data.append(data)

    def log_info(self, *args, **kwargs):
        pass

    def log_debug(self, *args, **kwargs):
        pass


class DummyASR(AsyncASRBaseExtension):
    def __new__(cls, name="dummy_asr"):
        return super().__new__(cls, name)

    def __init__(self, name="dummy_asr"):
        super().__init__(name)

    def vendor(self) -> str:
        return "dummy_vendor"

    async def start_connection(self) -> None:
        return None

    def is_connected(self) -> bool:
        return False

    async def stop_connection(self) -> None:
        return None

    def input_audio_sample_rate(self) -> int:
        return 16000

    async def send_audio(self, frame, session_id):
        return True

    async def finalize(self, session_id):
        return None


def _decode_data(data):
    content, err = data.get_property_to_json(None)
    assert not err
    return data.get_name(), json.loads(content)


def test_send_connected_emits_payload_with_metadata():
    extension = DummyASR()
    extension.ten_env = FakeTenEnv()
    extension.uuid = "connection-id"
    extension.metadata = {"session_id": "session-1", "trace_id": "trace-1"}

    asyncio.run(extension.send_connected())

    assert len(extension.ten_env.sent_data) == 1
    name, payload = _decode_data(extension.ten_env.sent_data[0])
    assert name == DATA_OUT_CONNECTED
    assert payload == {
        "id": "connection-id",
        "module": ModuleType.ASR.value,
        "vendor": "dummy_vendor",
        "metadata": {"session_id": "session-1", "trace_id": "trace-1"},
    }


def test_send_disconnected_emits_payload_with_metadata():
    extension = DummyASR()
    extension.ten_env = FakeTenEnv()
    extension.uuid = "connection-id"
    extension.metadata = {"session_id": "session-1", "trace_id": "trace-1"}
    extension._connection_event_state = True

    asyncio.run(extension.send_disconnected())

    assert len(extension.ten_env.sent_data) == 1
    name, payload = _decode_data(extension.ten_env.sent_data[0])
    assert name == DATA_OUT_DISCONNECTED
    assert payload == {
        "id": "connection-id",
        "module": ModuleType.ASR.value,
        "vendor": "dummy_vendor",
        "metadata": {"session_id": "session-1", "trace_id": "trace-1"},
    }


def test_connection_events_are_idempotent_and_support_reconnect():
    extension = DummyASR()
    extension.ten_env = FakeTenEnv()
    extension.uuid = "connection-id"

    async def _exercise_events():
        await extension.send_connected()
        await extension.send_connected()
        await extension.send_disconnected()
        await extension.send_disconnected()
        await extension.send_connected()

    asyncio.run(_exercise_events())

    assert [data.get_name() for data in extension.ten_env.sent_data] == [
        DATA_OUT_CONNECTED,
        DATA_OUT_DISCONNECTED,
        DATA_OUT_CONNECTED,
    ]


def test_send_connected_uses_empty_metadata_when_unset():
    extension = DummyASR()
    extension.ten_env = FakeTenEnv()
    extension.uuid = "connection-id"

    asyncio.run(extension.send_connected())

    _, payload = _decode_data(extension.ten_env.sent_data[0])
    assert payload["metadata"] == {}
