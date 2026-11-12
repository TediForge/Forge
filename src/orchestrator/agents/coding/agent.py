"""Coding specialist for code-related tasks."""

from orchestrator.agents.base import BaseAgent


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