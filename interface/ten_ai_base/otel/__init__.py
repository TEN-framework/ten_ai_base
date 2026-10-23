# ABOUTME: Public OpenTelemetry context propagation for TEN Python extensions.
# ABOUTME: Exposes the instrumented extension base class and message helpers.

from .extension import InstrumentedExtension
from .propagation import (
    OTEL_CARRIER_PROPERTY,
    extract_otel_context,
    inject_otel_context,
)

__all__ = [
    "OTEL_CARRIER_PROPERTY",
    "InstrumentedExtension",
    "extract_otel_context",
    "inject_otel_context",
]
