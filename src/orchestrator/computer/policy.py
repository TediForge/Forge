"""Input checks for the isolated computer interface."""

import re

from orchestrator.computer.errors import ComputerPolicyError


_BLOCKED_COMMAND_PATTERNS = (
    re.compile(r"\brm\s+(?:-[^\s]*r[^\s]*f|-[^\s]*f[^\s]*r)\s+/(?:\s|$)", re.IGNORECASE),
    re.compile(r"\b(?:shutdown|reboot|poweroff|mount|umount)\b", re.IGNORECASE),
)
_MAX_COMMAND_LENGTH = 16_000


class PolicyEngine:
    """Reject obviously destructive commands before guest execution.

    The VM boundary, immutable root filesystem, absent network interface, and
    guest privilege separation provide isolation; these checks are additional
    guardrails, not a shell parser or a substitute for virtualization.
    """

    def validate_command(self, command: str) -> None:
        if not isinstance(command, str) or not command.strip():
            raise ComputerPolicyError("A non-empty command is required")
        if len(command) > _MAX_COMMAND_LENGTH or "\x00" in command:
            raise ComputerPolicyError("Command exceeds the supported size")
        if any(pattern.search(command) for pattern in _BLOCKED_COMMAND_PATTERNS):
            raise ComputerPolicyError("Command is blocked by computer policy")

    def validate_path(self, path: str) -> str:
        if not isinstance(path, str) or not path.strip() or "\x00" in path:
            raise ComputerPolicyError("A valid workspace-relative path is required")
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        if normalized.startswith("/") or any(part in {".", ".."} for part in parts):
            raise ComputerPolicyError("File paths must stay inside /workspace")
        return "/".join(part for part in parts if part)
