"""Observe HTTP request start and first audio response."""

from collections.abc import AsyncIterator, Callable

import httpx


class _AudioResponseStream(httpx.AsyncByteStream):
    def __init__(
        self,
        stream: httpx.AsyncByteStream,
        on_audio_received: Callable[[], None] | None,
        on_response_chunk: Callable[[], None],
    ) -> None:
        self.stream = stream
        self.on_audio_received = on_audio_received
        self.on_response_chunk = on_response_chunk

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.stream:
            if chunk:
                self.on_response_chunk()
                if self.on_audio_received is not None:
                    self.on_audio_received()
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


def observe_http_ttfb(
    client: httpx.AsyncClient,
    on_text_sent: Callable[[], None],
    on_audio_received: Callable[[], None],
    on_response_chunk: Callable[[], None],
) -> None:
    """Record request start before connection setup and observe audio responses."""

    async def request_hook(request: httpx.Request) -> None:
        on_text_sent()

    async def response_hook(response: httpx.Response) -> None:
        # Structured protocols identify valid audio in their adapters. Keep the
        # last chunk arrival as a candidate without treating envelopes as audio.
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "").lower()
            structured = any(
                kind in content_type for kind in ("text/event-stream", "json")
            )
            response.stream = _AudioResponseStream(
                response.stream,
                None if structured else on_audio_received,
                on_response_chunk,
            )

    client.event_hooks["request"].append(request_hook)
    client.event_hooks["response"].append(response_hook)
