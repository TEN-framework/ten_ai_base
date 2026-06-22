#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

import json

import pytest

from ten_ai_base import (
    DEFAULT_HEADER_KEYS,
    DEFAULT_JSON_KEYS,
    encrypt,
    mask_secret,
    redact_headers,
    redact_json,
)


def test_mask_secret_masks_long_values():
    assert mask_secret("1234567890") == "12...90#c775e7b7"
    assert mask_secret("abcdefghijklmnopqrstuvwxyz") == "abcde...vwxyz#71c480df"


def test_mask_secret_keeps_short_values():
    assert mask_secret("") == ""
    assert mask_secret("a") == "a"
    assert mask_secret("ab") == "ab"
    assert mask_secret("张") == "张"
    assert mask_secret("abcd") == "abcd"


def test_encrypt_calls_mask_secret():
    assert encrypt("abcdef123456") == mask_secret("abcdef123456")


def test_mask_secret_supports_modes():
    assert mask_secret("13800138000") == "13...00#a6942f97"
    assert mask_secret("+8613800138000") == "+8...00#ec61f3c6"
    assert mask_secret("alice@example.com") == "ali...com#ff8d9819"
    assert mask_secret("a@example.com") == "a@...om#08168cd8"
    assert mask_secret("110101199001011234") == "110...234#04e7358a"
    assert mask_secret("192.168.10.23") == "19...23#85512b03"


def test_default_key_sets_include_expected_items():
    assert "authorization" in DEFAULT_HEADER_KEYS
    assert "x-api-key" in DEFAULT_HEADER_KEYS
    assert "secretkey" in DEFAULT_JSON_KEYS


@pytest.mark.parametrize("json_key", sorted(DEFAULT_JSON_KEYS))
def test_redact_json_covers_all_default_json_keys(json_key):
    payload = {json_key: "abcdef123456", "normal": "visible"}

    data = redact_json(payload)

    assert data[json_key] == mask_secret("abcdef123456")
    assert data["normal"] == "visible"


def test_redact_json_redacts_sensitive_fields_recursively():
    payload = {
        "api_key": "abcdef123456",
        "nested": {
            "Authorization": "Bearer super-secret-token",
            "normal": "visible",
            "list": [
                {"secret_key": "nested-secret"},
                {"name": "kept"},
            ],
        },
        "count": 3,
        "empty_token": "",
        "none_token": None,
    }

    data = redact_json(payload)

    assert data["api_key"] == mask_secret("abcdef123456")
    assert data["nested"]["Authorization"] == mask_secret("Bearer super-secret-token")
    assert data["nested"]["normal"] == "visible"
    assert data["nested"]["list"][0]["secret_key"] == mask_secret("nested-secret")
    assert data["nested"]["list"][1]["name"] == "kept"
    assert data["count"] == 3
    assert data["empty_token"] == ""
    assert data["none_token"] is None


def test_redact_json_supports_custom_keys():
    payload = {"custom_secret": "abcdef123456", "normal": "visible"}
    data = redact_json(payload, json_keys={"custom_secret"})
    assert data["custom_secret"] == mask_secret("abcdef123456")
    assert data["normal"] == "visible"


def test_redact_headers_masks_known_sensitive_headers():
    headers = {
        "Authorization": "Bearer abcdef123456",
        "api-key": "key-123456",
        "xi-api-key": "xi-key-abcdef",
        "x-api-key": "xkey-abcdef",
        "Content-Type": "application/json",
    }

    sanitized = redact_headers(headers)

    assert sanitized["Authorization"] == mask_secret("Bearer abcdef123456")
    assert sanitized["api-key"] == mask_secret("key-123456")
    assert sanitized["xi-api-key"] == mask_secret("xi-key-abcdef")
    assert sanitized["x-api-key"] == mask_secret("xkey-abcdef")
    assert sanitized["Content-Type"] == "application/json"


@pytest.mark.parametrize("header_key", sorted(DEFAULT_HEADER_KEYS))
def test_redact_headers_covers_all_default_header_keys(header_key):
    headers = {header_key: "abcdef123456", "Content-Type": "application/json"}

    sanitized = redact_headers(headers)

    assert sanitized[header_key] == mask_secret("abcdef123456")
    assert sanitized["Content-Type"] == "application/json"


def test_mask_secret_default_mode_has_fingerprint():
    result = mask_secret("Bearer abcdef123456")
    assert result.startswith("Bea...456#")
    assert len(result.split("#", 1)[1]) == 8


def test_redact_headers_keeps_empty_input_shape():
    assert redact_headers({}) == {}
    assert redact_headers(None) is None


def test_redact_headers_supports_custom_keys():
    headers = {"x-custom-secret": "abcdef123456", "normal": "visible"}
    sanitized = redact_headers(headers, header_keys={"x-custom-secret"})
    assert sanitized["x-custom-secret"] == mask_secret("abcdef123456")
    assert sanitized["normal"] == "visible"
