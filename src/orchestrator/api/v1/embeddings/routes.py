"""Forge embeddings endpoint."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel

from orchestrator.inference.registry import get_model
from orchestrator.schemas.common import CamelBaseModel
from orchestrator.security.identity import Principal
from orchestrator.security.rbac import AuthorizationError, Permission, require_authorization
from orchestrator.api.v1.models.routes import getModelProvider


router = APIRouter()


class EmbeddingsRequest(CamelBaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    model: str = "embedding"
    input: str | list[str] = Field(..., min_length=1)


def _principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(status_code=401, detail="Authenticated principal is required.")
    try:
        require_authorization(principal, Permission.RUN)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return principal


def _vectors(result: Any, inputCount: int) -> list[list[float]]:
    if not isinstance(result, list):
        raise HTTPException(status_code=502, detail="Embedding model returned an invalid response.")
    if result and all(isinstance(value, (int, float)) for value in result):
        result = [result]
    if (
        len(result) != inputCount
        or any(not isinstance(vector, list) for vector in result)
        or any(not vector or any(not isinstance(value, (int, float)) for value in vector) for vector in result)
    ):
        raise HTTPException(status_code=502, detail="Embedding model returned an invalid response.")
    return [[float(value) for value in vector] for vector in result]


@router.post("/v1/embeddings")
async def createEmbeddings(payload: EmbeddingsRequest, request: Request) -> dict[str, object]:
    _principal(request)
    try:
        definition = get_model(payload.model)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "textEmbedding" not in definition.capabilities:
        raise HTTPException(status_code=400, detail=f"Model '{payload.model}' does not support embeddings.")

    provider = getModelProvider(request, "embeddingProvider", definition)

    inputs = payload.input if isinstance(payload.input, list) else [payload.input]
    try:
        result = await provider.embed(payload.input)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Forge embedding model is unavailable.") from exc

    vectors = _vectors(result, len(inputs))
    return {
        "object": "list",
        "model": payload.model,
        "data": [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ],
    }