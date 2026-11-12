"""OpenAI-compatible Forge model catalog endpoints."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from orchestrator.inference.registry import MODELS, ModelDefinition, get_model


router = APIRouter()


class ModelResponse(BaseModel):
    id: str
    object: Literal["model"]
    created: int
    owned_by: str


class ModelListResponse(BaseModel):
    object: Literal["list"]
    data: list[ModelResponse]


def getModelProvider(request: Request, attribute: str, model: ModelDefinition) -> Any:
    injected = getattr(request.app.state, attribute, None)
    if injected is not None:
        return injected

    gateway = getattr(request.app.state, "modelGateway", None)
    if gateway is None:
        raise HTTPException(status_code=503, detail="Model gateway is unavailable.")
    return gateway.get(model)


def _modelObject(modelId: str) -> ModelResponse:
    return ModelResponse(
        id=modelId,
        object="model",
        created=0,
        owned_by="tediforge",
    )


@router.get("/v1/models", response_model=ModelListResponse)
async def listModels() -> ModelListResponse:
    return ModelListResponse(
        object="list",
        data=[_modelObject(modelId) for modelId in MODELS],
    )


@router.get("/v1/models/{modelId}", response_model=ModelResponse)
async def retrieveModel(modelId: str) -> ModelResponse:
    try:
        definition = get_model(modelId)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    registryId = next(
        key for key, registeredModel in MODELS.items()
        if registeredModel is definition
    )
    return _modelObject(registryId)
