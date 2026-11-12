"""Authenticated batch audio transcription route."""

import base64
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from orchestrator.security.identity import Principal
from orchestrator.tools.definitions.transcribe import MAX_AUDIO_BYTES


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


def _raise_tool_error(result: object) -> None:
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Transcription model returned an invalid result.")
    if result.get("success"):
        return
    code = result.get("errorCode")
    status = 400 if code in {
        "INVALID_MEDIA",
        "EMPTY_AUDIO",
        "FILE_TOO_LARGE",
        "UNSUPPORTED_MEDIA",
        "INVALID_MODEL",
        "INVALID_FORMAT",
        "INVALID_LANGUAGE",
    } else 502
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": result.get("error", "Transcription failed.")},
    )


@router.post("/v1/audio/transcriptions")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    timestamps: bool = Form(default=False),
    model: str = Form(default="transcription"),
    response_format: Literal["json", "text", "verbose_json"] = Form(default="json"),
):
    _principal(request)
    audioBytes = await file.read(MAX_AUDIO_BYTES + 1)
    await file.close()
    if len(audioBytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio exceeds the 25 MB limit.")
    if not file.content_type:
        raise HTTPException(status_code=415, detail="Audio MIME type is required.")

    result = await _engine(request).toolExecutor.executeAsync({
        "name": "transcribe",
        "arguments": {
            "operation": "audio",
            "mediaData": base64.b64encode(audioBytes).decode("ascii"),
            "mimeType": file.content_type,
            "language": language,
            "timestamps": timestamps or response_format == "verbose_json",
            "model": model,
            "response_format": response_format,
        },
    })
    _raise_tool_error(result)
    if response_format == "text":
        return PlainTextResponse(result["text"])
    return JSONResponse({
        "text": result["text"],
        **({"language": result["language"]} if result.get("language") else {}),
        **({"segments": result.get("segments", [])} if timestamps or response_format == "verbose_json" else {}),
    })
