"""Authenticated batch text-to-speech route."""

import base64
import binascii
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from orchestrator.security.identity import Principal
from orchestrator.tools.definitions.speak import FORMATS, MAX_INPUT_CHARS


router = APIRouter()


def _principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(status_code=401, detail="Authenticated principal is required.")
    return principal


def _engine(request: Request):
    engine = getattr(request.app.state, "engine", None)
    if engine is None or not hasattr(engine, "toolExecutor"):
        raise HTTPException(status_code=503, detail="Audio tools are unavailable.")
    return engine


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str = Field(..., min_length=1, max_length=MAX_INPUT_CHARS)
    model: Literal["forge-tts"] = "forge-tts"
    voice: Literal["default"] = "default"
    response_format: Literal["wav", "pcm"] = "wav"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    instructions: str | None = None


@router.post("/v1/audio/speech")
async def speech(request: Request, payload: SpeechRequest):
    _principal(request)
    result = await _engine(request).toolExecutor.executeAsync({
        "name": "speak",
        "arguments": {
            "operation": "text",
            "text": payload.input,
            "model": payload.model,
            "voice": payload.voice,
            "format": payload.response_format,
            "speed": payload.speed,
            "instructions": payload.instructions,
        },
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Speech model returned an invalid result.")
    if not result.get("success"):
        code = result.get("errorCode")
        status = 400 if code in {
            "INVALID_TEXT",
            "TEXT_TOO_LONG",
            "INVALID_VOICE",
            "INVALID_FORMAT",
            "INVALID_SPEED",
            "INVALID_MODEL",
            "UNSUPPORTED_OPTION",
        } else 502
        raise HTTPException(
            status_code=status,
            detail={"code": code, "message": result.get("error", "Speech generation failed.")},
        )
    try:
        audioBytes = base64.b64decode(result["mediaData"], validate=True)
    except (KeyError, TypeError, binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Speech model returned invalid audio data.") from exc
    if not audioBytes or len(audioBytes) != result.get("fileSizeBytes"):
        raise HTTPException(status_code=502, detail="Speech model returned invalid audio data.")
    return Response(
        content=audioBytes,
        media_type=FORMATS[payload.response_format],
        headers={"Content-Length": str(len(audioBytes))},
    )
