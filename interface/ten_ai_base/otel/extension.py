# ABOUTME: Propagates OTel context through AsyncExtension callbacks.
# ABOUTME: Leaves business callback names and TEN environment usage unchanged.

import json
from typing import Any, cast

from opentelemetry import trace
from opentelemetry.context import Context
from ten_runtime import (
    AsyncExtension,
    AsyncTenEnv,
    AudioFrame,
    Cmd,
    Data,
    VideoFrame,
)

from .propagation import extract_otel_context, use_otel_context
from .ten_env import InstrumentedTenEnv


class InstrumentedExtension(AsyncExtension):
    otel_instrumentation_name = ""

    def __init__(self, name: str):
        super().__init__(name)
        self._otel_root_span: trace.Span | None = None
        self._otel_root_context: Context | None = None
        self._otel_session_span: trace.Span | None = None
        self._otel_session_context: Context | None = None
        self._otel_connection_span: trace.Span | None = None
        self._otel_connection_context: Context | None = None

    def _instrument(self, ten_env: AsyncTenEnv) -> AsyncTenEnv:
        return cast("AsyncTenEnv", InstrumentedTenEnv(ten_env))

    async def _wrapper_on_init(self, async_ten_env: AsyncTenEnv) -> None:
        await super()._wrapper_on_init(self._instrument(async_ten_env))

    async def _wrapper_on_start(self, async_ten_env: AsyncTenEnv) -> None:
        await super()._wrapper_on_start(self._instrument(async_ten_env))

    async def _wrapper_on_stop(self, async_ten_env: AsyncTenEnv) -> None:
        await super()._wrapper_on_stop(self._instrument(async_ten_env))

    async def _wrapper_on_deinit(self, async_ten_env: AsyncTenEnv) -> None:
        try:
            await super()._wrapper_on_deinit(self._instrument(async_ten_env))
        finally:
            self.end_root_span()

    async def _wrapper_on_cmd(self, async_ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        await self._run_with_message_context(
            async_ten_env,
            cmd,
            super()._wrapper_on_cmd,
        )

    async def _wrapper_on_data(self, async_ten_env: AsyncTenEnv, data: Data) -> None:
        await self._run_with_message_context(
            async_ten_env,
            data,
            super()._wrapper_on_data,
        )

    async def _wrapper_on_audio_frame(
        self,
        async_ten_env: AsyncTenEnv,
        audio_frame: AudioFrame,
    ) -> None:
        await self._run_with_message_context(
            async_ten_env,
            audio_frame,
            super()._wrapper_on_audio_frame,
        )

    async def _wrapper_on_video_frame(
        self,
        async_ten_env: AsyncTenEnv,
        video_frame: VideoFrame,
    ) -> None:
        await self._run_with_message_context(
            async_ten_env,
            video_frame,
            super()._wrapper_on_video_frame,
        )

    async def _run_with_message_context(
        self,
        ten_env: AsyncTenEnv,
        message: Any,
        callback: Any,
    ) -> None:
        context = extract_otel_context(message)
        try:
            if not trace.get_current_span(context).get_span_context().is_valid:
                context = (
                    self._otel_root_context
                    or self._otel_session_context
                    or context
                )
        except Exception:  # noqa: BLE001, S110 - tracing must not stop application work.
            pass
        with use_otel_context(context):
            await callback(self._instrument(ten_env), message)

    def start_root_span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> trace.Span:
        """Start the extension lifecycle span used as a fallback parent."""
        if self._otel_root_span is not None:
            return self._otel_root_span
        span = trace.INVALID_SPAN
        try:
            span = trace.get_tracer(self.otel_instrumentation_name).start_span(
                name,
                context=Context(),
                record_exception=False,
                set_status_on_exception=False,
            )
            self._otel_root_span = span
            if span.get_span_context().is_valid:
                self._otel_root_context = trace.set_span_in_context(span, Context())
            if attributes:
                span.set_attributes(attributes)
        except Exception:  # noqa: BLE001, S110 - tracing must not stop application work.
            pass
        return span

    def end_root_span(self, *, attributes: dict[str, Any] | None = None) -> None:
        """End the extension lifecycle span, if one was started."""
        span = self._otel_root_span
        if span is None:
            return
        self._otel_root_span = None
        self._otel_root_context = None
        try:
            if attributes:
                span.set_attributes(attributes)
        except Exception:  # noqa: BLE001, S110 - tracing must not stop application work.
            pass
        finally:
            try:
                span.end()
            except Exception:  # noqa: BLE001, S110 - tracing must not stop application work.
                pass

    def _start_otel_span(
        self,
        name: str,
        *,
        parent_context: Context | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> tuple[trace.Span, Context]:
        """Start a lifecycle span and return it with its child context."""
        span: trace.Span = trace.INVALID_SPAN
        context = parent_context if parent_context is not None else Context()
        try:
            span = trace.get_tracer(self.otel_instrumentation_name).start_span(
                name,
                context=context,
                attributes=attributes,
                record_exception=False,
                set_status_on_exception=False,
            )
            if span.get_span_context().is_valid:
                context = trace.set_span_in_context(span, context)
        except Exception:  # noqa: BLE001, S110 - tracing must not block callbacks.
            pass
        return span, context

    def start_otel_session_span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> trace.Span:
        """Start the one span covering the extension session."""
        if self._otel_session_span is not None:
            return self._otel_session_span
        span, context = self._start_otel_span(
            name,
            attributes=attributes,
        )
        self._otel_session_span = span
        self._otel_session_context = context
        return span

    def end_otel_session_span(self) -> None:
        """End the extension session span, if present."""
        span = self._otel_session_span
        self._otel_session_span = None
        self._otel_session_context = None
        if span is None:
            return
        try:
            span.end()
        except Exception:  # noqa: BLE001, S110 - tracing must not block callbacks.
            pass

    def start_otel_connection_span(self, name: str) -> trace.Span:
        """Start a websocket connection segment under the session span."""
        if self._otel_connection_span is not None:
            return self._otel_connection_span
        span, context = self._start_otel_span(
            name,
            parent_context=self._otel_session_context,
        )
        self._otel_connection_span = span
        self._otel_connection_context = context
        return span

    def end_otel_connection_span(
        self,
        *,
        error: str | None = None,
    ) -> None:
        """End a websocket connection segment, optionally marking an error."""
        span = self._otel_connection_span
        self._otel_connection_span = None
        self._otel_connection_context = None
        if span is None:
            return
        try:
            if error:
                span.set_status(trace.StatusCode.ERROR, error)
        except Exception:  # noqa: BLE001, S110 - tracing must not block callbacks.
            pass
        finally:
            try:
                span.end()
            except Exception:  # noqa: BLE001, S110 - tracing must not block callbacks.
                pass

    def add_otel_span_event(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
        span: trace.Span | None = None,
    ) -> None:
        """Record a legacy TEN event on the active lifecycle span."""
        target = span or self._otel_connection_span or self._otel_session_span
        if target is None:
            return
        try:
            event_attributes = {
                key: self._otel_event_attribute(value)
                for key, value in (attributes or {}).items()
            }
            target.add_event(name, attributes=event_attributes)
        except Exception:  # noqa: BLE001, S110 - tracing must not block callbacks.
            pass

    @staticmethod
    def _otel_event_attribute(value: Any) -> str | bool | int | float:
        if isinstance(value, (str, bool, int, float)):
            return value
        try:
            return json.dumps(value, separators=(",", ":"), default=str)
        except Exception:  # noqa: BLE001 - tracing must not block callbacks.
            return str(value)
