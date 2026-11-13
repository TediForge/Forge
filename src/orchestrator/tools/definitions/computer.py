"""Tool for executing commands and managing files in isolated Firecracker guests."""

import asyncio
import base64
from typing import Any

from orchestrator.computer.errors import ComputerError, ComputerPolicyError, ComputerUnavailableError
from orchestrator.computer.manager import ComputerManager
from orchestrator.computer.policy import PolicyEngine


_policy = PolicyEngine()
_ACTIONS = {
    "execute": ("A8M4C7", "Running a command in an isolated computer"),
    "read_file": ("A3C1V6", "Reading a file from an isolated computer"),
    "write_file": ("A9P5D2", "Writing a file to an isolated computer"),
}


async def computer(
    operation: str,
    command: str | None = None,
    path: str | None = None,
    content: str | None = None,
    computerSessionId: str | None = None,
    computerTenantId: str | None = None,
    computerUserId: str | None = None,
    computerRunId: str | None = None,
    computerManager: ComputerManager | None = None,
) -> dict[str, Any]:
    if computerManager is None:
        return {
            "success": False,
            "error": "The Firecracker computer runtime is not configured",
            "errorCode": "COMPUTER_UNAVAILABLE",
        }
    try:
        if operation == "execute":
            _policy.validate_command(command or "")
        elif operation in {"read_file", "write_file"}:
            _policy.validate_path(path or "")
        else:
            return {"success": False, "error": "Unsupported computer operation", "errorCode": "INVALID_OPERATION"}
    except ComputerPolicyError as exc:
        return {"success": False, "error": str(exc), "errorCode": "POLICY_VIOLATION"}

    instance = None
    cancelled = False
    try:
        instance = await computerManager.acquire(
            computerSessionId,
            tenant_id=computerTenantId,
            user_id=computerUserId,
            run_id=computerRunId,
        )
        if operation == "execute":
            result = await instance.execute_result(command or "")
            if result["timed_out"]:
                return {
                    "success": False,
                    **result,
                    "error": "Computer command timed out",
                    "errorCode": "COMMAND_TIMEOUT",
                }
            if result["truncated"]:
                return {
                    "success": False,
                    **result,
                    "error": "Computer command output exceeded the configured limit",
                    "errorCode": "OUTPUT_LIMIT_EXCEEDED",
                }
            exit_code = result["exit_code"]
            return {
                "success": exit_code == 0,
                **result,
                "error": None if exit_code == 0 else f"Command exited with status {exit_code}",
                "errorCode": None if exit_code == 0 else "COMMAND_FAILED",
            }
        if operation == "read_file":
            data = await instance.read_file(path or "")
            try:
                decoded = data.decode("utf-8")
                encoding = "utf-8"
            except UnicodeDecodeError:
                decoded = base64.b64encode(data).decode("ascii")
                encoding = "base64"
            return {
                "success": True,
                "content": decoded,
                "encoding": encoding,
                "error": None,
                "errorCode": None,
            }
        await instance.write_file(path or "", (content or "").encode("utf-8"))
        return {"success": True, "path": path, "bytes_written": len((content or "").encode("utf-8")), "error": None, "errorCode": None}
    except ComputerUnavailableError as exc:
        return {"success": False, "error": str(exc), "errorCode": "COMPUTER_UNAVAILABLE"}
    except ComputerPolicyError as exc:
        return {"success": False, "error": str(exc), "errorCode": "POLICY_VIOLATION"}
    except ComputerError as exc:
        return {"success": False, "error": str(exc), "errorCode": "COMPUTER_ERROR"}
    except asyncio.CancelledError:
        cancelled = True
        raise
    finally:
        if instance is not None:
            if cancelled:
                await asyncio.shield(computerManager.release(
                    instance,
                    computerSessionId,
                    destroy_session=True,
                ))
            else:
                await asyncio.shield(computerManager.release(instance, computerSessionId))


TOOLS = [{
    "type": "function",
    "function": {
        "name": "computer",
        "description": "Run a command or manage a file inside an isolated Linux microVM. Select one operation.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["execute", "read_file", "write_file"]},
                "command": {"type": "string", "maxLength": 16000, "description": "Shell command executed inside the isolated guest."},
                "path": {"type": "string", "maxLength": 1024, "description": "Path relative to the guest /workspace directory."},
                "content": {"type": "string", "maxLength": 1048576, "description": "UTF-8 text to write into /workspace."},
            },
            "required": ["operation"],
            "allOf": [
                {"if": {"properties": {"operation": {"const": "execute"}}}, "then": {"required": ["command"]}},
                {"if": {"properties": {"operation": {"const": "read_file"}}}, "then": {"required": ["path"]}},
                {"if": {"properties": {"operation": {"const": "write_file"}}}, "then": {"required": ["path", "content"]}},
            ],
            "additionalProperties": False,
        },
    },
}]

HANDLERS = {"computer": computer}


def _action_factory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = arguments.get("operation")
    if operation not in _ACTIONS:
        raise ValueError(f"Unsupported computer operation: {operation}")
    action_id, message = _ACTIONS[operation]
    return {
        "actionId": action_id,
        "actionType": "tool",
        "toolName": tool_name,
        "message": message,
        "metadata": {},
    }


setattr(computer, "__forge_action_factory__", _action_factory)
