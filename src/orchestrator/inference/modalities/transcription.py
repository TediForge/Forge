"""Speech transcription facade."""

from typing import Any

from orchestrator.inference.gateway import InferenceGateway
from orchestrator.inference.protocols import InferenceRequest


class TranscriptionFacade:
    def __init__(self, gateway: InferenceGateway, model_id: str = "transcription") -> None:
        self.gateway = gateway
        self.model_id = model_id

    async def transcribe(self, audio: Any, **parameters: Any) -> Any:
        return (await self.gateway.infer(
            InferenceRequest(self.model_id, "transcription", audio, parameters)
        )).output
