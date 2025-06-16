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


class ExtensionTesterCmdReturn(AsyncExtensionTester):
    async def on_start(self, ten_env_tester: AsyncTenEnvTester) -> None:

        # make sure any cmd will be returned properly
        test_cmd = Cmd.create("test_cmd")
        _, ten_err = await ten_env_tester.send_cmd(test_cmd)
        assert not ten_err

        ten_env_tester.stop_test()


def test_cmd_return():
    tester = ExtensionTesterCmdReturn()
    tester.set_test_mode_single("test_async_tts_base")
    tester.run()
