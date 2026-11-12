import asyncio
import json

from src.synthesis import OutputSynthesizer, aggregate_output_items


def test_aggregation_excludes_reasoning_and_collects_explicit_sources_and_assets():
	result = aggregate_output_items([
		{"type": "reasoning", "summary": "private reasoning"},
		{"type": "function_call_output", "call_id": "call-1", "output": {
			"sources": [{"title": "Docs", "url": "https://example.test/docs", "sourceType": "web"}],
			"mediaAssets": [{"type": "image", "assetId": "asset-1", "url": "https://cdn.test/image.png", "mediaData": "unused"}],
		}},
		{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Found it."}]},
	])

	assert result.content == "Found it."
	assert len(result.output_items) == 2
	assert result.sources[0].title == "Docs"
	assert result.media_assets[0]["assetId"] == "asset-1"
	assert result.media_assets[0]["mediaData"] == "unused"


def test_responses_and_chat_completion_formatters_exclude_private_reasoning():
	response = OutputSynthesizer.synthesizeStatic(
		"run-1",
		"The answer is documented.",
		sources=[{"title": "Docs", "url": "https://example.test/docs", "snippet": "documented"}],
	)
	items = [
		{"type": "reasoning", "summary": "do not return this"},
		{"type": "function_call", "call_id": "call-1", "name": "search", "arguments": "{}"},
	]

	responses = OutputSynthesizer.toResponses(response, items, createdAt=100)
	chat = OutputSynthesizer.toChatCompletion(
		response,
		created=100,
		toolCalls=[{"id": "call-2", "function": {"name": "search", "arguments": '{"apiKey":"secret"}'}}],
	)

	assert responses["object"] == "response"
	assert responses["created_at"] == 100
	assert [item["type"] for item in responses["output"]] == ["function_call", "message"]
	assert responses["output"][-1]["content"][0]["annotations"][0]["url"] == "https://example.test/docs"
	assert "reasoning" not in str(responses)
	assert chat["object"] == "chat.completion"
	assert chat["choices"][0]["message"]["content"] == "The answer is documented."
	assert chat["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] == '{"apiKey":"[REDACTED]"}'


def test_partial_failure_policy_keeps_partial_content_and_hides_raw_error():
	response = OutputSynthesizer.synthesizeStatic(
		"run-2", "Useful partial answer", failures=[{"code": "FAILED", "message": "secret token leaked"}],
	)

	assert "".join(block.text or "" for block in response.content) == "Useful partial answer"
	assert response.metadata["status"] == "summarized"
	assert response.metadata["partialFailures"][0]["message"] == "An execution step failed."
	assert "secret token leaked" not in str(response.model_dump())


def test_failure_without_partial_content_returns_failed_response():
	response = OutputSynthesizer.synthesizeStatic("run-3", "", failures=["failed"])

	assert response.metadata["status"] == "failed"
	assert response.content


def test_synthesis_normalizes_thought_message_status_and_data():
	response = OutputSynthesizer.synthesizeStatic(
		"run-thought",
		"answer",
		reasoningLogs=[{"id": "T9N3Q7", "message": "  ", "status": "failed", "data": None}],
	)

	thought = response.events[0]
	assert thought.message == "Progress update"
	assert thought.status == "completed"
	assert thought.data == {}


def test_stream_complete_event_matches_emitted_timeline():
	async def events():
		yield {"type": "thought", "data": {
			"id": "T9N3Q7", "type": "thought", "message": "Working", "status": "processing",
		}}
		yield {"type": "action", "data": {
			"actionId": "A123AB", "actionType": "tool", "status": "completed", "message": "Done",
		}}
		yield {"type": "status", "data": {"status": "completed", "stepCount": 1}}

	async def collect():
		return [frame async for frame in OutputSynthesizer.synthesizeStream("run-stream", events())]

	frames = asyncio.run(collect())
	packets = [json.loads(frame.split("data: ", 1)[1]) for frame in frames]
	emitted = [
		packet["data"]
		for packet in packets
		if packet["type"] == "event" and packet["data"]["type"] in {"thought", "action", "status"}
	]
	complete = next(packet["data"] for packet in packets if packet["type"] == "complete")
	assert complete["events"] == emitted
