"""Aggregate public message/tool outputs while excluding private reasoning."""

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any

from orchestrator.security.audit import redact
from orchestrator.synthesis.normalizer import normalize_media_assets, normalize_sources


@dataclass
class AggregatedOutput:
	content: str = ""
	output_items: list[dict[str, Any]] = field(default_factory=list)
	sources: list[Any] = field(default_factory=list)
	media_assets: list[Any] = field(default_factory=list)
	failures: list[dict[str, Any]] = field(default_factory=list)


def _as_dict(value: Any) -> dict[str, Any] | None:
	if hasattr(value, "model_dump"):
		return value.model_dump(by_alias=True)
	return dict(value) if isinstance(value, Mapping) else None


def _message_text(content: Any) -> str:
	if isinstance(content, str):
		return content
	if not isinstance(content, list):
		return ""
	parts = []
	for part in content:
		if isinstance(part, Mapping) and part.get("type") in {"output_text", "text"}:
			text = part.get("text")
			if isinstance(text, str):
				parts.append(text)
	return "".join(parts)


def aggregate_output_items(items: list[Any] | None) -> AggregatedOutput:
	"""Collect final assistant text, executed calls, citations, media, and failures."""
	result = AggregatedOutput()
	messages: list[str] = []
	for raw_item in items or []:
		item = _as_dict(raw_item)
		if item is None:
			continue
		item_type = str(item.get("type", "")).casefold()
		if item_type in {"reasoning", "thought", "chain_of_thought", "internal_reasoning"}:
			continue
		if item_type in {"source", "citations", "mediaasset", "media_asset", "attachment"}:
			if item_type in {"source", "citations"}:
				result.sources.extend(normalize_sources(item))
			else:
				result.media_assets.extend(normalize_media_assets(item))
			continue
		result.sources.extend(normalize_sources(item))
		result.media_assets.extend(normalize_media_assets(item))
		if item_type == "message":
			role = item.get("role", "assistant")
			if role == "assistant":
				text = _message_text(item.get("content"))
				if text:
					messages.append(text)
			result.output_items.append(redact(item))
		elif item_type in {"function_call", "function_call_output", "web_search_call", "file_search_call", "tool_call", "tool_result"}:
			result.output_items.append(redact(item))
		elif item_type in {"error", "failed", "failure"} or item.get("status") == "failed":
			result.failures.append({"code": item.get("code"), "message": item.get("message", item.get("error"))})
	result.content = "\n".join(messages).strip()
	result.sources = normalize_sources(result.sources)
	result.media_assets = normalize_media_assets(result.media_assets)
	return result