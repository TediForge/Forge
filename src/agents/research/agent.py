"""Research specialist definitions for Forge."""

from typing import Any, Sequence

from agents import Agent

from src.agents.base import BaseAgent
from src.ochestrator.runner import build_agent


class ResearchAgent(BaseAgent):
    name = "research"
    skillName = "research"
    capabilities = frozenset({"research", "search", "analysis", "fact_checking", "web_research", "source_synthesis"})

    async def execute(self, instruction: str, state, task_id: int | None = None) -> str:
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.task", instruction)
        result = await self._dispatch(instruction, state, task_id)
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.status", "completed")
        self.send_message(state, "coordinator", "context_share", result, task_id, {
            "domain": "research", "corroboration_needed": True,
        })
        return result


def build_research_agent(
    *,
    tools: Sequence[Any] = (),
    handoffs: Sequence[Agent[Any]] = (),
    model: Any = None,
) -> Agent[Any]:
    return build_agent(
        name="research",
        instructions=ResearchAgent().system_prompt,
        tools=tools,
        handoffs=handoffs,
        model=model,
    )