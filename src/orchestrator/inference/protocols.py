"""Stable inference contracts shared by serving components."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class InferenceRequest:
    model_id: str
    modality: str
    input: Any
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceResponse:
    model_id: str
    modality: str
    backend_id: str
    output: Any
    load_ms: float
    latency_ms: float


class BackendProtocol(Protocol):
    backend_id: str

    async def generate(self, request: InferenceRequest) -> Any: ...

    async def embed(self, request: InferenceRequest) -> Any: ...

    async def transcribe(self, request: InferenceRequest) -> Any: ...

    async def synthesize(self, request: InferenceRequest) -> Any: ...

    def stream(self, request: InferenceRequest) -> AsyncIterator[str]: ...

    async def health(self) -> bool: ...

    async def close(self) -> None: ...
