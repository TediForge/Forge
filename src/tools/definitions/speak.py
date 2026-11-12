"""Batch text-to-speech tool backed by Forge's local Piper model."""

import base64
from typing import Any

from src.core.models.adapters.base import DispatcherError
from src.core.models.adapters.voice import VoiceDispatcher
from src.tools.actions import action_handler


MAX_INPUT_CHARS = 4096
FORMATS = {"wav": "audio/wav", "pcm": "audio/pcm"}
VOICES = {"default"}
MODELS = {"forge-tts"}


@action_handler("A8S4P2", "Generating speech")
async def handle_speak(
    operation: str,
    text: str,
    voice: str = "default",
    format: str = "wav",
    speed: float = 1.0,
    instructions: str | None = None,
    model: str = "forge-tts",
    *,
    dispatcher: VoiceDispatcher,
) -> dict[str, Any]:
    if operation != "text":
        return {
            "success": False,
            "operation": operation,
            "error": "Unsupported speech operation",
            "errorCode": "INVALID_OPERATION",
        }
    if not isinstance(text, str) or not text.strip():
        return {"success": False, "error": "Text must be non-empty", "errorCode": "INVALID_TEXT"}
    if len(text) > MAX_INPUT_CHARS:
        return {"success": False, "error": "Text exceeds the 4096-character limit", "errorCode": "TEXT_TOO_LONG"}
    if voice not in VOICES:
        return {"success": False, "error": "Unsupported configured voice", "errorCode": "INVALID_VOICE"}
    if format not in FORMATS:
        return {"success": False, "error": "Unsupported audio format", "errorCode": "INVALID_FORMAT"}
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not 0.25 <= speed <= 4.0:
        return {"success": False, "error": "Speed must be between 0.25 and 4.0", "errorCode": "INVALID_SPEED"}
    if model not in MODELS:
        return {"success": False, "error": "Unsupported speech model", "errorCode": "INVALID_MODEL"}
    if instructions:
        return {"success": False, "error": "Piper does not support speech instructions", "errorCode": "UNSUPPORTED_OPTION"}

    try:
        audioBytes = await dispatcher.synthesize(
            text=text,
            voice=voice,
            format=format,
            speed=float(speed),
            instructions=instructions,
        )
    except DispatcherError:
        return {"success": False, "error": "Forge speech model failed", "errorCode": "PROVIDER_ERROR"}
    if not audioBytes:
        return {"success": False, "error": "Forge speech model returned empty audio", "errorCode": "INVALID_PROVIDER_RESPONSE"}
    return {
        "success": True,
        "mediaData": base64.b64encode(audioBytes).decode("ascii"),
        "mimeType": FORMATS[format],
        "fileSizeBytes": len(audioBytes),
        "error": None,
        "errorCode": None,
    }


TOOLS = [{
    "type": "function",
    "function": {
        "name": "speak",
        "description": "Generate speech from text using Forge's configured local Piper model. Supports the configured voice and WAV or raw PCM output.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["text"]},
                "text": {"type": "string", "maxLength": MAX_INPUT_CHARS},
                "voice": {"type": "string", "enum": ["default"], "default": "default"},
                "format": {"type": "string", "enum": ["wav", "pcm"], "default": "wav"},
                "speed": {"type": "number", "minimum": 0.25, "maximum": 4.0, "default": 1.0},
                "instructions": {"type": "string"},
                "model": {"type": "string", "enum": ["forge-tts"], "default": "forge-tts"},
            },
            "required": ["operation", "text"],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"speak": handle_speak}
