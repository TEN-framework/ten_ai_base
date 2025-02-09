#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten import (
    Extension,
    TenEnv,
    Cmd,
)
from ten_ai_base.config import BaseConfig
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


class TestConfigPythonExtension(Extension):
    def on_start(self, ten_env: TenEnv) -> None:
        config = BasicTypesTestConfig.create(ten_env=ten_env)
        ten_env.log_debug(f"config: {config}")

        cmd = Cmd.create("test_cmd")
        cmd.set_property_from_json("", json.dumps(asdict(config)))
        ten_env.send_cmd(cmd, None)

        ten_env.on_start_done()
