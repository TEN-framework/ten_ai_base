"""A minimal HTTP adapter exercising the production TTS2 HTTP base."""

import httpx
from ten_ai_base.struct import TTS2HttpResponseEventType
from ten_ai_base.tts2_http import AsyncTTS2HttpClient, AsyncTTS2HttpConfig, AsyncTTS2HttpExtension


class Config(AsyncTTS2HttpConfig):
    url: str

    def update_params(self):
        pass

    def validate(self):
        pass

    def to_str(self, sensitive_handling=True):
        return "HTTP timing test configuration"


class Client(AsyncTTS2HttpClient):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.http = httpx.AsyncClient()
        self.observe_http_ttfb(self.http)

    async def get(self, text, request_id):
        if text:
            async with self.http.stream("POST", self.config.url, content=text) as response:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk, TTS2HttpResponseEventType.RESPONSE
        yield None, TTS2HttpResponseEventType.END

    async def clean(self):
        await self.http.aclose()

    async def cancel(self):
        pass

    def get_extra_metadata(self):
        return {}


class TimingExtension(AsyncTTS2HttpExtension):
    async def create_config(self, config_json_str):
        return Config.model_validate_json(config_json_str)

    async def create_client(self, config, ten_env):
        return Client(config)

    def vendor(self):
        return "http-timing-test"

    def synthesize_audio_sample_rate(self):
        return 16000
