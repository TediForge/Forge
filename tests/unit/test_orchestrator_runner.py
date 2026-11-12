import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents import function_tool

from src.ochestrator.events import to_forge_event
from src.ochestrator.events import forward_runner_events
from src.ochestrator.runner import OrchestrationRunner, build_agent


@function_tool
def lookup_value() -> str:
    """Return a fixed test value."""
    return "value"


def test_build_agent_attaches_agent_owned_tools_and_handoffs():
    specialist = build_agent(name="research", instructions="Research carefully")

    manager = build_agent(
        name="manager",
        instructions="Delegate when appropriate",
        tools=[lookup_value],
        handoffs=[specialist],
    )

    assert [tool.name for tool in manager.tools] == ["lookup_value"]
    assert manager.handoffs == [specialist]


def test_runner_run_uses_sdk_runner_with_agent_context():
    agent = build_agent(name="assistant", instructions="Be concise")
    context = {"tenant_id": "tenant-test"}
    expected = object()

    with patch("src.ochestrator.runner.Runner.run", new=AsyncMock(return_value=expected)) as run:
        result = asyncio.run(OrchestrationRunner(agent).run("Hello", context=context))

    assert result is expected
    run.assert_awaited_once_with(agent, input="Hello", context=context, run_config=None)


def test_text_delta_becomes_forge_text_chunk():
    event = SimpleNamespace(
        type="raw_response_event",
        data=SimpleNamespace(type="response.output_text.delta", delta="Hello"),
    )

    assert to_forge_event(event) == {"type": "textChunk", "data": {"content": "Hello"}}


def test_non_text_sdk_events_are_not_misreported_as_thoughts():
    event = SimpleNamespace(
        type="run_item_stream_event",
        name="tool_called",
        item=SimpleNamespace(type="tool_call_item"),
    )

    assert to_forge_event(event) is None


def test_forward_runner_events_yields_only_forge_events():
    events = [
        SimpleNamespace(
            type="raw_response_event",
            data=SimpleNamespace(type="response.output_text.delta", delta="Hello"),
        ),
        SimpleNamespace(type="agent_updated_stream_event"),
    ]

    class StreamedResult:
        async def stream_events(self):
            for event in events:
                yield event

    async def collect_events():
        return [event async for event in forward_runner_events(StreamedResult())]

    assert asyncio.run(collect_events()) == [
        {"type": "textChunk", "data": {"content": "Hello"}},
        {"type": "complete", "data": {"content": "Hello"}},
    ]