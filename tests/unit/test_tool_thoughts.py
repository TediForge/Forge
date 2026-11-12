import asyncio
import json
from types import SimpleNamespace

from orchestrator.engine.engine import ExecutionPlan, ExecutionStep, ForgeEngine
from orchestrator.context.limits import ExecutionBudget
from orchestrator.context.state import ExecutionState
from orchestrator.synthesis.output import OutputSynthesizer


class FakeToolExecutor:
    def __init__(self):
        self.calls = []

    async def executeAsync(self, toolCall, context=None):
        name = toolCall["function"]["name"]
        self.calls.append(name)
        return {"success": True, "metadata": {}}


def test_multi_tool_step_emits_action_lifecycle_and_deprecated_legacy_thoughts():
    engine = ForgeEngine(text_dispatcher=SimpleNamespace(generate=lambda **kwargs: "answer"))
    toolIds = {"search": "A78ORH", "calculate": "A4M9Q2"}
    engine.toolRegistry = SimpleNamespace(actionFor=lambda name, arguments: {
        "actionId": toolIds[name],
        "actionType": "tool",
        "toolName": name,
        "message": f"Running {name}",
        "metadata": {},
    })
    executor = FakeToolExecutor()
    engine.toolExecutor = executor
    state = ExecutionState("run-tools")
    state.setVariable("toolArguments", {"search": {"query": "weather"}, "calculate": {"expression": "2+2"}})
    plan = ExecutionPlan(reasoning="Two registered tools", steps=[
        ExecutionStep(
            step_id=1,
            modality="text",
            capability="research",
            task_instruction="Search and calculate",
            tool_calls=["search", "calculate"],
        ),
    ])

    async def collect():
        return [event async for event in engine._executeGraphStream(plan, state, ExecutionBudget(engine.executionLimits))]

    events = asyncio.run(collect())
    actions = [event["data"] for event in events if event["type"] == "action"]
    statuses = [event["data"]["status"] for event in events if event["type"] == "status"]
    legacyThoughts = [
        event["data"] for event in events
        if event["type"] == "thought" and event["data"].get("data", {}).get("deprecated")
    ]

    assert executor.calls == ["search", "calculate"]
    assert statuses == ["started", "planned", "completed"]
    assert [(action["actionId"], action["status"]) for action in actions] == [
        ("A78ORH", "started"), ("A78ORH", "processing"), ("A78ORH", "completed"),
        ("A4M9Q2", "started"), ("A4M9Q2", "processing"), ("A4M9Q2", "completed"),
    ]
    assert [(thought["id"], thought["data"]["deprecated"]) for thought in legacyThoughts] == [
        ("T78ORH", True), ("T4M9Q2", True),
    ]


def test_action_metadata_is_redacted_in_stream_and_static_response():
    async def events():
        yield {
            "type": "action",
            "data": {
                "actionId": "A5Q8V3",
                "actionType": "integration",
                "toolName": "design",
                "status": "completed",
                "message": "Created a design",
                "metadata": {"authorization": "secret", "designType": "poster"},
            },
        }

    async def collect():
        return [frame async for frame in OutputSynthesizer.synthesizeStream("run-redaction", events())]

    frames = asyncio.run(collect())
    action_frame = json.loads(frames[0].split("data: ", 1)[1].strip())
    complete_frame = json.loads(frames[-1].split("data: ", 1)[1].strip())
    assert action_frame["data"]["metadata"]["authorization"] == "[REDACTED]"
    action = next(event for event in complete_frame["data"]["events"] if event["type"] == "action")
    assert action["metadata"]["authorization"] == "[REDACTED]"
