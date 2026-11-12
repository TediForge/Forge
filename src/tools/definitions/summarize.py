"""Bounded extractive summaries of supplied text and allowlisted HTTPS pages."""

from collections import Counter
import base64
from html.parser import HTMLParser
import re
from typing import Any

from src.core.models.adapters.media import MediaConversionError, MediaConverter
from src.tools.actions import action_handler


MAX_TEXT_CHARS = 100_000
_STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was",
    "were", "will", "with",
})


@action_handler("A4S9U2", "Summarizing supplied text")
def _summarizeText(text: str, maxSentences: int = 3) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        return _failure("text", "Text must be non-empty", "INVALID_TEXT")
    if len(text) > MAX_TEXT_CHARS:
        return _failure("text", "Text exceeds the supported size", "TEXT_TOO_LARGE")
    if isinstance(maxSentences, bool) or not isinstance(maxSentences, int) or not 1 <= maxSentences <= 10:
        return _failure("text", "maxSentences must be between 1 and 10", "INVALID_LIMIT")
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text.strip()) if sentence.strip()]
    if len(sentences) <= maxSentences:
        selected = sentences
    else:
        words = [
            word.casefold()
            for sentence in sentences
            for word in re.findall(r"\b[\w'-]+\b", sentence)
            if word.casefold() not in _STOP_WORDS and len(word) > 2
        ]
        frequencies = Counter(words)
        maximum = max(frequencies.values(), default=1)
        scores = []
        for index, sentence in enumerate(sentences):
            terms = [
                word.casefold() for word in re.findall(r"\b[\w'-]+\b", sentence)
                if word.casefold() not in _STOP_WORDS and len(word) > 2
            ]
            score = sum(frequencies[word] / maximum for word in terms) / max(len(terms), 1)
            scores.append((score, -index, index))
        chosen = {index for _, _, index in sorted(scores, reverse=True)[:maxSentences]}
        selected = [sentence for index, sentence in enumerate(sentences) if index in chosen]
    return {
        "success": True, "summary": " ".join(selected), "sentenceCount": len(selected),
        "method": "extractive", "error": None, "errorCode": None,
    }


class _PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth and data.strip():
            self.parts.append(data.strip())


@action_handler("A8C5D3", "Summarizing a URL")
async def _summarizeUrl(url: str, mediaConverter: MediaConverter | None = None, maxSentences: int = 3) -> dict[str, Any]:
    if mediaConverter is None:
        return _failure("url", "URL fetching is not configured", "PROVIDER_NOT_CONFIGURED")
    try:
        page = await mediaConverter.fromUrl(url, max_bytes=2 * 1024 * 1024)
    except MediaConversionError as exc:
        return _failure("url", str(exc), exc.code)
    if not page.mimeType.casefold().startswith(("text/", "application/xhtml+xml")):
        return _failure("url", "URL did not return a text page", "UNSUPPORTED_CONTENT_TYPE")
    try:
        source = base64.b64decode(page.mediaData).decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return _failure("url", "Page content could not be decoded", "INVALID_CONTENT")
    parser = _PageText()
    parser.feed(source)
    text = " ".join(parser.parts) if "html" in page.mimeType.casefold() else source
    if not text.strip():
        return _failure("url", "Page contains no readable text", "EMPTY_CONTENT")
    if len(text) > MAX_TEXT_CHARS:
        return _failure("url", "Page text exceeds the supported size", "CONTENT_TOO_LARGE")
    summary = _summarizeText(text, maxSentences=maxSentences)
    summary["url"] = url
    return summary


def _failure(operation: str, error: str, errorCode: str) -> dict[str, Any]:
    return {"success": False, "operation": operation, "summary": "", "sentenceCount": 0, "error": error, "errorCode": errorCode}


_OPERATIONS = {"text": _summarizeText, "url": _summarizeUrl}


def summarize(operation: str, **arguments: Any) -> dict[str, Any]:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return _failure(operation, "Unsupported summary operation", "INVALID_OPERATION")
    return handler(**arguments)


def _actionFactory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = _OPERATIONS.get(arguments.get("operation"))
    if handler is None:
        raise ValueError(f"Unsupported summary operation: {arguments.get('operation')}")
    return handler.__forge_action_factory__(tool_name, arguments)


setattr(summarize, "__forge_action_factory__", _actionFactory)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "summarize",
        "description": "Create a bounded extractive summary of supplied text or allowlisted HTTPS page content. Use for concise summaries, not paraphrase generation.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)},
                "text": {"type": "string", "maxLength": MAX_TEXT_CHARS},
                "url": {"type": "string"},
                "maxSentences": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
            },
            "required": ["operation"],
            "allOf": [
                {"if": {"properties": {"operation": {"const": operation}}}, "then": {"required": required}}
                for operation, required in {"text": ["text"], "url": ["url"]}.items()
            ],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"summarize": summarize}
