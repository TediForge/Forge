"""Batch speech-to-text tool backed by Forge's local faster-whisper model."""

import base64
import binascii
from typing import Any

from orchestrator.inference.modalities import DispatcherError, SttDispatcher
from orchestrator.inference.registry import MODELS, get_model
from orchestrator.tools.actions import action_handler


MAX_AUDIO_BYTES = 25 * 1024 * 1024
SUPPORTED_MIME_TYPES = {
    "audio/flac", "audio/mpeg", "audio/mp4", "audio/mpga", "audio/m4a",
    "audio/ogg", "audio/wav", "audio/webm", "audio/x-wav",
}
@action_handler("A5T8R1", "Transcribing audio")
async def handle_transcribe(
    operation: str,
    mediaData: str,
    mimeType: str,
    language: str | None = None,
    timestamps: bool = False,
    model: str = "transcription",
    response_format: str = "json",
    *,
    dispatcher: SttDispatcher,
) -> dict[str, Any]:
    if operation != "audio":
        return {
            "success": False,
            "operation": operation,
            "text": "",
            "error": "Unsupported transcription operation",
            "errorCode": "INVALID_OPERATION",
        }
    try:
        audioBytes = base64.b64decode(mediaData, validate=True)
    except (binascii.Error, ValueError):
        return {"success": False, "text": "", "error": "mediaData must be valid base64", "errorCode": "INVALID_MEDIA"}
    if not audioBytes:
        return {"success": False, "text": "", "error": "Audio data is empty", "errorCode": "EMPTY_AUDIO"}
    if len(audioBytes) > MAX_AUDIO_BYTES:
        return {"success": False, "text": "", "error": "Audio exceeds the 25 MB limit", "errorCode": "FILE_TOO_LARGE"}
    normalizedMime = mimeType.split(";", 1)[0].strip().casefold()
    if normalizedMime not in SUPPORTED_MIME_TYPES:
        return {"success": False, "text": "", "error": "Unsupported audio MIME type", "errorCode": "UNSUPPORTED_MEDIA"}
    try:
        definition = get_model(model)
    except (AttributeError, KeyError):
        return {"success": False, "text": "", "error": "Unsupported transcription model", "errorCode": "INVALID_MODEL"}
    if "speechToText" not in definition.capabilities:
        return {"success": False, "text": "", "error": "Unsupported transcription model", "errorCode": "INVALID_MODEL"}
    if response_format not in {"json", "text", "verbose_json"}:
        return {"success": False, "text": "", "error": "Unsupported transcription response format", "errorCode": "INVALID_FORMAT"}
    if language is not None and (not isinstance(language, str) or not language.strip()):
        return {"success": False, "text": "", "error": "Language must be a non-empty language code", "errorCode": "INVALID_LANGUAGE"}

    try:
        result = await dispatcher.transcribe(
            audioBytes=audioBytes,
            mimeType=normalizedMime,
            language=language,
            timestamps=timestamps or response_format == "verbose_json",
        )
    except DispatcherError:
        return {"success": False, "text": "", "error": "Forge transcription model failed", "errorCode": "PROVIDER_ERROR"}
    if not isinstance(result, dict) or not isinstance(result.get("text"), str):
        return {
            "success": False,
            "text": "",
            "error": "Forge transcription model returned an invalid response",
            "errorCode": "INVALID_PROVIDER_RESPONSE",
        }
    response = {
        "success": True,
        "text": result["text"],
        "language": result.get("language"),
        "error": None,
        "errorCode": None,
    }
    if timestamps or response_format == "verbose_json":
        response["segments"] = result.get("segments", [])
    return response


TOOLS = [{
    "type": "function",
    "function": {
        "name": "transcribe",
        "description": "Transcribe supplied audio using Forge's configured local faster-whisper model. Do not use for text input or non-speech audio.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["audio"]},
                "mediaData": {"type": "string"},
                "mimeType": {"type": "string"},
                "language": {"type": "string", "description": "Optional ISO-639-1 language hint"},
                "timestamps": {"type": "boolean", "default": False},
                "model": {
                    "type": "string",
                    "enum": [
                        key for key, definition in MODELS.items()
                        if "speechToText" in definition.capabilities
                    ],
                    "default": "transcription",
                },
                "response_format": {"type": "string", "enum": ["json", "text", "verbose_json"], "default": "json"},
            },
            "required": ["operation", "mediaData", "mimeType"],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"transcribe": handle_transcribe}
