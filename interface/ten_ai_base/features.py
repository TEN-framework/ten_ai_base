#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from typing import Any, Mapping

from ten_runtime import AsyncTenEnv, Data

from .const import DATA_OUT_PROVIDE_FEATURES
from .message import ProvideFeaturesPayload


async def send_provide_features(
    ten_env: AsyncTenEnv, features: Mapping[str, Any]
) -> None:
    data = Data.create(DATA_OUT_PROVIDE_FEATURES)
    payload = ProvideFeaturesPayload(features=dict(features))
    data.set_property_from_json(None, payload.model_dump_json())
    await ten_env.send_data(data)
