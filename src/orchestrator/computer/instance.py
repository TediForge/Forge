"""A single isolated computer lease."""

import base64
import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from orchestrator.computer.config import ComputerConfig
from orchestrator.computer.errors import ComputerError
from orchestrator.computer.policy import PolicyEngine
from orchestrator.computer.protocol import VsockClient, decode_file_response


class ComputerInstance:
    def __init__(
        self,
        vsock_path: str,
        config: ComputerConfig,
        destroy_callback: Callable[[], Awaitable[None]],
        policy: PolicyEngine | None = None,
    ) -> None:
        self.instance_id = uuid.uuid4().hex
        self._config = config
        self._client = VsockClient(
            vsock_path,
            config.guest_agent_port,
            max(config.max_file_bytes * 2, config.max_output_bytes * 2, 64 * 1024),
        )
        self._destroy_callback = destroy_callback
        self._policy = policy or PolicyEngine()
        self._destroyed = False
        self._destroy_lock = asyncio.Lock()

    async def wait_ready(self, timeout: float = 30) -> None:
        await self._client.wait_ready(timeout)

    async def execute(self, command: str) -> str:
        result = await self.execute_result(command)
        if result["timed_out"]:
            raise ComputerError("Computer command timed out")
        if result["truncated"]:
            raise ComputerError("Computer command output exceeded the configured limit")
        return result["output"]

    async def execute_result(self, command: str) -> dict[str, Any]:
        self._ensure_live()
        self._policy.validate_command(command)
        response = await self._client.request(
            "execute",
            command=command,
            timeout_seconds=self._config.command_timeout_seconds,
            max_output_bytes=self._config.max_output_bytes,
        )
        output = response.get("output")
        exit_code = response.get("exit_code")
        timed_out = response.get("timed_out")
        truncated = response.get("truncated")
        if (
            not isinstance(output, str)
            or not isinstance(exit_code, int)
            or not isinstance(timed_out, bool)
            or not isinstance(truncated, bool)
        ):
            raise ComputerError("Computer guest agent returned invalid command output")
        return {
            "output": output,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "truncated": truncated,
        }

    async def read_file(self, path: str) -> bytes:
        self._ensure_live()
        workspace_path = self._policy.validate_path(path)
        response = await self._client.request(
            "read_file",
            path=workspace_path,
            max_file_bytes=self._config.max_file_bytes,
        )
        return decode_file_response(response, self._config.max_file_bytes)

    async def write_file(self, path: str, content: bytes) -> None:
        self._ensure_live()
        workspace_path = self._policy.validate_path(path)
        if not isinstance(content, bytes):
            raise ComputerError("Computer file content must be bytes")
        if len(content) > self._config.max_file_bytes:
            raise ComputerError("File exceeds the configured computer file-size limit")
        await self._client.request(
            "write_file",
            path=workspace_path,
            content=base64.b64encode(content).decode("ascii"),
        )

    async def reset(self) -> None:
        self._ensure_live()
        await self._client.request("reset")

    async def destroy(self) -> None:
        async with self._destroy_lock:
            if self._destroyed:
                return
            await self._destroy_callback()
            self._destroyed = True

    def _ensure_live(self) -> None:
        if self._destroyed:
            raise ComputerError("Computer instance has been destroyed")
