"""Text embedding facade."""

from typing import Any

from orchestrator.inference.gateway import InferenceGateway
from orchestrator.inference.protocols import InferenceRequest


class EmbeddingFacade:
    def __init__(self, gateway: InferenceGateway, model_id: str = "embedding") -> None:
        self.gateway = gateway
        self.model_id = model_id

    async def embed(self, inputs: str | list[str]) -> Any:
        return (await self.gateway.infer(
            InferenceRequest(self.model_id, "embedding", inputs)
        )).output
