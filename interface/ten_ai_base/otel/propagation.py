# ABOUTME: Carries OpenTelemetry context in the TEN `_otel` JSON property.
# ABOUTME: Keeps business payload metadata separate from trace propagation.

import json
from typing import Any

from opentelemetry.context import Context
from opentelemetry.propagate import get_global_textmap, inject

OTEL_CARRIER_PROPERTY = "_otel"


def inject_otel_context(message: Any) -> None:
    """Replace the TEN `_otel` JSON carrier with the active OTel context."""
    carrier: dict[str, str] = {}
    inject(carrier)
    if not carrier:
        _, error = message.get_property_to_json(OTEL_CARRIER_PROPERTY)
        if error is not None:
            return
    message.set_property_from_json(
        OTEL_CARRIER_PROPERTY,
        json.dumps(carrier, separators=(",", ":")),
    )


def extract_otel_context(message: Any) -> Context:
    """Extract OTel context only from the TEN `_otel` JSON carrier."""
    propagator = get_global_textmap()
    carrier_json, error = message.get_property_to_json(OTEL_CARRIER_PROPERTY)
    if error is not None or not carrier_json:
        return propagator.extract({}, context=Context())
    try:
        carrier = json.loads(carrier_json)
    except json.JSONDecodeError:
        carrier = {}
    if not isinstance(carrier, dict):
        carrier = {}
    carrier = {
        key: value
        for key, value in carrier.items()
        if key in propagator.fields and isinstance(value, str)
    }
    return propagator.extract(carrier, context=Context())
