#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten_ai_base.struct import TTSTextInput


def test_tts_text_input_flush_defaults_to_false():
    tts_input = TTSTextInput(
        request_id="req-1",
        text="hello",
    )

    assert tts_input.flush is False


def test_tts_text_input_accepts_explicit_flush_true():
    tts_input = TTSTextInput(
        request_id="req-2",
        text="hello",
        flush=True,
    )

    assert tts_input.flush is True
