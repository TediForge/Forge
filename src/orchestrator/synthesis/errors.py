"""Centralized deterministic policy for full and partial execution failures."""

from typing import Any

from orchestrator.security.audit import redact
from orchestrator.schemas.v1.responses import TerminalStatus


def apply_failure_policy(
	content: str,
	status: str,
	failures: list[Any] | None = None,
	allow_partial: bool = True,
) -> tuple[str, str, dict[str, Any]]:
	"""Keep useful partial content, but never expose raw exception details."""
	failures = failures or []
	if not failures:
		return content, status, {}

	public_failures = []
	for failure in failures:
		if isinstance(failure, dict):
			public_failures.append({
				"code": failure.get("code") if isinstance(failure.get("code"), str) else None,
				"message": "An execution step failed.",
			})
		else:
			public_failures.append({"code": None, "message": "An execution step failed."})
	metadata = {"partialFailures": redact(public_failures)}
	if content.strip() and allow_partial:
		return content, TerminalStatus.SUMMARIZED.value, metadata
	return "The request could not be completed because an execution step failed.", TerminalStatus.FAILED.value, metadata