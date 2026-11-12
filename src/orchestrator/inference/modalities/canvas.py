"""Image generation modality dispatcher."""

import inspect
from typing import Any

from orchestrator.inference.modalities.base import BaseDispatcher, DispatcherError


class CanvasDispatcher(BaseDispatcher):
    modality = "image"

    def __init__(self, provider: Any | None = None) -> None:
        self.provider = provider

    async def generate(self, prompt: str, **options: Any) -> Any:
        if self.provider is None:
            raise DispatcherError("Forge Canvas provider is not configured")
        method = (
            getattr(self.provider, "generate_image", None)
            or getattr(self.provider, "generateImage", None)
            or getattr(self.provider, "generate", None)
        )
        if method is None and callable(self.provider):
            method = self.provider
        if method is None:
            raise DispatcherError("Canvas provider does not expose image generation")
        try:
            result = method(prompt=prompt, **options)
        except TypeError:
            result = method(prompt, **options)
        if inspect.isawaitable(result):
            result = await result
        if result is None:
            raise DispatcherError("Forge Canvas provider returned no asset")
        return result

    async def close(self) -> None:
        close = getattr(self.provider, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result
