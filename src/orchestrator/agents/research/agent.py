"""Research specialist for web and evidence-based tasks."""

from orchestrator.agents.base import BaseAgent


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