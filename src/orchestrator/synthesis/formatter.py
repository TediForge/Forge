"""Endpoint-specific deterministic formatting for synthesized results."""

from datetime import datetime, timezone
import json
from typing import Any

from orchestrator.schemas.v1.responses import UnifiedOrchestratorResponse
from orchestrator.security.audit import redact


def _usage(metadata: dict[str, Any]) -> dict[str, int]:
	input_tokens = int(metadata.get("inputTokens", metadata.get("input_tokens", 0)) or 0)
	output_tokens = int(metadata.get("outputTokens", metadata.get("output_tokens", 0)) or 0)
	return {
		"input_tokens": input_tokens,
		"output_tokens": output_tokens,
		"total_tokens": int(metadata.get("totalTokens", metadata.get("total_tokens", input_tokens + output_tokens)) or 0),
	}


def _status(response: UnifiedOrchestratorResponse) -> str:
	status = str(response.metadata.get("status", "completed"))
	if status == "failed":
		return "failed"
	if status in {"stopped_budget", "stopped_circuit_breaker", "summarized"}:
		return "incomplete"
	return "completed"


def _annotations(response: UnifiedOrchestratorResponse) -> list[dict[str, Any]]:
	annotations = []
	text = "".join(block.text or "" for block in response.content if block.type == "text")
	for source in response.sources:
		snippet = source.snippet
		if not snippet:
			continue
		start = text.find(snippet)
		if start < 0:
			continue
		annotations.append({
			"type": "url_citation",
			"url": source.url,
			"title": source.title,
			"start_index": start,
			"end_index": start + len(snippet),
		})
	return annotations


def _text(response: UnifiedOrchestratorResponse) -> str:
	return "".join(block.text or "" for block in response.content if block.type == "text")


def _redact_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
	cleaned = redact(tool_calls)
	for call in cleaned:
		function = call.get("function") if isinstance(call, dict) else None
		arguments = function.get("arguments") if isinstance(function, dict) else None
		if not isinstance(arguments, str):
			continue
		try:
			parsed = json.loads(arguments)
			safe_arguments = redact(parsed)
			function["arguments"] = json.dumps(safe_arguments, ensure_ascii=True, separators=(",", ":"))
		except (json.JSONDecodeError, TypeError):
			continue
	return cleaned


def to_responses(
	response: UnifiedOrchestratorResponse,
	output_items: list[dict[str, Any]] | None = None,
	model: str = "forge",
	created_at: int | None = None,
) -> dict[str, Any]:
	"""Format the unified result as an OpenAI Responses-style object."""
	content_item = {
		"type": "output_text",
		"text": _text(response),
		"annotations": _annotations(response),
	}
	message_item = {
		"id": f"msg_{response.runId}",
		"type": "message",
		"status": "completed",
		"role": "assistant",
		"content": [content_item],
	}
	items = [dict(item) for item in (output_items or [])]
	contains_final_message = any(
		item.get("type") == "message"
		and item.get("role", "assistant") == "assistant"
		and any(part.get("text") == _text(response) for part in item.get("content", []) if isinstance(part, dict))
		for item in items
	)
	if not contains_final_message:
		items.append(message_item)
	created = created_at if created_at is not None else int(datetime.now(timezone.utc).timestamp())
	return {
		"id": response.runId,
		"object": "response",
		"created_at": created,
		"status": _status(response),
		"model": model,
		"output": items,
		"usage": _usage(response.metadata),
		"sources": [source.model_dump(by_alias=True, exclude_none=True) for source in response.sources],
		"mediaAssets": [block.model_dump(by_alias=True, exclude_none=True) for block in response.content if block.type != "text"],
		"actions": [event.model_dump(by_alias=True, exclude_none=True) for event in response.events if getattr(event, "type", None) == "action"],
	}


def to_chat_completion(
	response: UnifiedOrchestratorResponse,
	model: str = "forge",
	created: int | None = None,
	tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
	"""Format the same result as a Chat Completions-compatible response."""
	created = created if created is not None else int(datetime.now(timezone.utc).timestamp())
	message: dict[str, Any] = {"role": "assistant", "content": _text(response)}
	finish_reason = "stop"
	if tool_calls:
		message["tool_calls"] = _redact_tool_calls(tool_calls)
		finish_reason = "tool_calls"
	return {
		"id": f"chatcmpl-{response.runId}",
		"object": "chat.completion",
		"created": created,
		"model": model,
		"choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
		"usage": {
			"prompt_tokens": _usage(response.metadata)["input_tokens"],
			"completion_tokens": _usage(response.metadata)["output_tokens"],
			"total_tokens": _usage(response.metadata)["total_tokens"],
		},
		"sources": [source.model_dump(by_alias=True, exclude_none=True) for source in response.sources],
		"mediaAssets": [block.model_dump(by_alias=True, exclude_none=True) for block in response.content if block.type != "text"],
		"actions": [event.model_dump(by_alias=True, exclude_none=True) for event in response.events if getattr(event, "type", None) == "action"],
	}