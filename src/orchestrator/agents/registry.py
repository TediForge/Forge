"""Agent discovery and collaborative task routing."""

from typing import Any

from orchestrator.agents.base import BaseAgent
from orchestrator.context.state import ExecutionState


class AgentRegistry:
    def __init__(self, agents: list[BaseAgent] | None = None) -> None:
        self._agents: dict[str, BaseAgent] = {}
        for agent in agents or []:
            self.register(agent)

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name.lower()] = agent

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name.lower())

    def names(self) -> list[str]:
        return sorted(self._agents)

    def resolve(self, capability: str, modality: str | None = None) -> BaseAgent | None:
        capability = capability.lower().replace("_", "")
        modality = modality.lower() if modality else None
        scored: list[tuple[int, BaseAgent]] = []
        for agent in self._agents.values():
            capabilities = {item.lower().replace("_", "") for item in agent.capabilities}
            score = 100 if capability in capabilities else 0
            if modality:
                score += 20 if modality in capabilities else 0
            if score:
                scored.append((score, agent))
        return max(scored, key=lambda item: item[0])[1] if scored else None

    async def collaborate(
        self,
        agent: BaseAgent,
        instruction: str,
        state: ExecutionState,
        task_id: int | None = None,
    ) -> str:
        result = await agent.execute(instruction, state, task_id)
        agent.send_message(
            state=state,
            recipient="coordinator",
            kind="result",
            content=result,
            task_id=task_id,
        )
        return result
