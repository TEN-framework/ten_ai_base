#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import hashlib
import json
import re
from typing import Any, Collection, Mapping
from urllib.parse import unquote_plus

# Default HTTP header names treated as sensitive by `redact_headers`.
DEFAULT_HEADER_KEYS = frozenset({"authorization", "api-key", "x-api-key", "xi-api-key"})
# Default JSON field names treated as sensitive by `redact_json`.
DEFAULT_JSON_KEYS = frozenset(
    {
        "accesskey",
        "apikey",
        "api_key",
        "appkey",
        "authorization",
        "key",
        "password",
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
DEFAULT_URL_KEYS = frozenset({"sign", "signature"} | DEFAULT_JSON_KEYS)

# Keep these constants shared by the formatter and recognizer so the canonical
# masked format cannot drift between them. The pattern is precompiled because
# masking is used on reporting hot paths. A plaintext value that exactly matches
# this canonical format is intentionally treated as already masked.
_MAX_MASK_VISIBLE_CHARS = 5
_MASK_FINGERPRINT_HEX_CHARS = 8
_MIN_MASKED_SECRET_CHARS = 1 + 3 + 1 + 1 + _MASK_FINGERPRINT_HEX_CHARS
_MAX_MASKED_SECRET_CHARS = (
    _MAX_MASK_VISIBLE_CHARS * 2 + 3 + 1 + _MASK_FINGERPRINT_HEX_CHARS
)
_MASKED_SECRET_PATTERN = re.compile(
    rf"^.{{1,{_MAX_MASK_VISIBLE_CHARS}}}\.\.\."
    rf".{{1,{_MAX_MASK_VISIBLE_CHARS}}}#[0-9a-f]"
    rf"{{{_MASK_FINGERPRINT_HEX_CHARS}}}$",
    re.DOTALL,
)


def _mask_default(value: str) -> str:
    if not value:
        return value
    # Avoid regex work for ordinary secrets whose length cannot match the
    # canonical masked representation.
    could_be_masked = _MIN_MASKED_SECRET_CHARS <= len(value) <= _MAX_MASKED_SECRET_CHARS
    if could_be_masked and _MASKED_SECRET_PATTERN.fullmatch(value):
        return value
    step = int(len(value) / 5)
    if step <= 0:
        return value
    if step > _MAX_MASK_VISIBLE_CHARS:
        step = _MAX_MASK_VISIBLE_CHARS
    fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()[
        :_MASK_FINGERPRINT_HEX_CHARS
    ]
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


def redact_url(
    url: str,
    *,
    url_keys: Collection[str] | None = None,
) -> str:
    """Return a copy of a URL with sensitive query parameter values masked."""
    if not url:
        return url

    query_start = url.find("?")
    if query_start < 0:
        return url

    effective_url_keys = DEFAULT_URL_KEYS if url_keys is None else url_keys
    normalized_url_keys = _normalized_json_keys(effective_url_keys)
    prefix = url[: query_start + 1]
    query_and_fragment = url[query_start + 1 :]
    fragment = ""
    fragment_start = query_and_fragment.find("#")
    if fragment_start >= 0:
        fragment = query_and_fragment[fragment_start:]
        query_and_fragment = query_and_fragment[:fragment_start]

    if not query_and_fragment:
        return url

    pairs = query_and_fragment.split("&")
    for index, pair in enumerate(pairs):
        if not pair:
            continue

        key, has_value, value = pair.partition("=")
        try:
            decoded_key = unquote_plus(key)
        except Exception:
            decoded_key = key

        if not _is_sensitive_key(decoded_key, normalized_url_keys):
            continue

        if has_value:
            pairs[index] = f"{key}={mask_secret(value)}"

    return f"{prefix}{'&'.join(pairs)}{fragment}"


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
