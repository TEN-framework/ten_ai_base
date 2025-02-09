#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

from ten_ai_base.chat_memory import ChatMemory, EVENT_MEMORY_APPENDED, EVENT_MEMORY_EXPIRED
import pytest
import asyncio


@pytest.fixture
def sample_data_2rounds():
    return [
        {"role": "user", "content": "123"},
        {"role": "assistant", "content": "abc"},
        {"role": "user", "content": "你好啊"},
        {"role": "assistant", "content": "再见了"},
    ]


def test_reach_max_len(sample_data_2rounds):
    for max_len in [2]:
        memory = ChatMemory(max_len)
        for d in sample_data_2rounds:
            memory.put(d)
        assert memory.count() == max_len
        assert memory.get() == sample_data_2rounds[max_len:]


def test_reach_max_len_and_first_not_assistant(sample_data_2rounds):
    memory = ChatMemory(3)
    for d in sample_data_2rounds:
        memory.put(d)
    assert memory.count() == 2  # first one can't be 'assistant'
    assert memory.get() == sample_data_2rounds[2:]


def test_not_reach_max_len(sample_data_2rounds):
    for max_len in [4, 100]:
        memory = ChatMemory(max_len)
        for d in sample_data_2rounds:
            memory.put(d)
        assert memory.count() == len(sample_data_2rounds)
        assert memory.get() == sample_data_2rounds


def test_empty_memory(sample_data_2rounds):
    for max_len in [0, -1]:
        memory = ChatMemory(max_len)
        for d in sample_data_2rounds:
            memory.put(d)
        assert memory.count() == 0


def test_clear():
    memory = ChatMemory(2)
    memory.put({"role": "user", "content": "123"})
    memory.put({"role": "assistant", "content": "abc"})
    assert memory.count() == 2
    memory.clear()
    assert memory.count() == 0
    assert not memory.get()


def test_on_emit(sample_data_2rounds):
    asyncio.run(async_test_on_emit(sample_data_2rounds))


async def async_test_on_emit(sample_data_2rounds):
    on_append_count = 0
    on_expired_count = 0

    async def on_appended(message):
        nonlocal on_append_count
        assert message == sample_data_2rounds[on_append_count]
        on_append_count += 1

    async def on_expired(message):
        nonlocal on_expired_count
        assert message == sample_data_2rounds[on_expired_count]
        on_append_count += 1

    memory = ChatMemory(2)
    memory.on(EVENT_MEMORY_APPENDED, on_appended)
    memory.on(EVENT_MEMORY_EXPIRED, on_expired)

    for d in sample_data_2rounds:
        memory.put(d)
