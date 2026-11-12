"""Image generation facade."""

from typing import Any

from orchestrator.inference.gateway import InferenceGateway
from orchestrator.inference.protocols import InferenceRequest


class ImageGenFacade:
    def __init__(self, gateway: InferenceGateway, model_id: str = "image") -> None:
        self.gateway = gateway
        self.model_id = model_id

    async def generate(self, prompt: str, **parameters: Any) -> Any:
        return (await self.gateway.infer(
            InferenceRequest(self.model_id, "image_gen", prompt, parameters)
        )).output
