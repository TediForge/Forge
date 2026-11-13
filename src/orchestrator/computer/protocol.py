"""Host-side Firecracker vsock guest-agent client."""

import asyncio
import base64
import binascii
import json
import socket
from typing import Any
import uuid

from orchestrator.computer.errors import ComputerError, ComputerUnavailableError


class VsockClient:
    def __init__(self, socket_path: str, guest_port: int, max_message_bytes: int) -> None:
        self.socket_path = socket_path
        self.guest_port = guest_port
        self.max_message_bytes = max_message_bytes

    async def request(self, operation: str, **payload: Any) -> dict[str, Any]:
        sock = None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.setblocking(False)
            await asyncio.wait_for(
                asyncio.get_running_loop().sock_connect(sock, self.socket_path),
                timeout=5,
            )
            reader, writer = await asyncio.open_connection(sock=sock, limit=self.max_message_bytes + 1)
        except (OSError, asyncio.TimeoutError) as exc:
            if sock is not None:
                sock.close()
            raise ComputerUnavailableError("The computer guest agent is not reachable") from exc

        try:
            writer.write(f"CONNECT {self.guest_port}\n".encode("ascii"))
            await writer.drain()
            handshake = await asyncio.wait_for(reader.readline(), timeout=5)
            if not handshake.startswith(b"OK "):
                raise ComputerUnavailableError("Firecracker rejected the guest-agent connection")
            message = {"id": uuid.uuid4().hex, "operation": operation, **payload}
            encoded = json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"
            if len(encoded) > self.max_message_bytes:
                raise ComputerError("Computer request exceeds the supported size")
            writer.write(encoded)
            await writer.drain()
            response_line = await asyncio.wait_for(reader.readline(), timeout=35)
            if not response_line or len(response_line) > self.max_message_bytes:
                raise ComputerUnavailableError("The computer guest agent returned an invalid response")
            response = json.loads(response_line)
            if not isinstance(response, dict) or response.get("id") != message["id"]:
                raise ComputerUnavailableError("The computer guest agent response did not match the request")
            if not response.get("success"):
                raise ComputerError(str(response.get("error", "Computer operation failed")))
            return response
        except (OSError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
            raise ComputerUnavailableError("Communication with the computer guest agent failed") from exc
        finally:
            writer.close()
            await writer.wait_closed()

    async def wait_ready(self, timeout: float = 30) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                await self.request("ping")
                return
            except ComputerUnavailableError:
                if asyncio.get_running_loop().time() >= deadline:
                    raise ComputerUnavailableError("Computer guest agent did not become ready")
                await asyncio.sleep(0.2)


def decode_file_response(response: dict[str, Any], max_file_bytes: int) -> bytes:
    encoded = response.get("content")
    if not isinstance(encoded, str):
        raise ComputerUnavailableError("Computer guest agent returned invalid file data")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ComputerUnavailableError("Computer guest agent returned invalid file data") from exc
    if len(content) > max_file_bytes:
        raise ComputerError("File exceeds the configured computer file-size limit")
    return content
