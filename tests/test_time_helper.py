#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

import time
from ten_ai_base import TimeHelper
import math


def test_duration():
    start = time.time()
    time.sleep(0.05)  # Sleep for 50 milliseconds
    end = time.time()
    duration = TimeHelper.duration(start, end)
    assert math.isclose(duration, 0.05, rel_tol=0.1)


def test_duration_since():
    start = time.time()
    time.sleep(0.05)  # Sleep for 50 milliseconds
    duration = TimeHelper.duration_since(start)
    assert math.isclose(duration, 0.05, rel_tol=0.1)


def test_duration_ms():
    start = time.time()
    time.sleep(0.05)  # Sleep for 50 milliseconds
    end = time.time()
    duration_ms = TimeHelper.duration_ms(start, end)
    assert math.isclose(duration_ms, 50, rel_tol=1)


def test_duration_ms_since():
    start = time.time()
    time.sleep(0.05)  # Sleep for 50 milliseconds
    end = time.time()
    duration_ms = TimeHelper.duration_ms(start, end)
    assert math.isclose(duration_ms, 50, rel_tol=1)


def test_duration_ms_since():
    start = time.time()
    time.sleep(0.05)  # Sleep for 50 milliseconds
    duration_ms = TimeHelper.duration_ms_since(start)
    assert math.isclose(duration_ms, 50, rel_tol=1)
