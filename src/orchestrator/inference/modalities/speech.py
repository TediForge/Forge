"""Speech synthesis facade."""

from typing import Any

from orchestrator.inference.gateway import InferenceGateway
from orchestrator.inference.protocols import InferenceRequest


class SpeechFacade:
    def __init__(self, gateway: InferenceGateway, model_id: str = "audio") -> None:
        self.gateway = gateway
        self.model_id = model_id

    async def synthesize(self, text: str, **parameters: Any) -> Any:
        return (await self.gateway.infer(
            InferenceRequest(self.model_id, "speech", text, parameters)
        )).output
