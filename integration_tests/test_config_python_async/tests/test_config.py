#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

from ten_runtime import AsyncExtensionTester, AsyncTenEnvTester, Cmd, CmdResult, StatusCode

import pytest
import asyncio
import json
import math


@pytest.fixture
def sample_property():
    return {
        "c_int": 1,
        "c_str": "abc",
        "c_float": 1.5,
        "c_bool": True,
        "c_str_enum": "example_1"
    }


class ExtensionTesterBasicTypesTestConfig(AsyncExtensionTester):
    async def on_cmd(self, ten_env_tester: AsyncTenEnvTester, cmd: Cmd) -> None:

        cmd_name = cmd.get_name()
        if cmd_name != "test_cmd":
            await ten_env_tester.return_result(CmdResult.create(StatusCode.OK, cmd))
            return

        cmd_prop, err = cmd.get_property_to_json("")
        if err:
            raise RuntimeError(f"Failed to get property to JSON: {err}")
        prop_json = json.loads(cmd_prop)
        ten_env_tester.log_debug(f"prop_json: {prop_json}")

        assert prop_json["c_int"] == 1
        assert prop_json["c_str"] == "abc"
        assert math.isclose(prop_json["c_float"], 1.5)
        assert prop_json["c_bool"] == True
        assert prop_json["c_str_enum"] == "example_1"

        await ten_env_tester.return_result(CmdResult.create(StatusCode.OK, cmd))

        ten_env_tester.stop_test()


def test_config_sync(sample_property):
    tester = ExtensionTesterBasicTypesTestConfig()
    tester.set_test_mode_single(
        "test_config_python_async", json.dumps(sample_property))
    tester.run()
