#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten import (
    AsyncExtension,
    AsyncTenEnv,
    Cmd,
)
from ten_ai_base import BaseConfig
from enum import Enum
from dataclasses import dataclass, asdict
import json


class TestStrEnum(str, Enum):
    DEFAULT = "default"
    EXAMPLE_1 = "example_1"


@dataclass
class BasicTypesTestConfig(BaseConfig):
    c_int: int = 0
    c_str: str = ""
    c_float: float = 0.0
    c_bool: bool = False
    c_str_enum: TestStrEnum = TestStrEnum.DEFAULT


class TestConfigPythonAsyncExtension(AsyncExtension):
    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        config = await BasicTypesTestConfig.create_async(ten_env=ten_env)
        ten_env.log_debug(f"config: {config}")

        cmd = Cmd.create("test_cmd")
        cmd.set_property_from_json("", json.dumps(asdict(config)))
        await ten_env.send_cmd(cmd)
