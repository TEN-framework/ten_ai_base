#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ten_ai_base import (
    AsyncASRBaseExtension,
    ModuleConnectionStatus,
    ModuleError,
    ModuleErrorCode,
    ModuleErrorVendorInfo,
    ModuleMetrics,
    ModuleType,
    VENDOR_METADATA_KEY,
    mask_secret,
)
from ten_ai_base.const import (
    DATA_IN_TRIGGER_CONNECT,
    DATA_OUT_CONNECTION_STATUS_CHANGED,
    DATA_OUT_METRICS,
)
from ten_runtime import Data


class _AudioFrame:
    def __init__(self, buf: bytes):
        self._buf = buf

    def get_buf(self) -> bytes:
        return self._buf

    def get_property_to_json(self, key):
        return None, None


class _MockASRExtension(AsyncASRBaseExtension):
    def vendor(self) -> str:
        return "mock_vendor"

    async def start_connection(self) -> None:
        return None

    def is_connected(self) -> bool:
        return self._connected

    async def stop_connection(self) -> None:
        self._connected = False

    async def send_audio(self, frame, session_id: str | None) -> bool:
        return True

    async def finalize(self, session_id: str | None) -> None:
        return None

    def input_audio_sample_rate(self) -> int:
        return 16000

    def vendor_metadata(self) -> dict:
        return {
            "key": "abcdef123456",
            "url": "wss://example.com/asr",
            "model": "mock-model",
            "region": "cn",
            "mode": "",
        }

    def __init__(self, name: str = "mock_asr"):
        super().__init__(name)
        self._connected = False
        self.sent_data: list[tuple[str, dict]] = []

    async def _capture_send_data(self, data) -> None:
        payload = json.loads(data.get_property_to_json(None)[0])
        self.sent_data.append((data.get_name(), payload))


@pytest.fixture
def asr_ext():
    ext = _MockASRExtension("mock_asr")
    ext.ten_env = MagicMock()
    ext.ten_env.send_data = AsyncMock(side_effect=ext._capture_send_data)
    ext.ten_env.log_info = MagicMock()
    ext.ten_env.log_warn = MagicMock()
    ext.ten_env.log_debug = MagicMock()
    return ext


def test_start_connection_emits_connecting_before_vendor_hook(asr_ext):
    asyncio.run(async_test_start_connection_emits_connecting_before_vendor_hook(asr_ext))


async def async_test_start_connection_emits_connecting_before_vendor_hook(asr_ext):
    await asr_ext.start_connection()

    assert len(asr_ext.sent_data) == 1
    assert asr_ext.sent_data[0][0] == DATA_OUT_CONNECTION_STATUS_CHANGED
    assert asr_ext.sent_data[0][1]["current"] == "connecting"
    assert asr_ext.connection_status == ModuleConnectionStatus.CONNECTING


def test_connection_status_transitions(asr_ext):
    asyncio.run(async_test_connection_status_transitions(asr_ext))


async def async_test_connection_status_transitions(asr_ext):
    await asr_ext._emit_connection_transition(
        asr_ext._connection_machine.try_connecting(),
        already_done="skip",
    )
    assert asr_ext.connection_status == ModuleConnectionStatus.CONNECTING
    assert len(asr_ext.sent_data) == 1
    assert asr_ext.sent_data[0][0] == DATA_OUT_CONNECTION_STATUS_CHANGED
    assert asr_ext.sent_data[0][1]["current"] == "connecting"
    assert asr_ext.sent_data[0][1]["last"] == "disconnected"

    await asr_ext.on_connected()
    assert asr_ext.connection_status == ModuleConnectionStatus.CONNECTED
    assert asr_ext.sent_data[1][1]["current"] == "connected"

    await asr_ext.on_disconnected(
        code=1006,
        message="websocket closed",
        vendor_info=ModuleErrorVendorInfo(
            vendor="mock_vendor",
            code="vendor-1006",
            message="vendor websocket closed",
        ),
    )
    assert asr_ext.connection_status == ModuleConnectionStatus.DISCONNECTED
    assert asr_ext.sent_data[2][1]["current"] == "disconnected"
    assert asr_ext.sent_data[2][1]["code"] == 1006
    assert asr_ext.sent_data[2][1]["message"] == "websocket closed"
    assert asr_ext.sent_data[2][1]["vendor_info"] == {
        "vendor": "mock_vendor",
        "code": "vendor-1006",
        "message": "vendor websocket closed",
    }


def test_connection_status_includes_masked_vendor_metadata(asr_ext):
    asyncio.run(async_test_connection_status_includes_masked_vendor_metadata(asr_ext))


async def async_test_connection_status_includes_masked_vendor_metadata(asr_ext):
    await asr_ext._emit_connection_transition(
        asr_ext._connection_machine.try_connecting(),
        already_done="skip",
    )
    vendor_metadata = asr_ext.sent_data[0][1]["metadata"][VENDOR_METADATA_KEY]
    assert vendor_metadata["key"] == mask_secret("abcdef123456")
    assert vendor_metadata["url"] == "wss://example.com/asr"
    assert vendor_metadata["model"] == "mock-model"


def test_metrics_metadata_includes_vendor_metadata(asr_ext):
    asyncio.run(async_test_metrics_metadata_includes_vendor_metadata(asr_ext))


async def async_test_metrics_metadata_includes_vendor_metadata(asr_ext):
    metrics = ModuleMetrics(
        module=ModuleType.ASR,
        vendor="mock_vendor",
        metrics={"request_time_ms": 10, "response_time_ms": 20},
    )
    await asr_ext._send_asr_metrics(metrics)

    assert len(asr_ext.sent_data) == 1
    assert asr_ext.sent_data[0][0] == DATA_OUT_METRICS
    metadata = asr_ext.sent_data[0][1]["metadata"]
    assert metadata[VENDOR_METADATA_KEY]["key"] == mask_secret("abcdef123456")


def test_error_metadata_includes_vendor_metadata(asr_ext):
    asyncio.run(async_test_error_metadata_includes_vendor_metadata(asr_ext))


async def async_test_error_metadata_includes_vendor_metadata(asr_ext):
    await asr_ext.send_asr_error(
        ModuleError(
            module=ModuleType.ASR,
            code=ModuleErrorCode.NON_FATAL_ERROR,
            message="vendor failed",
        )
    )

    assert len(asr_ext.sent_data) == 1
    metadata = asr_ext.sent_data[0][1]["metadata"]
    assert metadata[VENDOR_METADATA_KEY]["region"] == "cn"


def test_audio_frame_not_connected_log_suppressed_before_trigger_connect(asr_ext):
    asyncio.run(
        async_test_audio_frame_not_connected_log_suppressed_before_trigger_connect(
            asr_ext
        )
    )


async def async_test_audio_frame_not_connected_log_suppressed_before_trigger_connect(
    asr_ext,
):
    asr_ext.auto_connect = False

    await asr_ext._handle_audio_frame(asr_ext.ten_env, _AudioFrame(b"\x00\x01"))

    asr_ext.ten_env.log_debug.assert_not_called()


def test_audio_frame_not_connected_log_after_trigger_connect(asr_ext):
    asyncio.run(async_test_audio_frame_not_connected_log_after_trigger_connect(asr_ext))


async def async_test_audio_frame_not_connected_log_after_trigger_connect(asr_ext):
    asr_ext.auto_connect = False

    await asr_ext.on_data(asr_ext.ten_env, Data.create(DATA_IN_TRIGGER_CONNECT))
    asr_ext.ten_env.log_debug.reset_mock()

    await asr_ext._handle_audio_frame(asr_ext.ten_env, _AudioFrame(b"\x00\x01"))

    asr_ext.ten_env.log_debug.assert_called_once_with(
        "send_frame: service not connected."
    )


class _MinimalASRExtension(AsyncASRBaseExtension):
    """Subclass without vendor_metadata override — uses base default."""

    def vendor(self) -> str:
        return "minimal_vendor"

    async def start_connection(self) -> None:
        return None

    def is_connected(self) -> bool:
        return False

    async def stop_connection(self) -> None:
        return None

    async def send_audio(self, frame, session_id: str | None) -> bool:
        return True

    async def finalize(self, session_id: str | None) -> None:
        return None

    def input_audio_sample_rate(self) -> int:
        return 16000


def test_default_vendor_metadata_does_not_crash():
    asyncio.run(async_test_default_vendor_metadata_does_not_crash())


async def async_test_default_vendor_metadata_does_not_crash():
    ext = _MinimalASRExtension("minimal_asr")
    ext.ten_env = MagicMock()
    ext.ten_env.send_data = AsyncMock()
    ext.ten_env.log_info = MagicMock()
    ext.ten_env.log_warn = MagicMock()
    ext.ten_env.log_debug = MagicMock()

    metadata = ext._build_report_metadata()
    assert metadata[VENDOR_METADATA_KEY] == {}

    await ext._emit_connection_transition(
        ext._connection_machine.try_connecting(),
        already_done="skip",
    )
    ext.ten_env.send_data.assert_awaited_once()
