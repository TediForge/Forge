"""Local Forge image and speech generation operations."""

from typing import Any

from src.core.models.adapters.base import DispatcherError
from src.tools.actions import action_handler
from src.tools.definitions.image import generate as generateImage


def _failure(operation: str, error: str, errorCode: str) -> dict[str, Any]:
    return {"success": False, "operation": operation, "error": error, "errorCode": errorCode}


@action_handler("A2G7M4", "Generating an image")
async def _image(prompt: str, output_path: str, imageDispatcher: Any = None) -> dict[str, Any]:
    result = await generateImage(prompt=prompt, output_path=output_path, dispatcher=imageDispatcher)
    result["operation"] = "image"
    return result


@action_handler("A5A1D8", "Generating audio")
async def _audio(prompt: str, audioDispatcher: Any = None) -> dict[str, Any]:
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        return _failure("audio", "Prompt must contain between 1 and 4000 characters", "INVALID_PROMPT")
    if audioDispatcher is None:
        return _failure("audio", "Forge Voice provider is not configured", "PROVIDER_NOT_CONFIGURED")
    try:
        result = await audioDispatcher.generate(prompt=prompt)
    except DispatcherError as exc:
        code = "PROVIDER_NOT_CONFIGURED" if "not configured" in str(exc).casefold() else "GENERATION_FAILED"
        return _failure("audio", str(exc), code)
    except Exception:
        return _failure("audio", "Forge Voice audio generation failed", "GENERATION_FAILED")
    if not isinstance(result, dict) or result.get("mediaType") != "audio" or not result.get("mediaData"):
        return _failure("audio", "Forge Voice returned an unsupported audio result", "INVALID_PROVIDER_RESULT")
    return {"success": True, "operation": "audio", **result, "error": None, "errorCode": None}


_OPERATIONS = {"image": _image, "audio": _audio}


async def generate(operation: str, **arguments: Any) -> dict[str, Any]:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return _failure(operation, "Unsupported generation operation", "INVALID_OPERATION")
    return await handler(**arguments)


def _actionFactory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = _OPERATIONS.get(arguments.get("operation"))
    if handler is None:
        raise ValueError(f"Unsupported generation operation: {arguments.get('operation')}")
    return handler.__forge_action_factory__(tool_name, arguments)


setattr(generate, "__forge_action_factory__", _actionFactory)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "generate",
        "description": "Generate an image using Forge Canvas or speech audio using Forge Voice local models. Use for explicit media generation, not analysis or transcription.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)},
                "prompt": {"type": "string", "maxLength": 4000},
                "output_path": {"type": "string"},
            },
            "required": ["operation", "prompt"],
            "allOf": [{
                "if": {"properties": {"operation": {"const": "image"}}},
                "then": {"required": ["output_path"]},
            }],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"generate": generate}
