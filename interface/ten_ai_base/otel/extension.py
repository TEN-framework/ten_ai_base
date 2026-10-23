# ABOUTME: Adds OTel setup and context propagation to AsyncExtension callbacks.
# ABOUTME: Leaves business callback names and TEN environment usage unchanged.

from typing import Any, cast

from opentelemetry import trace
from opentelemetry.context import Context, attach, detach
from ten_runtime import (
    AsyncExtension,
    AsyncTenEnv,
    AudioFrame,
    Cmd,
    Data,
    VideoFrame,
)

from .propagation import extract_otel_context
from .ten_env import InstrumentedTenEnv


class InstrumentedExtension(AsyncExtension):
    otel_instrumentation_name = ""

    def __init__(self, name: str):
        super().__init__(name)
        self._otel_root_span: trace.Span | None = None
        self._otel_root_context: Context | None = None

    def _instrument(self, ten_env: AsyncTenEnv) -> AsyncTenEnv:
        return cast("AsyncTenEnv", InstrumentedTenEnv(ten_env))

    async def _wrapper_on_init(self, async_ten_env: AsyncTenEnv) -> None:
        await super()._wrapper_on_init(self._instrument(async_ten_env))

    async def _wrapper_on_start(self, async_ten_env: AsyncTenEnv) -> None:
        await super()._wrapper_on_start(self._instrument(async_ten_env))

    async def _wrapper_on_stop(self, async_ten_env: AsyncTenEnv) -> None:
        await super()._wrapper_on_stop(self._instrument(async_ten_env))

    async def _wrapper_on_deinit(self, async_ten_env: AsyncTenEnv) -> None:
        await super()._wrapper_on_deinit(self._instrument(async_ten_env))
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
        if not trace.get_current_span(context).get_span_context().is_valid:
            context = self._otel_root_context or context
        token = attach(context)
        try:
            await callback(self._instrument(ten_env), message)
        finally:
            detach(token)

    def start_root_span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> trace.Span:
        """Start the extension lifecycle span used as a fallback parent."""
        if self._otel_root_span is not None:
            return self._otel_root_span
        span = trace.get_tracer(self.otel_instrumentation_name).start_span(
            name,
            context=Context(),
            record_exception=False,
            set_status_on_exception=False,
        )
        if attributes:
            span.set_attributes(attributes)
        self._otel_root_span = span
        self._otel_root_context = trace.set_span_in_context(span)
        return span

    def end_root_span(self, *, attributes: dict[str, Any] | None = None) -> None:
        """End the extension lifecycle span, if one was started."""
        span = self._otel_root_span
        if span is None:
            return
        if attributes:
            span.set_attributes(attributes)
        span.end()
        self._otel_root_span = None
        self._otel_root_context = None
