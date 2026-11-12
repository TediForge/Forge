"""Base dispatcher contract for Forge model adapters."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Mapping


class DispatcherError(RuntimeError):
    pass


class BaseDispatcher(ABC):
    modality: str

    @abstractmethod
    async def generate(self, prompt: str, **options: Any) -> Any:
        raise NotImplementedError

    async def stream(self, prompt: str, **options: Any) -> AsyncIterator[Any]:
        result = await self.generate(prompt, **options)
        yield result

    async def health(self) -> Mapping[str, Any]:
        return {"modality": self.modality, "status": "ready"}
