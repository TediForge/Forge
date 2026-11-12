"""Bounded public HTTPS retrieval for text, JSON, and PDF content."""

import base64
from html.parser import HTMLParser
import io
import json
from typing import Any

from src.core.models.adapters.media import MediaConversionError, MediaConverter
from src.tools.actions import action_handler


MAX_FETCH_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 100_000


class _TextContent(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def _failure(operation: str, error: str, errorCode: str) -> dict[str, Any]:
    return {"success": False, "operation": operation, "error": error, "errorCode": errorCode}


async def _retrieve(operation: str, url: str, mediaConverter: MediaConverter | None) -> dict[str, Any]:
    if mediaConverter is None:
        return _failure(operation, "URL retrieval is not configured", "PROVIDER_NOT_CONFIGURED")
    try:
        payload = await mediaConverter.fromUrl(url, max_bytes=MAX_FETCH_BYTES)
    except MediaConversionError as exc:
        return _failure(operation, str(exc), exc.code)
    try:
        raw = base64.b64decode(payload.mediaData, validate=True)
        if operation == "json":
            data = json.loads(raw.decode("utf-8-sig"))
            return {"success": True, "operation": operation, "url": url, "data": data, "error": None, "errorCode": None}
        if operation == "pdf":
            return _pdfContent(raw, url)
        if not payload.mimeType.casefold().startswith(("text/", "application/xhtml+xml")):
            return _failure(operation, "URL did not return a text page", "UNSUPPORTED_CONTENT_TYPE")
        source = raw.decode("utf-8-sig", errors="replace")
        if "html" in payload.mimeType.casefold() or "xhtml" in payload.mimeType.casefold():
            parser = _TextContent()
            parser.feed(source)
            source = " ".join(parser.parts)
        if not source.strip():
            return _failure(operation, "The page contains no readable text", "EMPTY_CONTENT")
        if len(source) > MAX_TEXT_CHARS:
            return _failure(operation, "Page text exceeds the supported size", "CONTENT_TOO_LARGE")
        return {"success": True, "operation": operation, "url": url, "content": source, "error": None, "errorCode": None}
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return _failure(operation, "Fetched content could not be decoded", "INVALID_CONTENT")


def _pdfContent(raw: bytes, url: str) -> dict[str, Any]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw), strict=True)
        if len(reader.pages) > 500:
            return _failure("pdf", "PDF exceeds the 500-page limit", "TOO_MANY_PAGES")
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        if len(text) > MAX_TEXT_CHARS:
            return _failure("pdf", "Extracted PDF text exceeds the supported size", "CONTENT_TOO_LARGE")
        return {"success": True, "operation": "pdf", "url": url, "pageCount": len(reader.pages), "text": text, "error": None, "errorCode": None}
    except ImportError:
        return _failure("pdf", "pypdf is not installed", "DEPENDENCY_MISSING")
    except Exception:
        return _failure("pdf", "PDF content could not be parsed", "INVALID_PDF")


@action_handler("A3F8Q1", "Fetching a URL")
async def _url(url: str, mediaConverter: MediaConverter | None = None) -> dict[str, Any]:
    return await _retrieve("url", url, mediaConverter)


@action_handler("A6F2J9", "Fetching a PDF")
async def _pdf(url: str, mediaConverter: MediaConverter | None = None) -> dict[str, Any]:
    return await _retrieve("pdf", url, mediaConverter)


@action_handler("A9D4K7", "Fetching JSON")
async def _json(url: str, mediaConverter: MediaConverter | None = None) -> dict[str, Any]:
    return await _retrieve("json", url, mediaConverter)


_OPERATIONS = {"url": _url, "pdf": _pdf, "json": _json}


async def fetch(operation: str, **arguments: Any) -> dict[str, Any]:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return _failure(operation, "Unsupported fetch operation", "INVALID_OPERATION")
    return await handler(**arguments)


def _actionFactory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = _OPERATIONS.get(arguments.get("operation"))
    if handler is None:
        raise ValueError(f"Unsupported fetch operation: {arguments.get('operation')}")
    return handler.__forge_action_factory__(tool_name, arguments)


setattr(fetch, "__forge_action_factory__", _actionFactory)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "fetch",
        "description": "Retrieve text pages, JSON, or PDF text from allowlisted public HTTPS URLs. Use to inspect a known URL; do not use for local files or web search.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)},
                "url": {"type": "string", "format": "uri"},
            },
            "required": ["operation", "url"],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"fetch": fetch}
