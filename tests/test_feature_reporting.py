#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


def _create_fake_ten_runtime_modules() -> dict[str, types.ModuleType]:
    ten_runtime = types.ModuleType("ten_runtime")

    class AsyncTenEnv:
        pass

    class AsyncExtension:
        def __init__(self, name: str) -> None:
            self.name = name

        async def on_init(self, ten_env) -> None:
            return None

        async def on_start(self, ten_env) -> None:
            return None

        async def on_stop(self, ten_env) -> None:
            return None

        async def on_deinit(self, ten_env) -> None:
            return None

    class Data:
        def __init__(self, name: str) -> None:
            self._name = name
            self._json_properties: dict[str | None, str] = {}

        @staticmethod
        def create(name: str):
            return Data(name)

        def get_name(self) -> str:
            return self._name

        def set_property_from_json(self, key, value) -> None:
            self._json_properties[key] = value

        def get_property_to_json(self, key):
            return self._json_properties[key], None

    class AudioFrame:
        @staticmethod
        def create(name: str):
            return types.SimpleNamespace(name=name)

    class AudioFrameDataFmt:
        INTERLEAVE = "interleave"

    class Cmd:
        pass

    class CmdResult:
        @staticmethod
        def create(status_code, cmd):
            return types.SimpleNamespace(status_code=status_code, cmd=cmd)

    class StatusCode:
        OK = "ok"
        ERROR = "error"

    ten_runtime.AsyncTenEnv = AsyncTenEnv
    ten_runtime.AsyncExtension = AsyncExtension
    ten_runtime.Data = Data
    ten_runtime.AudioFrame = AudioFrame
    ten_runtime.AudioFrameDataFmt = AudioFrameDataFmt
    ten_runtime.Cmd = Cmd
    ten_runtime.CmdResult = CmdResult
    ten_runtime.StatusCode = StatusCode

    async_ten_env_module = types.ModuleType("ten_runtime.async_ten_env")
    async_ten_env_module.AsyncTenEnv = AsyncTenEnv

    audio_frame_module = types.ModuleType("ten_runtime.audio_frame")
    audio_frame_module.AudioFrame = AudioFrame
    audio_frame_module.AudioFrameDataFmt = AudioFrameDataFmt

    cmd_module = types.ModuleType("ten_runtime.cmd")
    cmd_module.Cmd = Cmd

    cmd_result_module = types.ModuleType("ten_runtime.cmd_result")
    cmd_result_module.CmdResult = CmdResult
    cmd_result_module.StatusCode = StatusCode

    return {
        "ten_runtime": ten_runtime,
        "ten_runtime.async_ten_env": async_ten_env_module,
        "ten_runtime.audio_frame": audio_frame_module,
        "ten_runtime.cmd": cmd_module,
        "ten_runtime.cmd_result": cmd_result_module,
    }


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_feature_reporting_symbols():
    fake_runtime_modules = _create_fake_ten_runtime_modules()
    original_runtime_modules = {
        name: sys.modules.get(name) for name in fake_runtime_modules
    }
    sys.modules.update(fake_runtime_modules)

    package_root = (
        Path(__file__).resolve().parents[1] / "interface" / "ten_ai_base"
    )
    package_name = "ten_ai_base"
    package_module_names = [
        package_name,
        f"{package_name}.const",
        f"{package_name}.message",
        f"{package_name}.helper",
        f"{package_name}.struct",
        f"{package_name}.types",
        f"{package_name}.connection_status",
        f"{package_name}.timeline",
        f"{package_name}.utils",
        f"{package_name}.features",
        f"{package_name}.asr",
        f"{package_name}.tts2",
    ]
    original_package_modules = {
        name: sys.modules.get(name) for name in package_module_names
    }
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_root)]
    sys.modules[package_name] = package

    try:
        for module in [
            "const",
            "message",
            "helper",
            "struct",
            "types",
            "connection_status",
            "timeline",
            "utils",
            "features",
            "asr",
            "tts2",
        ]:
            _load_module(
                f"{package_name}.{module}", package_root / f"{module}.py"
            )

        return {
            "AsyncASRBaseExtension": sys.modules[
                f"{package_name}.asr"
            ].AsyncASRBaseExtension,
            "AsyncTTS2BaseExtension": sys.modules[
                f"{package_name}.tts2"
            ].AsyncTTS2BaseExtension,
            "ProvideFeaturesPayload": sys.modules[
                f"{package_name}.message"
            ].ProvideFeaturesPayload,
            "DATA_OUT_PROVIDE_FEATURES": sys.modules[
                f"{package_name}.const"
            ].DATA_OUT_PROVIDE_FEATURES,
            "send_provide_features": sys.modules[
                f"{package_name}.features"
            ].send_provide_features,
        }
    finally:
        for name, module in original_package_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        for name, module in original_runtime_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


SYMBOLS = _load_feature_reporting_symbols()
AsyncASRBaseExtension = SYMBOLS["AsyncASRBaseExtension"]
AsyncTTS2BaseExtension = SYMBOLS["AsyncTTS2BaseExtension"]
ProvideFeaturesPayload = SYMBOLS["ProvideFeaturesPayload"]
DATA_OUT_PROVIDE_FEATURES = SYMBOLS["DATA_OUT_PROVIDE_FEATURES"]
send_provide_features = SYMBOLS["send_provide_features"]


def _make_mock_ten_env(sent_data: list[tuple[str, dict]]) -> MagicMock:
    async def capture_send_data(data) -> None:
        payload = json.loads(data.get_property_to_json(None)[0])
        sent_data.append((data.get_name(), payload))

    ten_env = MagicMock()
    ten_env.send_data = AsyncMock(side_effect=capture_send_data)
    ten_env.log_info = MagicMock()
    ten_env.log_warn = MagicMock()
    ten_env.log_debug = MagicMock()
    ten_env.log_error = MagicMock()
    return ten_env


async def _cancel_task(task: asyncio.Task | None) -> None:
    if task is None:
        return

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


class _FeatureASRExtension(AsyncASRBaseExtension):
    def vendor(self) -> str:
        return "feature-asr"

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


class _FeatureTTSExtension(AsyncTTS2BaseExtension):
    def vendor(self) -> str:
        return "feature-tts"

    async def request_tts(self, t) -> None:
        return None

    def synthesize_audio_sample_rate(self) -> int:
        return 16000


def test_send_provide_features_emits_expected_payload():
    asyncio.run(async_test_send_provide_features_emits_expected_payload())


async def async_test_send_provide_features_emits_expected_payload():
    sent_data: list[tuple[str, dict]] = []
    ten_env = _make_mock_ten_env(sent_data)

    await send_provide_features(ten_env, {"asr.vendor": "feature-asr"})

    assert sent_data == [
        (
            DATA_OUT_PROVIDE_FEATURES,
            ProvideFeaturesPayload(
                features={"asr.vendor": "feature-asr"}
            ).model_dump(),
        )
    ]


def test_asr_on_start_reports_vendor_feature():
    asyncio.run(async_test_asr_on_start_reports_vendor_feature())


async def async_test_asr_on_start_reports_vendor_feature():
    sent_data: list[tuple[str, dict]] = []
    ext = _FeatureASRExtension("feature-asr")
    ext.ten_env = _make_mock_ten_env(sent_data)
    ext.auto_connect = False

    try:
        await ext.on_start(ext.ten_env)
        assert sent_data[0] == (
            DATA_OUT_PROVIDE_FEATURES,
            {"features": {"asr.vendor": "feature-asr"}},
        )
    finally:
        await _cancel_task(ext.audio_actual_send_metrics_task)


def test_tts2_on_start_reports_vendor_feature():
    asyncio.run(async_test_tts2_on_start_reports_vendor_feature())


async def async_test_tts2_on_start_reports_vendor_feature():
    sent_data: list[tuple[str, dict]] = []
    ext = _FeatureTTSExtension("feature-tts")
    ten_env = _make_mock_ten_env(sent_data)

    try:
        await ext.on_start(ten_env)
        assert sent_data[0] == (
            DATA_OUT_PROVIDE_FEATURES,
            {"features": {"tts.vendor": "feature-tts"}},
        )
    finally:
        await _cancel_task(ext.loop_task)
