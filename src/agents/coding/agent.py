"""Coding specialist definitions for Forge."""

from typing import Any, Sequence

from agents import Agent

from src.agents.base import BaseAgent
from src.ochestrator.runner import build_agent


class CodingAgent(BaseAgent):
    name = "coding"
    skillName = "coding"
    capabilities = frozenset({"coding", "code", "review_code", "debugging", "testing", "implementation"})

    async def execute(self, instruction: str, state, task_id: int | None = None) -> str:
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.task", instruction)
        result = await self._dispatch(instruction, state, task_id)
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.status", "completed")
        self.send_message(state, "review", "review_request", result, task_id, {
            "domain": "code", "requires_validation": True,
        })
        return result


def build_coding_agent(
    *,
    tools: Sequence[Any] = (),
    handoffs: Sequence[Agent[Any]] = (),
    model: Any = None,
) -> Agent[Any]:
    return build_agent(
        name="coding",
        instructions=CodingAgent().system_prompt,
        tools=tools,
        handoffs=handoffs,
        model=model,
    )