"""Vision understanding facade."""

from typing import Any

from orchestrator.inference.gateway import InferenceGateway
from orchestrator.inference.protocols import InferenceRequest


class VisionFacade:
    def __init__(self, gateway: InferenceGateway, model_id: str = "vision") -> None:
        self.gateway = gateway
        self.model_id = model_id

    async def analyze(self, image: Any, prompt: str, **parameters: Any) -> Any:
        return (await self.gateway.infer(
            InferenceRequest(self.model_id, "vision", {"image": image, "prompt": prompt}, parameters)
        )).output
