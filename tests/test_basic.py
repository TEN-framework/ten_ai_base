#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

import ten_ai_base


def test_basic():
    _chat_memory = ten_ai_base.ChatMemory(10)


if __name__ == "__main__":
    test_basic()
