"""Forge Text Chat Completions endpoint."""

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, ConfigDict, Field
from pydantic.alias_generators import to_camel

from orchestrator.inference.registry import MODELS, ModelDefinition, get_model
from orchestrator.schemas.common import CamelBaseModel
from orchestrator.security.identity import Principal
from orchestrator.security.rbac import AuthorizationError, Permission, require_authorization
from orchestrator.api.v1.models.routes import getModelProvider


router = APIRouter()


class ChatMessage(CamelBaseModel):
    role: Literal["system", "developer", "user", "assistant"]
    content: str | list[dict[str, Any]]
    name: str | None = None


def _messageContent(message: ChatMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    textParts = [
        part.get("text")
        for part in message.content
        if part.get("type") == "text" and isinstance(part.get("text"), str)
    ]
    if len(textParts) != len(message.content):
        raise HTTPException(status_code=400, detail="Forge Text chat supports text content parts only.")
    return "\n".join(textParts)


class ChatCompletionRequest(CamelBaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    model: str = "text"
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=100)
    stream: bool = False
    maxTokens: int | None = Field(
        default=None,
        ge=1,
        validation_alias=AliasChoices("max_tokens", "max_completion_tokens", "maxTokens"),
    )
    temperature: float | None = Field(default=None, ge=0, le=2)
    topP: float | None = Field(
        default=None,
        ge=0,
        le=1,
        validation_alias=AliasChoices("top_p", "topP"),
    )
    stop: str | list[str] | None = None
    n: int = Field(default=1, ge=1, le=1)


def _principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(status_code=401, detail="Authenticated principal is required.")
    try:
        require_authorization(principal, Permission.RUN)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return principal


def _requestContext(payload: ChatCompletionRequest) -> tuple[ModelDefinition, str, str]:
    try:
        definition = get_model(payload.model)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "chat" not in definition.capabilities:
        raise HTTPException(status_code=400, detail=f"Model '{payload.model}' does not support chat.")

    lastMessage = payload.messages[-1]
    lastMessageContent = _messageContent(lastMessage)
    if lastMessage.role != "user" or not lastMessageContent.strip():
        raise HTTPException(status_code=400, detail="The last message must contain user text.")
    prompt = "\n".join(
        f"{message.role}: {_messageContent(message)}"
        for message in payload.messages
    )
    prompt = f"{prompt}\nassistant:"
    modelId = next(
        key for key, registeredModel in MODELS.items()
        if registeredModel is definition
    )
    return definition, prompt, modelId


def _generationOptions(
    definition: ModelDefinition,
    payload: ChatCompletionRequest,
) -> dict[str, object]:
    options: dict[str, object] = {}
    parameters = definition.parameters
    options["max_new_tokens"] = payload.maxTokens or parameters.get("maxTokens", 4096)
    options["temperature"] = (
        payload.temperature if payload.temperature is not None
        else parameters.get("temperature", 0.7)
    )
    options["top_p"] = payload.topP if payload.topP is not None else parameters.get("topP", 0.9)
    if payload.stop is not None:
        options["stop"] = payload.stop
    return options


def _completion(
    completionId: str,
    model: str,
    created: int,
    content: str,
) -> dict[str, Any]:
    return {
        "id": completionId,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
    }


async def _completionStream(completion: dict[str, Any]) -> AsyncIterator[str]:
    responseMetadata = {
        key: value for key, value in completion.items()
    }
    roleChunk = {
        **responseMetadata,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(roleChunk)}\n\n"

    contentChunk = {
        **responseMetadata,
        "object": "chat.completion.chunk",
        "choices": [{
            "index": 0,
            "delta": {"content": completion["choices"][0]["message"]["content"]},
            "finish_reason": None,
        }],
    }
    yield f"data: {json.dumps(contentChunk)}\n\n"

    finishChunk = {
        **responseMetadata,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(finishChunk)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/v1/chat/completions")
async def createChatCompletion(payload: ChatCompletionRequest, request: Request):
    _principal(request)
    definition, prompt, modelId = _requestContext(payload)
    provider = getModelProvider(request, "chatCompletionProvider", definition)

    options = _generationOptions(definition, payload)
    try:
        content = await provider.generateText(prompt, **options)
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=502, detail="Forge Text model returned an empty completion.")
        content = content.strip()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Forge Text model is unavailable.") from exc

    completion = _completion(
        f"chatcmpl_{uuid.uuid4().hex}",
        modelId,
        int(time.time()),
        content,
    )
    if payload.stream:
        return StreamingResponse(_completionStream(completion), media_type="text/event-stream")
    return completion
