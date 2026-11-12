"""Text generation facade."""

from collections.abc import AsyncIterator
from typing import Any

from orchestrator.inference.gateway import InferenceGateway
from orchestrator.inference.protocols import InferenceRequest


class TextFacade:
    def __init__(self, gateway: InferenceGateway, model_id: str = "text") -> None:
        self.gateway = gateway
        self.model_id = model_id

    async def generate(self, prompt: str, **parameters: Any) -> str:
        result = await self.gateway.infer(InferenceRequest(self.model_id, "text", prompt, parameters))
        return str(result.output)

    async def stream(self, prompt: str, **parameters: Any) -> AsyncIterator[str]:
        async for part in self.gateway.stream(InferenceRequest(self.model_id, "text", prompt, parameters)):
            yield part
