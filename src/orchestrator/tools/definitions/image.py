"""Image inspection and transformation tools."""

import os
from typing import Any
import uuid

from orchestrator.inference.modalities import DispatcherError
from orchestrator.computer.workspace import SandboxPathError, safePath, workspaceRelativePath
from orchestrator.tools.actions import action_handler


@action_handler("A9F3A6", "Reading image metadata")
def info(path: str) -> dict[str, Any]:
    try:
        source = safePath(path, "read")
    except SandboxPathError as exc:
        return {"success": False, "error": str(exc), "errorCode": "PATH_NOT_ALLOWED"}
    if not source.is_file():
        return {"success": False, "error": "Image file was not found", "errorCode": "NOT_FOUND"}

    try:
        from PIL import Image
    except ImportError:
        return {"success": False, "error": "Pillow is not installed", "errorCode": "DEPENDENCY_MISSING"}

    try:
        with Image.open(source) as image:
            return {
                "success": True,
                "path": workspaceRelativePath(source),
                "format": image.format,
                "mode": image.mode,
                "width": image.width,
                "height": image.height,
                "error": None,
                "errorCode": None,
            }
    except OSError:
        return {"success": False, "error": "Image could not be decoded", "errorCode": "IMAGE_ERROR"}


@action_handler("A2H8K1", "Resizing an image")
def resize(path: str, output_path: str, width: int, height: int) -> dict[str, Any]:
    try:
        source = safePath(path, "read")
        destination = safePath(output_path, "write")
    except SandboxPathError as exc:
        return {"success": False, "error": str(exc), "errorCode": "PATH_NOT_ALLOWED"}
    if not source.is_file():
        return {"success": False, "error": "Image file was not found", "errorCode": "NOT_FOUND"}
    if isinstance(width, bool) or isinstance(height, bool) or width < 1 or height < 1 or width > 8192 or height > 8192 or width * height > 40_000_000:
        return {"success": False, "error": "Image dimensions exceed supported limits", "errorCode": "INVALID_DIMENSIONS"}

    try:
        from PIL import Image
    except ImportError:
        return {"success": False, "error": "Pillow is not installed", "errorCode": "DEPENDENCY_MISSING"}

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            resized = image.resize((width, height), Image.Resampling.LANCZOS)
            resized.save(destination)
        return {"success": True, "source": workspaceRelativePath(source), "output": workspaceRelativePath(destination), "width": width, "height": height, "error": None, "errorCode": None}
    except OSError:
        return {"success": False, "error": "Image could not be resized", "errorCode": "IMAGE_ERROR"}


@action_handler("A3W7C2", "Extracting text from an image")
def ocr(path: str) -> dict[str, Any]:
    try:
        source = safePath(path, "read")
    except SandboxPathError as exc:
        return {"success": False, "text": "", "error": str(exc), "errorCode": "PATH_NOT_ALLOWED"}
    if not source.is_file():
        return {"success": False, "text": "", "error": "Image file was not found", "errorCode": "NOT_FOUND"}
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return {"success": False, "text": "", "error": "Pillow and pytesseract are required for OCR", "errorCode": "DEPENDENCY_MISSING"}
    try:
        with Image.open(source) as image:
            text = pytesseract.image_to_string(image)
        return {"success": True, "path": workspaceRelativePath(source), "text": text, "error": None, "errorCode": None}
    except pytesseract.TesseractNotFoundError:
        return {"success": False, "text": "", "error": "Tesseract OCR executable is not installed", "errorCode": "OCR_ENGINE_MISSING"}
    except OSError:
        return {"success": False, "text": "", "error": "Image could not be decoded for OCR", "errorCode": "IMAGE_ERROR"}


@action_handler("A5R2N6", "Generating an image")
async def generate(prompt: str, output_path: str, dispatcher: Any = None) -> dict[str, Any]:
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        return {"success": False, "error": "Prompt must contain between 1 and 4000 characters", "errorCode": "INVALID_PROMPT"}
    try:
        destination = safePath(output_path, "write")
    except SandboxPathError as exc:
        return {"success": False, "error": str(exc), "errorCode": "PATH_NOT_ALLOWED"}
    if destination.exists():
        return {"success": False, "error": "Output file already exists", "errorCode": "OUTPUT_EXISTS"}
    if dispatcher is None:
        return {"success": False, "error": "Forge Canvas provider is not configured", "errorCode": "PROVIDER_NOT_CONFIGURED"}
    try:
        generated = await dispatcher.generate(prompt=prompt)
    except DispatcherError as exc:
        code = "PROVIDER_NOT_CONFIGURED" if "not configured" in str(exc).casefold() else "GENERATION_FAILED"
        return {"success": False, "error": str(exc), "errorCode": code}
    except (RuntimeError, ValueError, OSError):
        return {"success": False, "error": "Forge Canvas image generation failed", "errorCode": "GENERATION_FAILED"}
    images = getattr(generated, "images", None)
    if not images and isinstance(generated, dict):
        images = generated.get("images")
    if not isinstance(images, (list, tuple)) or not images or not callable(getattr(images[0], "save", None)):
        return {"success": False, "error": "Forge Canvas returned an unsupported image result", "errorCode": "INVALID_PROVIDER_RESULT"}
    staging = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}{destination.suffix}")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        images[0].save(staging)
        os.link(staging, destination)
        staging.unlink(missing_ok=True)
        return {
            "success": True, "mediaType": "image",
            "path": workspaceRelativePath(destination), "error": None, "errorCode": None,
        }
    except FileExistsError:
        staging.unlink(missing_ok=True)
        return {"success": False, "error": "Output file already exists", "errorCode": "OUTPUT_EXISTS"}
    except OSError:
        staging.unlink(missing_ok=True)
        return {"success": False, "error": "Generated image could not be saved", "errorCode": "WRITE_ERROR"}


_OPERATIONS = {
    "info": info,
    "resize": resize,
    "ocr": ocr,
    "generate": generate,
}


def image(operation: str, **arguments: Any) -> Any:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return {"success": False, "error": "Unsupported image operation", "errorCode": "INVALID_OPERATION"}
    return handler(**arguments)


def _action_factory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = arguments.get("operation")
    handler = _OPERATIONS.get(operation)
    if handler is None:
        raise ValueError(f"Unsupported image operation: {operation}")
    factory = getattr(handler, "__forge_action_factory__")
    return factory(tool_name, arguments)


setattr(image, "__forge_action_factory__", _action_factory)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "image",
        "description": "Inspect image metadata, resize, OCR, or generate an image. Select exactly one operation.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)},
                "path": {"type": "string"},
                "output_path": {"type": "string"},
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "prompt": {"type": "string"},
            },
            "required": ["operation"],
            "allOf": [
                {"if": {"properties": {"operation": {"const": operation}}}, "then": {"required": required}}
                for operation, required in {
                    "info": ["path"], "resize": ["path", "output_path", "width", "height"],
                        "ocr": ["path"], "generate": ["prompt", "output_path"],
                    }.items()
            ],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"image": image}
