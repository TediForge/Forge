"""Forge Speech-to-text adapter for the local faster-whisper runtime."""

from typing import Any

from src.core.models.adapters.base import BaseDispatcher, DispatcherError
from src.core.models.huggingface import HuggingFaceInference


class SttDispatcher(BaseDispatcher):
    modality = "audio"

    def __init__(self, provider: Any | None = None) -> None:
        self.provider = provider if provider is not None else HuggingFaceInference(model="transcription")

    async def transcribe(
        self,
        audioBytes: bytes,
        mimeType: str,
        language: str | None = None,
        timestamps: bool = False,
    ) -> dict[str, Any]:
        try:
            result = await self.provider.transcribe(
                audioBytes=audioBytes,
                mimeType=mimeType,
                language=language,
                timestamps=timestamps,
            )
        except Exception as exc:
            raise DispatcherError("Forge Speech local transcription failed") from exc
        if not isinstance(result, dict):
            raise DispatcherError("Forge Speech runtime returned an invalid transcription")
        return result

    async def generate(self, prompt: str, **options: Any) -> Any:
        raise DispatcherError("Speech-to-text dispatcher cannot generate audio")

    async def close(self) -> None:
        close = getattr(self.provider, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result
