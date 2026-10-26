# ABOUTME: Carries OpenTelemetry context in the TEN `_otel` JSON property.
# ABOUTME: Keeps business payload metadata separate from trace propagation.

import json
from contextlib import contextmanager
from typing import Any

from opentelemetry.context import Context, attach, detach
from opentelemetry.propagate import get_global_textmap, inject

OTEL_CARRIER_PROPERTY = "_otel"


def inject_otel_context(message: Any) -> None:
    """Replace the TEN `_otel` JSON carrier with the active OTel context."""
    try:
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

    except Exception:  # noqa: BLE001 - tracing must not block message delivery.
        # Telemetry must not prevent delivery of the business message.
        return


def extract_otel_context(message: Any) -> Context:
    """Extract OTel context only from the TEN `_otel` JSON carrier."""
    try:
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
    except Exception:  # noqa: BLE001 - tracing must not block message delivery.
        return Context()


@contextmanager
def use_otel_context(context: Context):
    """Attach context without allowing instrumentation failures to escape."""
    token = None
    try:
        token = attach(context)
    except Exception:  # noqa: BLE001, S110 - tracing must not block callbacks.
        pass
    try:
        yield
    finally:
        if token is not None:
            try:
                detach(token)
            except Exception:  # noqa: BLE001, S110 - tracing must not block callbacks.
                pass
