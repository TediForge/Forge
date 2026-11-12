"""Production data analysis, reporting, and SQL specialist."""

from src.agents.base import BaseAgent
from src.context.state import ExecutionState


class DataAgent(BaseAgent):
    name = "data"
    skillName = "data"
    capabilities = frozenset({
        "data", "data_analysis", "analytics", "statistics", "pandas",
        "sql", "database", "datawarehouse", "reporting", "visualization",
        "spreadsheet", "dataset_profiling", "business_intelligence",
    })
    async def execute(self, instruction: str, state: ExecutionState, task_id: int | None = None) -> str:
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.task", instruction)
        result = await self._dispatch(instruction, state, task_id)
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.status", "completed")
        self.send_message(state, "coding", "analysis_review_request", result, task_id, {
            "domain": "data", "requires_reproducibility_check": True,
        })
        return result