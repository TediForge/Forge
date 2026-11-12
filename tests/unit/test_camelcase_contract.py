import json
import re

from fastapi import FastAPI

from src.api.v1.responses.http import router
from src.core.schemas.input import OrchestratorRequest
from src.core.schemas.output import (
    ActionRecord,
    CompleteStreamEvent,
    ContentBlock,
    EventStreamEvent,
    FunctionCall,
    FunctionCallStreamEvent,
    MediaStreamEvent,
    RunStatus,
    TextChunkData,
    TextChunkStreamEvent,
    Thought,
    UnifiedOrchestratorResponse,
)


def test_request_contract_uses_tools_reasoning_and_messages_for_resume():
    request = OrchestratorRequest.model_validate({
        "messages": [{
            "type": "function_call_output",
            "call_id": "call_123456",
            "output": "ok",
        }],
        "tools": [],
        "previous_response_id": "run-1",
        "reasoning": {"effort": "xhigh"},
        "metadata": {"trainingExport": True},
    })
    dumped = request.model_dump(by_alias=True)
    assert dumped["tools"] == []
    assert dumped["previous_response_id"] == "run-1"
    assert dumped["messages"][0]["call_id"] == "call_123456"
    assert dumped["reasoning"]["effort"] == "xhigh"
    assert dumped["metadata"]["trainingExport"] is True
    assert not {
        "externalTools", "external_tools", "functionCallOutputs",
        "function_call_outputs", "trainingExport", "topology", "sessionId",
    } & dumped.keys()


def test_response_round_trip_keeps_ordered_content_and_call_id_exception():
    response = UnifiedOrchestratorResponse(
        runId="run-1",
        functionCalls=[FunctionCall(call_id="call_123456", name="lookup", arguments="{}")],
        events=[
            Thought(id="T123AB", message="Working"),
            ActionRecord(actionId="A123AB", actionType="tool", status="completed", message="Looked up"),
            RunStatus(status="completed"),
        ],
        content=[
            ContentBlock(type="text", text="before"),
            ContentBlock(type="text", text="after"),
        ],
    )
    dumped = json.loads(response.model_dump_json(by_alias=True))
    assert [block["text"] for block in dumped["content"]] == ["before", "after"]
    assert dumped["functionCalls"][0]["call_id"] == "call_123456"
    assert "callId" not in dumped["functionCalls"][0]
    assert "mediaAssets" not in dumped
    assert "thoughts" not in dumped and "actions" not in dumped


def test_stream_event_data_keys_are_camelcase_and_openapi_has_canonical_names():
    events = [
        EventStreamEvent(runId="r", sequence=1, data=Thought(id="T123AB", message="Working")),
        EventStreamEvent(runId="r", sequence=2, data=ActionRecord(
            actionId="A123AB", actionType="tool", status="completed", message="Done",
        )),
        EventStreamEvent(runId="r", sequence=3, data=RunStatus(status="completed")),
        TextChunkStreamEvent(runId="r", sequence=4, data=TextChunkData(content="hello")),
        FunctionCallStreamEvent(runId="r", sequence=5, data=FunctionCall(
            call_id="call_123456", name="lookup", arguments="{}",
        )),
        CompleteStreamEvent(runId="r", sequence=6, data=UnifiedOrchestratorResponse(runId="r")),
    ]
    assert [event.type for event in events] == [
        "event", "event", "event", "textChunk", "function_call", "complete",
    ]
    assert events[0].model_dump(by_alias=True)["data"]["type"] == "thought"
    assert events[4].model_dump(by_alias=True)["data"]["call_id"] == "call_123456"

    app = FastAPI()
    app.include_router(router)
    schemas = app.openapi()["components"]["schemas"]
    request_properties = schemas["OrchestratorRequest"]["properties"]
    response_properties = schemas["UnifiedOrchestratorResponse"]["properties"]
    assert {"tools", "reasoning", "previous_response_id", "metadata"} <= request_properties.keys()
    assert {"functionCalls", "runId", "content", "events"} <= response_properties.keys()
    assert "title" not in response_properties
    for schema_name in (
        "OrchestratorRequest",
        "UnifiedOrchestratorResponse",
        "Thought",
        "ActionRecord",
        "RunStatus",
        "FunctionCall",
        "ContentBlock",
        "SourceReference",
    ):
        for field in schemas[schema_name].get("properties", {}):
            assert not re.search(r"_[a-z]", field) or field in {"call_id", "previous_response_id"}, (schema_name, field)
    assert schemas["FunctionCall"]["properties"].get("call_id") is not None


def test_native_request_uses_messages_with_per_turn_base64_attachments():
    request = OrchestratorRequest.model_validate({
        "messages": [
            {"role": "user", "content": "Review this"},
            {
                "role": "user",
                "content": "Describe this image",
                "attachments": [{
                    "fileId": "file-1",
                    "fileName": "pixel.png",
                    "mimeType": "image/png",
                    "fileData": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jO7sAAAAASUVORK5CYII=",
                }],
            },
        ],
    })
    payload = request.model_dump(by_alias=True)
    assert payload["messages"][1]["attachments"][0]["fileData"].startswith("iVBOR")
    assert "prompt" not in payload
    assert "attachments" not in payload
    assert "history" not in payload

    import pytest

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        OrchestratorRequest.model_validate({"prompt": "not accepted"})
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        OrchestratorRequest.model_validate({
            "messages": [{"role": "user", "content": "url media"}],
            "attachments": [],
        })


def test_stream_events_discriminate_packet_and_timeline_types():
    import pytest
    from pydantic import TypeAdapter, ValidationError
    from src.core.schemas.output import StreamEvent

    adapter = TypeAdapter(StreamEvent)
    parsed = adapter.validate_python({
        "type": "event",
        "runId": "r",
        "sequence": 1,
        "data": {"type": "thought", "id": "T123AB", "message": "Working"},
    })
    assert isinstance(parsed, EventStreamEvent)
    assert parsed.data.type == "thought"
    with pytest.raises(ValidationError):
        adapter.validate_python({
            "type": "event", "runId": "r", "sequence": 1,
            "data": {"type": "unknown"},
        })


def test_stream_complete_timeline_matches_emitted_event_packets():
    import asyncio

    from src.synthesis.output import OutputSynthesizer

    async def source():
        yield {"type": "thought", "data": {"id": "T123AB", "message": "Starting"}}
        yield {"type": "action", "data": {
            "actionId": "A123AB", "actionType": "tool", "status": "completed", "message": "Done",
        }}
        yield {"type": "status", "data": {"status": "completed"}}

    frames = asyncio.run(_collect(OutputSynthesizer.synthesizeStream("r", source())))
    eventPackets = [
        json.loads(frame.split("data: ", 1)[1])
        for frame in frames
        if frame.startswith("event: event\n")
    ]
    complete = json.loads(next(frame.split("data: ", 1)[1] for frame in frames if frame.startswith("event: complete\n")))
    emittedTimeline = [packet["data"] for packet in eventPackets]
    assert emittedTimeline == complete["data"]["events"]


async def _collect(generator):
    return [frame async for frame in generator]
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        OrchestratorRequest.model_validate({
            "messages": [{
                "role": "user",
                "content": "url media",
                "attachments": [{
                    "fileId": "file-1",
                    "fileName": "image.png",
                    "mimeType": "image/png",
                    "fileUrl": "https://example.test/image.png",
                }],
            }],
        })
