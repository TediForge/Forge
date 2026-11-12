"""Thin OpenAI Agents SDK entry point for Forge agent runs."""

from collections.abc import AsyncIterator, Sequence
from typing import Any

from agents import Agent, Runner

from src.ochestrator.events import forward_runner_events


def build_agent(
    *,
    name: str,
    instructions: str,
    tools: Sequence[Any] = (),
    handoffs: Sequence[Agent[Any]] = (),
    model: Any = None,
    output_type: Any = None,
    hooks: Any = None,
) -> Agent[Any]:
    agent_options: dict[str, Any] = {
        "name": name,
        "instructions": instructions,
        "tools": list(tools),
        "handoffs": list(handoffs),
    }
    if model is not None:
        agent_options["model"] = model
    if output_type is not None:
        agent_options["output_type"] = output_type
    if hooks is not None:
        agent_options["hooks"] = hooks
    return Agent(**agent_options)


class OrchestrationRunner:
    """Runs one configured SDK agent and exposes normalized text stream events."""

    def __init__(self, agent: Agent[Any]) -> None:
        self.agent = agent

    async def run(self, prompt: str, context: Any = None, run_config: Any = None) -> Any:
        return await Runner.run(
            self.agent,
            input=prompt,
            context=context,
            run_config=run_config,
        )

    async def run_streamed(
        self,
        prompt: str,
        context: Any = None,
        run_config: Any = None,
    ) -> AsyncIterator[dict[str, Any]]:
        result = Runner.run_streamed(
            self.agent,
            input=prompt,
            context=context,
            run_config=run_config,
        )
        async for event in forward_runner_events(result):
            yield event