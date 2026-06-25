#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import hashlib
import json
import re
from typing import Any, Collection, Mapping

# Default HTTP header names treated as sensitive by `redact_headers`.
DEFAULT_HEADER_KEYS = frozenset({"authorization", "api-key", "x-api-key", "xi-api-key"})
# Default JSON field names treated as sensitive by `redact_json`.
DEFAULT_JSON_KEYS = frozenset(
    {
        "accesskey",
        "apikey",
        "appkey",
        "authorization",
        "key",
        "secret",
        "secretid",
        "secretkey",
        "ststoken",
        "token",
        "vendorkey",
        "vendorsecret",
    }
    | DEFAULT_HEADER_KEYS
)


def _mask_default(value: str) -> str:
    if not value:
        return value
    step = int(len(value) / 5)
    if step <= 0:
        return value
    if step > 5:
        step = 5
    fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{value[:step]}...{value[-step:]}#{fingerprint}"


def mask_secret(value: str) -> str:
    """Mask a secret value while keeping a short prefix, suffix, and fingerprint."""
    return _mask_default(value)


def encrypt(value: str) -> str:
    """Backward-compatible alias for `mask_secret`."""
    return mask_secret(value)


def redact_headers(
    headers: Mapping[str, str] | None,
    *,
    header_keys: Collection[str] | None = None,
) -> dict[str, str] | None:
    """Return a copy of headers with sensitive header values masked."""
    if headers is None:
        return None
    if not headers:
        return {}

    effective_header_keys = {
        item.lower()
        for item in (DEFAULT_HEADER_KEYS if header_keys is None else header_keys)
    }
    return {
        key: mask_secret(value) if key.lower() in effective_header_keys else value
        for key, value in headers.items()
    }


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _normalized_json_keys(json_keys: Collection[str]) -> set[str]:
    return {_normalize_key(item) for item in json_keys}


def _is_sensitive_key(key: str, normalized_json_keys: set[str]) -> bool:
    normalized = _normalize_key(key)
    return normalized in normalized_json_keys


def _redact_value(value: Any, normalized_json_keys: set[str]) -> Any:
    if value in (None, ""):
        return value
    if isinstance(value, str):
        return mask_secret(value)
    if isinstance(value, list):
        return mask_secret(json.dumps(value, separators=(",", ":"), sort_keys=True))
    if isinstance(value, dict):
        return mask_secret(json.dumps(value, separators=(",", ":"), sort_keys=True))
    return mask_secret(str(value))


def _redact_json(value: Any, normalized_json_keys: set[str]) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key), normalized_json_keys):
                redacted[key] = _redact_value(item, normalized_json_keys)
            else:
                redacted[key] = _redact_json(item, normalized_json_keys)
        return redacted
    if isinstance(value, list):
        return [_redact_json(item, normalized_json_keys) for item in value]
    return value


def redact_json(
    value: Any,
    *,
    json_keys: Collection[str] | None = None,
) -> Any:
    """Recursively mask values whose keys match known sensitive JSON field names."""
    effective_json_keys = DEFAULT_JSON_KEYS if json_keys is None else json_keys
    return _redact_json(value, _normalized_json_keys(effective_json_keys))
