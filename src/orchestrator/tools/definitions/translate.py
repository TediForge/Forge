"""Local-model text and document translation operations."""

from typing import Any

from orchestrator.inference.modalities import DispatcherError
from orchestrator.sandbox.pathPolicy import SandboxPathError, safePath, workspaceRelativePath
from orchestrator.tools.actions import action_handler


MAX_TEXT_CHARS = 100_000


def _failure(operation: str, error: str, errorCode: str) -> dict[str, Any]:
    return {"success": False, "operation": operation, "translation": "", "error": error, "errorCode": errorCode}


@action_handler("A2T6V8", "Translating text")
async def _text(text: str, target_language: str, dispatcher: Any = None) -> dict[str, Any]:
    return await _translate("text", text, target_language, dispatcher)


@action_handler("A7D1K4", "Translating a document")
async def _document(path: str, target_language: str, dispatcher: Any = None) -> dict[str, Any]:
    try:
        source = safePath(path, "read")
    except SandboxPathError as exc:
        return _failure("document", str(exc), "PATH_NOT_ALLOWED")
    if not source.is_file():
        return _failure("document", "Document was not found", "NOT_FOUND")
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return _failure("document", "Document must be a readable UTF-8 text file", "READ_ERROR")
    result = await _translate("document", text, target_language, dispatcher)
    if result["success"]:
        result["path"] = workspaceRelativePath(source)
    return result


async def _translate(operation: str, text: str, target_language: str, dispatcher: Any) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        return _failure(operation, "Text must be non-empty", "INVALID_TEXT")
    if len(text) > MAX_TEXT_CHARS:
        return _failure(operation, "Text exceeds the supported size", "TEXT_TOO_LARGE")
    if not isinstance(target_language, str) or not target_language.strip() or len(target_language) > 100:
        return _failure(operation, "A target language is required", "INVALID_LANGUAGE")
    if dispatcher is None:
        return _failure(operation, "Forge Text provider is not configured", "PROVIDER_NOT_CONFIGURED")
    prompt = (
        f"Translate the following text into {target_language.strip()}. "
        "Preserve meaning and formatting. Return only the translation.\n\n"
        f"{text}"
    )
    try:
        translation = await dispatcher.generate(prompt=prompt, max_new_tokens=4096, temperature=0)
    except DispatcherError as exc:
        code = "PROVIDER_NOT_CONFIGURED" if "not configured" in str(exc).casefold() else "TRANSLATION_FAILED"
        return _failure(operation, str(exc), code)
    except Exception:
        return _failure(operation, "Forge Text translation failed", "TRANSLATION_FAILED")
    if not isinstance(translation, str) or not translation.strip():
        return _failure(operation, "Forge Text returned an empty translation", "INVALID_PROVIDER_RESULT")
    return {"success": True, "operation": operation, "translation": translation, "error": None, "errorCode": None}


_OPERATIONS = {"text": _text, "document": _document}


async def translate(operation: str, **arguments: Any) -> dict[str, Any]:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return _failure(operation, "Unsupported translation operation", "INVALID_OPERATION")
    return await handler(**arguments)


def _actionFactory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = _OPERATIONS.get(arguments.get("operation"))
    if handler is None:
        raise ValueError(f"Unsupported translation operation: {arguments.get('operation')}")
    return handler.__forge_action_factory__(tool_name, arguments)


setattr(translate, "__forge_action_factory__", _actionFactory)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "translate",
        "description": "Translate supplied text or a UTF-8 text document using the configured local Forge Text model. Use for explicit translation requests, not summarization.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)},
                "text": {"type": "string", "maxLength": MAX_TEXT_CHARS},
                "path": {"type": "string"},
                "target_language": {"type": "string", "maxLength": 100},
            },
            "required": ["operation", "target_language"],
            "allOf": [
                {"if": {"properties": {"operation": {"const": "text"}}}, "then": {"required": ["text"]}},
                {"if": {"properties": {"operation": {"const": "document"}}}, "then": {"required": ["path"]}},
            ],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"translate": translate}
