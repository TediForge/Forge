"""Forge Text model dispatcher."""

import inspect
from typing import Any

from src.core.models.adapters.base import BaseDispatcher, DispatcherError


class TextDispatcher(BaseDispatcher):
    modality = "text"

    def __init__(self, provider: Any | None = None) -> None:
        self.provider = provider

    async def generate(self, prompt: str, **options: Any) -> str:
        if self.provider is None:
            raise DispatcherError("Forge Text provider is not configured")
        method = getattr(self.provider, "generate_text", None) or getattr(self.provider, "generate", None)
        if method is None and callable(self.provider):
            method = self.provider
        if method is None:
            raise DispatcherError("Text provider does not expose a supported generation method")

        try:
            result = method(prompt=prompt, **options)
        except TypeError:
            result = method(prompt, **options)
        if inspect.isawaitable(result):
            result = await result
        if hasattr(result, "text"):
            result = result.text
        if isinstance(result, dict):
            result = result.get("text") or result.get("content") or result.get("output")
        if not isinstance(result, str) or not result.strip():
            raise DispatcherError("Forge Text provider returned an empty response")
        return result.strip()

    async def generate_text(self, prompt: str, **options: Any) -> str:
        return await self.generate(prompt, **options)
