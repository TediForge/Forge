"""Thread-safe in-process metrics for completed orchestration runs."""

import threading
from collections import Counter


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: Counter[str] = Counter()
        self._duration_seconds = 0.0
        self._tool_calls = 0
        self._estimated_tokens = 0

    def record_run(
        self,
        status: str,
        duration_seconds: float,
        tool_calls: int,
        estimated_tokens: int,
    ) -> None:
        with self._lock:
            self._runs[status] += 1
            self._duration_seconds += max(0.0, duration_seconds)
            self._tool_calls += max(0, tool_calls)
            self._estimated_tokens += max(0, estimated_tokens)

    def render(self) -> str:
        with self._lock:
            runs = dict(self._runs)
            duration = self._duration_seconds
            tool_calls = self._tool_calls
            tokens = self._estimated_tokens
        lines = [
            "# HELP forge_runs_total Orchestrator terminal run count by status.",
            "# TYPE forge_runs_total counter",
        ]
        lines.extend(
            f'forge_runs_total{{status="{status}"}} {count}'
            for status, count in sorted(runs.items())
        )
        lines.extend((
            "# HELP forge_run_duration_seconds_total Total run duration in seconds.",
            "# TYPE forge_run_duration_seconds_total counter",
            f"forge_run_duration_seconds_total {duration:.6f}",
            "# HELP forge_tool_calls_total Total tool calls across runs.",
            "# TYPE forge_tool_calls_total counter",
            f"forge_tool_calls_total {tool_calls}",
            "# HELP forge_estimated_tokens_total Estimated tokens across runs.",
            "# TYPE forge_estimated_tokens_total counter",
            f"forge_estimated_tokens_total {tokens}",
        ))
        return "\n".join(lines) + "\n"
