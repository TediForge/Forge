"""Hard execution budgets and loop-prevention controls."""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any
import json


class ExecutionLimitError(RuntimeError):
    def __init__(self, reason: str, metrics: dict[str, Any]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.metrics = metrics


@dataclass
class ExecutionLimits:
    max_steps: int = 10
    max_tool_calls: int = 20
    max_iterations: int = 12
    max_runtime_seconds: float = 300.0
    max_estimated_tokens: int = 100_000


@dataclass
class ExecutionBudget:
    limits: ExecutionLimits = field(default_factory=ExecutionLimits)
    started_at: float = field(default_factory=time.monotonic)
    steps: int = 0
    iterations: int = 0
    tool_calls: int = 0
    estimated_tokens: int = 0
    action_fingerprints: list[str] = field(default_factory=list)
    tool_fingerprint_counts: dict[str, int] = field(default_factory=dict)
    output_history: list[Any] = field(default_factory=list)
    termination_reason: str | None = None
    terminal_status: str = "completed"

    def fingerprint(self, modality: str, capability: str, instruction: str, arguments: Any = None) -> str:
        material = f"{modality}|{capability}|{instruction}|{arguments}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def begin_action(self, fingerprint: str, output_hint: str = "") -> None:
        elapsed = time.monotonic() - self.started_at
        if elapsed >= self.limits.max_runtime_seconds:
            self._stop("Execution timeout exceeded", elapsed=elapsed)
        if self.iterations >= self.limits.max_iterations:
            self._stop("Maximum iteration budget exceeded", elapsed=elapsed)
        if self.steps >= self.limits.max_steps:
            self._stop("Maximum step budget exceeded", elapsed=elapsed)
        if fingerprint in self.action_fingerprints[-3:]:
            self._stop("Repeated action circuit breaker triggered", elapsed=elapsed, terminal_status="stopped_circuit_breaker")
        self.action_fingerprints.append(fingerprint)
        self.iterations += 1
        self.steps += 1
        self.estimated_tokens += max(1, len(output_hint.split()) + len(output_hint) // 8)
        if self.estimated_tokens >= self.limits.max_estimated_tokens:
            self._stop("Estimated token budget exceeded", elapsed=elapsed)

    def record_tool_call(self, name: str, arguments: Any) -> None:
        encoded = json.dumps(arguments, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
        fingerprint = hashlib.sha256(f"tool:{name}:{encoded}".encode("utf-8")).hexdigest()
        if self.tool_calls >= self.limits.max_tool_calls:
            self._stop("Maximum tool-call budget exceeded", terminal_status="failed")
        repeats = self.tool_fingerprint_counts.get(fingerprint, 0)
        if repeats >= 3:
            self._stop("Duplicate tool-call circuit breaker triggered", terminal_status="stopped_circuit_breaker")
        self.tool_fingerprint_counts[fingerprint] = repeats + 1
        self.tool_calls += 1

    def record_output(self, output: Any) -> None:
        self.output_history.append(output)
        text = str(output)
        self.estimated_tokens += max(1, len(text.split()) + len(text) // 8)
        if self.estimated_tokens >= self.limits.max_estimated_tokens:
            self._stop("Estimated token budget exceeded")

    def _stop(self, reason: str, elapsed: float | None = None, terminal_status: str = "stopped_budget") -> None:
        self.termination_reason = reason
        self.terminal_status = terminal_status
        raise ExecutionLimitError(reason, self.metrics())

    def metrics(self) -> dict[str, Any]:
        return {
            "steps": self.steps,
            "iterations": self.iterations,
            "toolCalls": self.tool_calls,
            "estimatedTokens": self.estimated_tokens,
            "elapsedSeconds": round(time.monotonic() - self.started_at, 3),
            "terminalStatus": self.terminal_status,
            "terminationReason": self.termination_reason,
        }
