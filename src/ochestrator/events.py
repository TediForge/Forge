"""Translate SDK stream events into Forge's public event vocabulary."""

from collections.abc import AsyncIterator
from typing import Any


def to_forge_event(event: Any) -> dict[str, Any] | None:
    event_type = getattr(event, "type", None)
    if event_type != "raw_response_event":
        return None

    response_event = getattr(event, "data", None)
    response_event_type = getattr(response_event, "type", None)
    if response_event_type not in {"response.output_text.delta", "output_text_delta"}:
        return None

    content = getattr(response_event, "delta", None)
    if not isinstance(content, str) or not content:
        return None
    return {"type": "textChunk", "data": {"content": content}}


async def forward_runner_events(streamed_result: Any) -> AsyncIterator[dict[str, Any]]:
    content = ""
    async for event in streamed_result.stream_events():
        forge_event = to_forge_event(event)
        if forge_event is not None:
            content += forge_event["data"]["content"]
            yield forge_event
    yield {"type": "complete", "data": {"content": content}}