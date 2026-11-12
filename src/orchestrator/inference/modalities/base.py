"""Base dispatcher contract and modality capability errors."""

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
        raise DispatcherError(f"{self.modality} dispatcher does not support streaming")

    async def health(self) -> Mapping[str, Any]:
        return {"modality": self.modality, "status": "ready"}
