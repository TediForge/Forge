"""Agent discovery and collaborative task routing."""

import json
from typing import Any

from orchestrator.agents.base import AgentExecutionError, BaseAgent
from orchestrator.context.state import ExecutionState


class AgentRegistry:
    def __init__(self, agents: list[BaseAgent] | None = None, max_handoffs: int = 4) -> None:
        if max_handoffs < 0:
            raise ValueError("max_handoffs cannot be negative")
        self._agents: dict[str, BaseAgent] = {}
        self.max_handoffs = max_handoffs
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
        messages = state.getVariable("agentMessages", [])
        first_message_index = len(messages)
        result = await agent.execute(instruction, state, task_id)
        agent.send_message(
            state=state,
            recipient="coordinator",
            kind="result",
            content=result,
            task_id=task_id,
        )
        results = [result]
        results.extend(await self.execute_handoffs(agent, state, first_message_index, task_id))
        return "\n\n".join(results)

    async def execute_handoffs(
        self,
        agent: BaseAgent,
        state: ExecutionState,
        first_message_index: int,
        task_id: int | None = None,
    ) -> list[str]:
        visited = {agent.name.casefold()}
        processed: set[str] = set()
        handoff_count = 0
        results: list[str] = []

        while True:
            current_messages = state.getVariable("agentMessages", [])
            pending = next((
                message for message in current_messages[first_message_index:]
                if message.get("kind") == "handoff"
                and message.get("message_id") not in processed
                and not message.get("metadata", {}).get("accepted", False)
            ), None)
            if pending is None:
                break
            processed.add(pending["message_id"])
            handoff_count += 1
            if handoff_count > self.max_handoffs:
                raise AgentExecutionError(
                    f"Agent handoff limit of {self.max_handoffs} was exceeded"
                )

            raw_recipient = pending.get("recipient")
            if not isinstance(raw_recipient, str) or not raw_recipient.strip():
                raise AgentExecutionError(
                    f"Agent '{pending.get('sender')}' created a handoff without a recipient"
                )
            recipient_name = raw_recipient.casefold()
            recipient = self.get(recipient_name)
            if recipient is None:
                raise AgentExecutionError(
                    f"Agent '{pending.get('sender')}' handed off to unknown agent "
                    f"'{pending.get('recipient')}'"
                )
            if recipient_name in visited:
                raise AgentExecutionError(
                    f"Agent handoff cycle detected at '{pending.get('recipient')}'"
                )

            metadata = pending.setdefault("metadata", {})
            metadata["accepted"] = True
            metadata["status"] = "accepted"
            context = metadata.get("context", {})
            handoff_instruction = pending["content"]
            if context:
                handoff_instruction += "\n\nHandoff context:\n" + json.dumps(
                    context, ensure_ascii=False, default=str,
                )

            try:
                handoff_result = await recipient.execute(
                    handoff_instruction,
                    state,
                    pending.get("task_id", task_id),
                )
            except BaseException:
                metadata["status"] = "failed"
                raise

            visited.add(recipient_name)
            metadata["status"] = "completed"
            state.setScratchpad(
                f"{recipient.name}.{pending.get('task_id', task_id) or 'direct'}.result",
                handoff_result,
            )
            recipient.send_message(
                state=state,
                recipient=pending.get("sender", ""),
                kind="handoff_result",
                content=handoff_result,
                task_id=pending.get("task_id", task_id),
                metadata={
                    "correlation_id": metadata.get("correlation_id"),
                    "handoff_message_id": pending["message_id"],
                },
            )
            results.append(f"Handoff result from {recipient.name}:\n{handoff_result}")

        return results
