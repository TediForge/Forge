"""Production document and vision specialist."""

from orchestrator.agents.base import BaseAgent
from orchestrator.context.state import ExecutionState


class DocumentAgent(BaseAgent):
    name = "document"
    skillName = "document"
    capabilities = frozenset({"document", "document_analysis", "pdf", "invoice", "table", "summarize_document", "parse_document", "structured_rag"})

    async def execute(self, instruction: str, state: ExecutionState, task_id: int | None = None) -> str:
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.task", instruction)
        result = await self._dispatch(instruction, state, task_id)
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.status", "completed")
        self.handoff(state, "research", task_id or 0, "Verify document claims that require external evidence.", {
            "document_findings": result,
        })
        return result