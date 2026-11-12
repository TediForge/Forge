"""Speech synthesis modality dispatcher."""

import base64
from typing import Any

from orchestrator.inference.modalities.base import BaseDispatcher, DispatcherError


class VoiceDispatcher(BaseDispatcher):
    modality = "audio"

    def __init__(self, provider: Any | None = None) -> None:
        self.provider = provider

    async def synthesize(
        self,
        text: str,
        voice: str = "default",
        format: str = "wav",
        speed: float = 1.0,
        instructions: str | None = None,
    ) -> bytes:
        if self.provider is None:
            raise DispatcherError("Forge Voice synthesis provider is not configured")
        try:
            result = await self.provider.synthesize(
                text=text,
                voice=voice,
                format=format,
                speed=speed,
                instructions=instructions,
            )
        except Exception as exc:
            raise DispatcherError("Forge Voice local synthesis failed") from exc
        if not isinstance(result, bytes):
            raise DispatcherError("Forge Voice runtime returned an invalid audio result")
        return result

    async def generate(self, prompt: str, **options: Any) -> Any:
        audio = await self.synthesize(
            text=prompt,
            voice=options.get("voice", "default"),
            format=options.get("format", "wav"),
            speed=options.get("speed", 1.0),
            instructions=options.get("instructions"),
        )
        return {
            "mediaType": "audio",
            "mediaData": base64.b64encode(audio).decode("ascii"),
            "mimeType": "audio/wav",
            "fileName": "speech.wav",
        }

    async def close(self) -> None:
        close = getattr(self.provider, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result
