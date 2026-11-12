"""OpenAI-compatible Forge model catalog endpoints."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.core.models.huggingface import HuggingFaceInference
from src.core.models.registry import MODELS, ModelDefinition, get_model


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

    providers = getattr(request.app.state, "localModelProviders", None)
    if providers is None:
        providers = {}
        request.app.state.localModelProviders = providers
    provider = providers.get(model.model_id)
    if provider is None:
        provider = HuggingFaceInference(model=model)
        providers[model.model_id] = provider
    return provider


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
