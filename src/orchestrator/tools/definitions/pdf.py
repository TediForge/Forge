"""Bounded PDF text extraction."""

from typing import Any

from orchestrator.computer.workspace import SandboxPathError, safePath, workspaceRelativePath
from orchestrator.tools.actions import action_handler


MAX_PAGES = 500
MAX_TEXT_CHARS = 100_000


@action_handler("A4P8C2", "Extracting PDF text")
def _text(path: str) -> dict[str, Any]:
    try:
        source = safePath(path, "read")
    except SandboxPathError as exc:
        return {"success": False, "operation": "text", "error": str(exc), "errorCode": "PATH_NOT_ALLOWED"}
    if not source.is_file():
        return {"success": False, "operation": "text", "error": "PDF file was not found", "errorCode": "NOT_FOUND"}
    try:
        from pypdf import PdfReader

        reader = PdfReader(source, strict=True)
        if len(reader.pages) > MAX_PAGES:
            return {"success": False, "operation": "text", "error": "PDF exceeds the 500-page limit", "errorCode": "TOO_MANY_PAGES"}
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if len(text) > MAX_TEXT_CHARS:
            return {"success": False, "operation": "text", "error": "Extracted PDF text exceeds the supported size", "errorCode": "CONTENT_TOO_LARGE"}
        return {
            "success": True, "operation": "text", "path": workspaceRelativePath(source),
            "pageCount": len(reader.pages), "text": text, "error": None, "errorCode": None,
        }
    except ImportError:
        return {"success": False, "operation": "text", "error": "pypdf is not installed", "errorCode": "DEPENDENCY_MISSING"}
    except Exception:
        return {"success": False, "operation": "text", "error": "PDF could not be parsed", "errorCode": "INVALID_PDF"}


def pdf(operation: str, **arguments: Any) -> dict[str, Any]:
    if operation != "text":
        return {"success": False, "operation": operation, "error": "Unsupported PDF operation", "errorCode": "INVALID_OPERATION"}
    return _text(**arguments)


setattr(pdf, "__forge_action_factory__", lambda tool_name, arguments: _text.__forge_action_factory__(tool_name, arguments))

TOOLS = [{
    "type": "function",
    "function": {
        "name": "pdf",
        "description": "Extract bounded text from a local PDF in the sandbox. Use for PDF contents, not page rendering or table/image extraction.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["text"]},
                "path": {"type": "string"},
            },
            "required": ["operation", "path"],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"pdf": pdf}
