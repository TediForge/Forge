"""Local Transformers and sentence-transformers backend."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from orchestrator.inference.backends.base import Backend, BackendCapabilityError
from orchestrator.inference.protocols import InferenceRequest
from orchestrator.inference.backends.local import HuggingFaceInference
from orchestrator.inference.registry import ModelDefinition


class TransformersBackend(Backend):
    backend_id = "transformers"
    modalities = frozenset({"text", "embedding", "vision"})

    def __init__(self, model: ModelDefinition, model_path: Path, device: str = "cpu") -> None:
        self._provider = HuggingFaceInference(model=model, model_path=model_path, device=device)
        self._closed = False

    async def generate(self, request: InferenceRequest) -> str:
        if request.modality == "text":
            return await self._provider.generateText(str(request.input), **dict(request.parameters))
        if request.modality == "vision":
            if not isinstance(request.input, dict):
                raise ValueError("Vision input must contain prompt, system_prompt, and images.")
            return await self._provider.analyzeImage(
                prompt=str(request.input.get("prompt", "")),
                system_prompt=str(request.input.get("system_prompt", "")),
                images=request.input.get("images", []),
            )
        raise BackendCapabilityError(f"TransformersBackend does not support modality='{request.modality}'")

    async def embed(self, request: InferenceRequest) -> list[list[float]]:
        return await self._provider.embed(request.input)

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        if request.modality != "text":
            raise BackendCapabilityError("TransformersBackend streaming requires modality='text'")
        async for part in self._provider.streamText(str(request.input), **dict(request.parameters)):
            yield part

    async def health(self) -> bool:
        return not self._closed

    async def close(self) -> None:
        self._closed = True
        await self._provider.close()

    async def generateText(self, prompt: str, **parameters: Any) -> str:
        return await self.generate(InferenceRequest("", "text", prompt, parameters))

    async def streamText(self, prompt: str, **parameters: Any) -> AsyncIterator[str]:
        async for part in self.stream(InferenceRequest("", "text", prompt, parameters)):
            yield part

    async def generateImage(self, prompt: str, **parameters: Any) -> Any:
        return await self._provider.generateImage(prompt, **parameters)

    async def generate_image(self, request: InferenceRequest) -> Any:
        return await self._provider.generateImage(str(request.input), **dict(request.parameters))

    async def transcribe(self, request: InferenceRequest) -> Any:
        parameters = dict(request.parameters)
        mime_type = parameters.pop("mimeType", None)
        if not isinstance(mime_type, str):
            raise ValueError("Transcription requires a mimeType parameter.")
        return await self._provider.transcribe(request.input, mime_type, **parameters)

    async def synthesize(self, request: InferenceRequest) -> Any:
        return await self._provider.synthesize(request.input, **dict(request.parameters))
