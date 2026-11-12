"""Production data analysis, reporting, and SQL specialist."""

from collections.abc import AsyncIterator

from orchestrator.agents.base import BaseAgent
from orchestrator.context.state import ExecutionState


class DataAgent(BaseAgent):
    name = "data"
    skillName = "data"
    capabilities = frozenset({
        "data", "data_analysis", "analytics", "statistics", "pandas",
        "sql", "database", "datawarehouse", "reporting", "visualization",
        "spreadsheet", "dataset_profiling", "business_intelligence",
    })

    def _handoff_visualization(
        self,
        instruction: str,
        result: str,
        state: ExecutionState,
        task_id: int | None,
    ) -> None:
        if any(
            term in instruction.casefold()
            for term in ("chart", "graph", "plot", "visualiz", "diagram")
        ):
            self.handoff(
                state,
                "media",
                task_id or 0,
                "Render a chart or visual from the data analysis. Return the rendered asset path and a concise description.",
                {"analysis": result, "request": instruction},
            )

    async def execute(self, instruction: str, state: ExecutionState, task_id: int | None = None) -> str:
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.task", instruction)
        result = await self._dispatch(instruction, state, task_id)
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.status", "completed")
        self._handoff_visualization(instruction, result, state, task_id)
        self.send_message(state, "coding", "analysis_review_request", result, task_id, {
            "domain": "data", "requires_reproducibility_check": True,
        })
        return result

    async def stream(
        self,
        instruction: str,
        state: ExecutionState,
        task_id: int | None = None,
    ) -> AsyncIterator[str]:
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.task", instruction)
        parts: list[str] = []
        async for part in super().stream(instruction, state, task_id):
            parts.append(part)
            yield part
        result = "".join(parts).strip()
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.status", "completed")
        self._handoff_visualization(instruction, result, state, task_id)
        self.send_message(state, "coding", "analysis_review_request", result, task_id, {
            "domain": "data", "requires_reproducibility_check": True,
        })