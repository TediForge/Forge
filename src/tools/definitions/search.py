"""Structured web search with optional bounded extraction of public HTTPS pages."""

import ipaddress
import socket
from urllib.parse import urlsplit

from src.tools.actions import action_handler


class PublicSearchError(RuntimeError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


class PublicSearchAdapter:
    """Keep the search provider implementation inside the search tool domain."""

    def search(self, operation: str, query: str, max_results: int, extract_results: int = 0) -> dict:
        try:
            from ddgs import DDGS

            with DDGS() as client:
                if operation == "web":
                    raw = client.text(query, max_results=max_results)
                    results = [{
                        "title": str(item.get("title", "")),
                        "url": str(item.get("href", "")),
                        "snippet": str(item.get("body", "")),
                    } for item in raw]
                    errors = []
                    for result in results[:extract_results]:
                        if not _isPublicHttpsUrl(result["url"]):
                            errors.append({"url": result["url"], "error": "Only public HTTPS pages can be extracted", "errorCode": "URL_NOT_ALLOWED"})
                            continue
                        try:
                            page = client.extract(result["url"], fmt="text_markdown")
                            content = page.get("content", "") if isinstance(page, dict) else ""
                            result["content"] = str(content)[:5000]
                        except Exception:
                            errors.append({"url": result["url"], "error": "Page extraction failed", "errorCode": "EXTRACTION_FAILED"})
                    return {"results": results, "errors": errors}
                if operation == "image":
                    raw = client.images(query, max_results=max_results)
                    return {"results": [{
                        "title": str(item.get("title", "")),
                        "url": str(item.get("image", "")),
                        "thumbnail": str(item.get("thumbnail", "")),
                        "source": str(item.get("url", "")),
                    } for item in raw]}
                if operation == "news":
                    raw = client.news(query, max_results=max_results)
                    return {"results": [{
                        "title": str(item.get("title", "")),
                        "url": str(item.get("url", "")),
                        "snippet": str(item.get("body", "")),
                        "date": str(item.get("date", "")),
                        "source": str(item.get("source", "")),
                    } for item in raw]}
        except Exception as exc:
            if "rate" in type(exc).__name__.casefold() and "limit" in type(exc).__name__.casefold():
                raise PublicSearchError("Search rate limit reached", "RATE_LIMITED") from exc
            raise PublicSearchError("Search provider is unavailable", "SEARCH_UNAVAILABLE") from exc
        raise PublicSearchError("Unsupported search operation", "INVALID_OPERATION")


def _isPublicHttpsUrl(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").rstrip(".").casefold()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return False
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            ]
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


@action_handler("A78ORH", "Searching the public web")
def _web(query: str, maxResults: int = 5, extractResults: int = 0, provider: PublicSearchAdapter | None = None) -> dict:
    if not isinstance(query, str) or not query.strip():
        return {
            "success": False, "query": str(query), "results": [],
            "error": "A non-empty query is required", "errorCode": "INVALID_QUERY",
        }
    maxResults = max(1, min(int(maxResults), 10))
    extractResults = max(0, min(int(extractResults), 3, maxResults))

    try:
        result = (provider or PublicSearchAdapter()).search("web", query, maxResults, extractResults)
        results, errors = result["results"], result["errors"]
    except PublicSearchError as exc:
        return {
            "success": False,
            "query": query,
            "results": [],
            "error": str(exc),
            "errorCode": exc.code,
        }

    return {
        "success": True,
        "query": query,
        "maxResults": maxResults,
        "results": results,
        "errors": errors,
    }


@action_handler("A2I4M6", "Searching for images")
def _image(query: str, maxResults: int = 5, provider: PublicSearchAdapter | None = None) -> dict:
    return _searchCollection("image", query, maxResults, provider)


@action_handler("A7N3W5", "Searching the news")
def _news(query: str, maxResults: int = 5, provider: PublicSearchAdapter | None = None) -> dict:
    return _searchCollection("news", query, maxResults, provider)


def _searchCollection(operation: str, query: str, maxResults: int, provider: PublicSearchAdapter | None) -> dict:
    if not isinstance(query, str) or not query.strip():
        return {"success": False, "operation": operation, "query": str(query), "results": [], "error": "A non-empty query is required", "errorCode": "INVALID_QUERY"}
    limit = max(1, min(int(maxResults), 10))
    try:
        result = (provider or PublicSearchAdapter()).search(operation, query, limit)
    except PublicSearchError as exc:
        return {"success": False, "operation": operation, "query": query, "results": [], "error": str(exc), "errorCode": exc.code}
    return {"success": True, "operation": operation, "query": query, "maxResults": limit, **result, "error": None, "errorCode": None}


_OPERATIONS = {"web": _web, "image": _image, "news": _news}


def search(operation: str, provider: PublicSearchAdapter | None = None, **params) -> dict:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return {
            "success": False,
            "operation": operation,
            "error": "Unsupported search operation",
            "errorCode": "INVALID_OPERATION",
        }
    return handler(provider=provider, **params)


def _action_factory(tool_name: str, arguments: dict) -> dict:
    operation = arguments.get("operation")
    handler = _OPERATIONS.get(operation)
    if handler is None:
        raise ValueError(f"Unsupported search operation: {operation}")
    return handler.__forge_action_factory__(tool_name, arguments)


setattr(search, "__forge_action_factory__", _action_factory)


TOOLS = [{
    "type": "function",
    "function": {
        "name": "search",
        "description": (
            "Search the public web, images, or news. Use operation='web' for current facts and "
            "source citations; set extractResults from 1 to 3 only when you need page evidence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)},
                "query": {"type": "string"},
                "maxResults": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                "extractResults": {"type": "integer", "minimum": 0, "maximum": 3, "default": 0},
            },
            "required": ["operation", "query"],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"search": search}
