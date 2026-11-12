"""Backend lifecycle and capability contract."""

from collections.abc import AsyncIterator
from typing import Any

from orchestrator.inference.protocols import InferenceRequest


class BackendCapabilityError(NotImplementedError):
    """Raised when a backend does not implement a requested modality."""


class BackendUnavailableError(RuntimeError):
    """Raised when a configured optional backend cannot be loaded."""


class Backend:
    backend_id: str
    modalities: frozenset[str] = frozenset()

    async def generate(self, request: InferenceRequest) -> Any:
        raise BackendCapabilityError(f"{self.backend_id} does not support text generation")

    async def embed(self, request: InferenceRequest) -> Any:
        raise BackendCapabilityError(f"{self.backend_id} does not support embeddings")

    async def transcribe(self, request: InferenceRequest) -> Any:
        raise BackendCapabilityError(f"{self.backend_id} does not support transcription")

    async def synthesize(self, request: InferenceRequest) -> Any:
        raise BackendCapabilityError(f"{self.backend_id} does not support speech synthesis")

    async def generate_image(self, request: InferenceRequest) -> Any:
        raise BackendCapabilityError(f"{self.backend_id} does not support image generation")

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        raise BackendCapabilityError(f"{self.backend_id} does not support token streaming")

    async def health(self) -> bool:
        return True

    async def close(self) -> None:
        return None
