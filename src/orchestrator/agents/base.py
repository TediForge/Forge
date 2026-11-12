"""Production contracts and communication primitives for Forge agents."""

import asyncio
import inspect
from collections.abc import AsyncIterator
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from opentelemetry import trace

from orchestrator.context.state import ExecutionState
from orchestrator.skills.loader import loadAgentSkill


tracer = trace.get_tracer("orchestrator.agents")


@dataclass
class AgentMessage:
    sender: str
    recipient: str
    kind: str
    content: str
    task_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentExecutionError(RuntimeError):
    pass


class BaseAgent(ABC):
    name: str
    skillName: str = ""
    capabilities: frozenset[str]

    def __init__(self, dispatcher: Any = None, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.dispatcher = dispatcher
        self.max_attempts = max_attempts
        self._systemPrompt: str | None = None

    @property
    def system_prompt(self) -> str:
        if self._systemPrompt is None:
            if not self.skillName:
                raise ValueError(f"{type(self).__name__} does not declare a skillName")
            self._systemPrompt = loadAgentSkill(self.skillName)
        return self._systemPrompt

    def reloadSkill(self) -> None:
        self._systemPrompt = None

    def can_handle(self, capability: str) -> bool:
        return capability.lower() in {item.lower() for item in self.capabilities}

    def send_message(self, state: ExecutionState, recipient: str, kind: str,
                     content: str, task_id: int | None = None,
                     metadata: dict[str, Any] | None = None) -> AgentMessage:
        message = AgentMessage(self.name, recipient, kind, content, task_id, metadata or {})
        state.recordAgentMessage(message)
        return message

    def handoff(self, state: ExecutionState, recipient: str, task_id: int,
                instruction: str, context: dict[str, Any] | None = None) -> AgentMessage:
        correlation_id = uuid4().hex
        return self.send_message(
            state, recipient, "handoff", instruction, task_id,
            {"context": context or {}, "accepted": False, "correlation_id": correlation_id},
        )

    def build_prompt(self, instruction: str, state: ExecutionState, task_id: int | None = None) -> str:
        scratchpad = state.getVariable("scratchpad", {})
        shared_context = "\n".join(
            f"{key}: {value}" for key, value in scratchpad.items()
            if key.endswith(".result") and value
        )
        return "\n\n".join(filter(None, (
            self.system_prompt,
            shared_context and "COLLABORATIVE CONTEXT:\n" + shared_context,
            f"TASK:\n{instruction}",
        )))

    async def invoke_dispatcher(self, prompt: str) -> str:
        if self.dispatcher is None:
            raise AgentExecutionError(f"{self.name} agent has no model dispatcher configured")

        invoker: Callable[..., Any] | None = None
        for method_name in ("generate_text", "generate", "invoke"):
            candidate = getattr(self.dispatcher, method_name, None)
            if callable(candidate):
                invoker = candidate
                break
        if invoker is None and callable(self.dispatcher):
            invoker = self.dispatcher
        if invoker is None:
            raise AgentExecutionError(f"{self.name} dispatcher has no supported execution method")

        try:
            if inspect.signature(invoker).parameters:
                result = invoker(prompt=prompt, system_prompt=self.system_prompt)
            else:
                result = invoker()
        except TypeError:
            result = invoker(prompt)
        return await self._normalize_result(result)

    async def _normalize_result(self, result: Any) -> str:
        if isinstance(result, Awaitable):
            result = await result
        if result is None:
            raise AgentExecutionError(f"{self.name} dispatcher returned no result")
        if hasattr(result, "text"):
            result = result.text
        if isinstance(result, (bytes, bytearray)):
            result = result.decode("utf-8", errors="replace")
        if isinstance(result, dict):
            for key in ("text", "content", "output", "result"):
                if isinstance(result.get(key), str):
                    return result[key].strip()
            raise AgentExecutionError(f"{self.name} dispatcher returned unsupported object data")
        output = str(result).strip()
        if not output:
            raise AgentExecutionError(f"{self.name} dispatcher returned an empty result")
        return output

    async def _dispatch(self, instruction: str, state: ExecutionState, task_id: int | None = None) -> str:
        prompt = self.build_prompt(instruction, state, task_id)
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with tracer.start_as_current_span("orchestrator.agent") as span:
                    span.set_attribute("agent.name", self.name)
                    result = await self.invoke_dispatcher(prompt)
                state.setScratchpad(f"{self.name}.{task_id or 'direct'}.result", result)
                return result
            except Exception as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    await asyncio.sleep(0.05 * attempt)
        raise AgentExecutionError(f"{self.name} agent failed after {self.max_attempts} attempts: {last_error}")

    async def stream(
        self,
        instruction: str,
        state: ExecutionState,
        task_id: int | None = None,
    ) -> AsyncIterator[str]:
        if self.dispatcher is None:
            raise AgentExecutionError(f"{self.name} agent has no model dispatcher configured")
        streamer = getattr(self.dispatcher, "stream", None)
        if not callable(streamer):
            raise AgentExecutionError(f"{self.name} dispatcher does not support streaming")
        prompt = self.build_prompt(instruction, state, task_id)
        try:
            chunks = streamer(prompt=prompt, system_prompt=self.system_prompt)
        except TypeError:
            chunks = streamer(prompt)
        if inspect.isawaitable(chunks):
            chunks = await chunks
        if not hasattr(chunks, "__aiter__"):
            raise AgentExecutionError(f"{self.name} dispatcher returned an invalid stream")
        parts: list[str] = []
        with tracer.start_as_current_span("orchestrator.agent") as span:
            span.set_attribute("agent.name", self.name)
            async for chunk in chunks:
                if not isinstance(chunk, str):
                    raise AgentExecutionError(f"{self.name} dispatcher returned a non-text stream chunk")
                if chunk:
                    parts.append(chunk)
                    yield chunk
        result = "".join(parts).strip()
        if not result:
            raise AgentExecutionError(f"{self.name} dispatcher returned an empty stream")
        state.setScratchpad(f"{self.name}.{task_id or 'direct'}.result", result)
        self.send_message(state, "coordinator", "result", result, task_id)

    @abstractmethod
    async def execute(self, instruction: str, state: ExecutionState, task_id: int | None = None) -> str:
        raise NotImplementedError
