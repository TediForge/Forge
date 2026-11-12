"""Deterministic normalization for citations and returned media references."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from orchestrator.schemas.v1.responses import SourceReference
from orchestrator.security.audit import redact


def _mapping(value: Any) -> Mapping[str, Any] | None:
	if isinstance(value, BaseModel):
		return value.model_dump(by_alias=True)
	return value if isinstance(value, Mapping) else None


def _source_candidates(value: Any):
	if isinstance(value, (list, tuple)):
		for item in value:
			yield from _source_candidates(item)
		return

	item = _mapping(value)
	if item is None:
		return
	if item.get("url") and (item.get("title") or item.get("name")):
		yield item
		return
	for key in ("sources", "citations", "results", "items", "data", "output", "result"):
		if key in item:
			yield from _source_candidates(item[key])


def normalize_sources(values: Any) -> list[SourceReference]:
	"""Normalize explicit source records and deduplicate them by URL/title."""
	result: list[SourceReference] = []
	seen: set[tuple[str, str]] = set()
	for candidate in _source_candidates(values):
		data = dict(candidate)
		data.setdefault("title", data.pop("name", None))
		data.setdefault("snippet", data.pop("text", data.pop("description", None)))
		source_type = data.pop("source_type", data.get("sourceType", data.pop("type", "other")))
		if source_type in {"search", "web_search", "url_citation"}:
			source_type = "web"
		elif source_type in {"file", "file_search", "document_search"}:
			source_type = "document"
		elif source_type in {"tool", "integration_result"}:
			source_type = "integration"
		data["sourceType"] = source_type if source_type in {"web", "document", "integration", "other"} else "other"
		try:
			source = SourceReference.model_validate(redact(data))
		except (ValidationError, TypeError):
			continue
		key = (source.url, source.title.casefold())
		if key not in seen:
			seen.add(key)
			result.append(source)
	return result


def _media_candidates(value: Any):
	if isinstance(value, (list, tuple)):
		for item in value:
			yield from _media_candidates(item)
		return

	item = _mapping(value)
	if item is None:
		return
	media_type = item.get("mediaType", item.get("media_type", item.get("type")))
	if media_type and any(key in item for key in ("url", "fileUrl", "mediaData", "data", "assetId", "id")):
		yield item
		return
	for key in ("mediaAssets", "media_assets", "attachments", "files", "assets", "output", "result"):
		if key in item:
			yield from _media_candidates(item[key])


def normalize_media_assets(values: Any) -> list[dict[str, Any]]:
	"""Normalize candidate media records; URL conversion happens before serialization."""
	result: list[dict[str, Any]] = []
	seen: set[tuple[str, str]] = set()
	for candidate in _media_candidates(values):
		data = dict(candidate)
		media_type = data.pop("media_type", data.pop("type", data.get("mediaType", None)))
		data["mediaType"] = media_type
		if "assetId" not in data and "id" in data:
			data["assetId"] = data.pop("id")
		if "url" not in data and "fileUrl" in data:
			data["url"] = data.pop("fileUrl")
		if "mediaData" not in data:
			if isinstance(data.get("data"), str):
				data["mediaData"] = data["data"]
			elif isinstance(data.get("base64"), str):
				data["mediaData"] = data["base64"]
		data.pop("data", None)
		data.pop("base64", None)
		data["mediaType"] = media_type
		try:
			data = dict(redact(data))
		except (ValidationError, TypeError):
			continue
		if not media_type:
			continue
		key = (str(data.get("assetId") or data.get("url") or data.get("mediaData") or ""), str(media_type))
		if key not in seen:
			seen.add(key)
			result.append(data)
	return result