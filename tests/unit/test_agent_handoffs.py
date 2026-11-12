import asyncio
from types import SimpleNamespace

import pytest

from orchestrator.agents import AgentRegistry, create_default_agents
from orchestrator.agents.base import AgentExecutionError, BaseAgent
from orchestrator.context.limits import ExecutionBudget
from orchestrator.context.state import ExecutionState
from orchestrator.engine.engine import ExecutionPlan, ExecutionStep, ForgeEngine


def test_data_agent_handoff_runs_media_sequentially():
    prompts = []

    def generate(prompt=None, **_kwargs):
        prompts.append(prompt)
        if "Render a chart or visual" in prompt:
            return "Rendered chart: outputs/chart.png"
        return "Revenue increased by 20%."

    registry = AgentRegistry(create_default_agents(SimpleNamespace(generate=generate)))
    state = ExecutionState("handoff-run")
    data_agent = registry.get("data")

    result = asyncio.run(registry.collaborate(
        data_agent,
        "Analyze revenue.csv and create a chart",
        state,
        task_id=7,
    ))

    assert "Revenue increased by 20%." in result
    assert "Rendered chart: outputs/chart.png" in result
    assert len(prompts) == 2
    assert "Revenue increased by 20%." in prompts[1]
    handoff = state.getAgentMessages(kind="handoff")[0]
    assert handoff["recipient"] == "media"
    assert handoff["metadata"]["accepted"] is True
    assert handoff["metadata"]["status"] == "completed"
    handoff_result = state.getAgentMessages(kind="handoff_result")[0]
    assert handoff_result["recipient"] == "data"


def test_agent_handoff_cycles_are_rejected():
    class HandoffAgent(BaseAgent):
        name = "cycle"
        skillName = "coding"
        capabilities = frozenset({"cycle"})

        async def execute(self, instruction, state, task_id=None):
            self.handoff(state, "cycle", task_id or 0, "repeat")
            return "result"

    agent = HandoffAgent()
    registry = AgentRegistry([agent])
    with pytest.raises(AgentExecutionError, match="cycle detected"):
        asyncio.run(registry.collaborate(agent, "start", ExecutionState("cycle-run")))


def test_streaming_engine_executes_handoffs_before_completing_step():
    class Dispatcher:
        async def stream(self, prompt=None, **_kwargs):
            yield "Revenue increased by 20%."

        def generate_text(self, prompt=None, **_kwargs):
            if "Render a chart or visual" in prompt:
                return "Rendered chart: outputs/chart.png"
            return "Revenue increased by 20%."

    async def run():
        dispatcher = Dispatcher()
        engine = ForgeEngine(
            text_dispatcher=dispatcher,
            dispatcher_registry={"text": dispatcher},
        )
        state = ExecutionState("stream-handoff-run", {
            "userId": "user-1",
            "tenantId": "tenant-1",
            "principalRoles": ["operator"],
        })
        plan = ExecutionPlan(
            reasoning="Analyze and render",
            steps=[ExecutionStep(
                step_id=1,
                modality="text",
                capability="data_analysis",
                task_instruction="Analyze revenue and create a chart",
            )],
        )
        try:
            events = [
                event async for event in engine._executeGraphStream(
                    plan,
                    state,
                    ExecutionBudget(engine.executionLimits),
                )
            ]
            return events, state
        finally:
            await engine.close()

    events, state = asyncio.run(run())
    text = "".join(
        event["data"]["content"]
        for event in events
        if event["type"] == "textChunk"
    )
    assert "Revenue increased by 20%." in text
    assert "Rendered chart: outputs/chart.png" in text
    assert state.getAgentMessages(kind="handoff")[0]["metadata"]["status"] == "completed"
