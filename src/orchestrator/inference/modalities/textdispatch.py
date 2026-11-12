"""Text generation dispatcher for injected inference providers."""

import inspect
from collections.abc import AsyncIterator
from typing import Any

from opentelemetry import trace

from orchestrator.inference.modalities.base import BaseDispatcher, DispatcherError


tracer = trace.get_tracer("orchestrator.inference.text")


class TextDispatcher(BaseDispatcher):
    modality = "text"

    def __init__(self, provider: Any | None = None) -> None:
        self.provider = provider

    async def generate(self, prompt: str, **options: Any) -> str:
        if self.provider is None:
            raise DispatcherError("Forge Text provider is not configured")
        method = (
            getattr(self.provider, "generate_text", None)
            or getattr(self.provider, "generateText", None)
            or getattr(self.provider, "generate", None)
        )
        if method is None and callable(self.provider):
            method = self.provider
        if method is None:
            raise DispatcherError("Text provider does not expose a supported generation method")
        with tracer.start_as_current_span("orchestrator.inference.generate"):
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

    async def stream(self, prompt: str, **options: Any) -> AsyncIterator[str]:
        if self.provider is None:
            raise DispatcherError("Forge Text provider is not configured")
        method = (
            getattr(self.provider, "stream_text", None)
            or getattr(self.provider, "streamText", None)
            or getattr(self.provider, "stream", None)
        )
        if not callable(method):
            raise DispatcherError("Forge Text provider does not support token streaming")
        with tracer.start_as_current_span("orchestrator.inference.stream"):
            try:
                chunks = method(prompt=prompt, **options)
            except TypeError:
                chunks = method(prompt, **options)
            if inspect.isawaitable(chunks):
                chunks = await chunks
            if not hasattr(chunks, "__aiter__"):
                raise DispatcherError("Forge Text provider returned an invalid stream")
            async for chunk in chunks:
                if hasattr(chunk, "text"):
                    chunk = chunk.text
                if isinstance(chunk, dict):
                    chunk = chunk.get("text") or chunk.get("content") or chunk.get("delta")
                if not isinstance(chunk, str):
                    raise DispatcherError("Forge Text provider returned a non-text stream chunk")
                if chunk:
                    yield chunk

    async def close(self) -> None:
        close = getattr(self.provider, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result
