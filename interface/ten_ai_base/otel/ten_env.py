# ABOUTME: Delegates AsyncTenEnv calls while injecting active OTel context.
# ABOUTME: Keeps existing extension callback and environment call shapes unchanged.

from typing import Any

from ten_runtime import AudioFrame, Cmd, CmdResult, Data, SendOptions, VideoFrame

from .propagation import inject_otel_context


class InstrumentedTenEnv:
    def __init__(self, ten_env: Any) -> None:
        self.raw = ten_env

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)

    async def send_cmd(self, cmd: Cmd):
        inject_otel_context(cmd)
        return await self.raw.send_cmd(cmd)

    async def send_data(
        self,
        data: Data,
        options: SendOptions | None = None,
    ):
        inject_otel_context(data)
        return await self.raw.send_data(data, options)

    async def send_audio_frame(
        self,
        audio_frame: AudioFrame,
        options: SendOptions | None = None,
    ):
        inject_otel_context(audio_frame)
        return await self.raw.send_audio_frame(audio_frame, options)

    async def send_video_frame(
        self,
        video_frame: VideoFrame,
        options: SendOptions | None = None,
    ):
        inject_otel_context(video_frame)
        return await self.raw.send_video_frame(video_frame, options)

    async def return_result(
        self,
        result: CmdResult,
        options: SendOptions | None = None,
    ):
        inject_otel_context(result)
        return await self.raw.return_result(result, options)
