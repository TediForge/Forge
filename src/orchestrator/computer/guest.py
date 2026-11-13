"""Small guest-side vsock agent; install and run it inside the immutable guest image."""

import asyncio
import base64
import binascii
import json
import os
from pathlib import Path
import shutil
import signal
import socket


WORKSPACE = Path("/workspace")
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 30
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
active_processes: set[asyncio.subprocess.Process] = set()


def _workspace_path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("A workspace-relative path is required")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or any(part in {".", ".."} for part in normalized.split("/")):
        raise ValueError("File paths must stay inside /workspace")
    root = WORKSPACE.resolve()
    target = (root / normalized).resolve(strict=False)
    if not target.is_relative_to(root):
        raise ValueError("File paths must stay inside /workspace")
    return target


async def _capture_output(
    stream: asyncio.StreamReader,
    process: asyncio.subprocess.Process,
    limit: int,
) -> tuple[bytes, bool]:
    output = bytearray()
    truncated = False
    while chunk := await stream.read(16 * 1024):
        remaining = limit - len(output)
        if remaining > 0:
            output.extend(chunk[:remaining])
        if len(chunk) > remaining and not truncated:
            truncated = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return bytes(output), truncated


async def _execute(command: object, timeout: object, output_limit: object) -> dict:
    if not isinstance(command, str) or not command.strip() or len(command) > 16_000 or "\x00" in command:
        raise ValueError("A valid command is required")
    timeout_seconds = min(MAX_TIMEOUT_SECONDS, max(1, int(timeout)))
    max_output_bytes = min(MAX_OUTPUT_BYTES, max(1, int(output_limit)))
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        "/bin/bash",
        "-c",
        command,
        cwd=WORKSPACE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    active_processes.add(process)
    output_task = asyncio.create_task(_capture_output(process.stdout, process, max_output_bytes))
    timed_out = False
    try:
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        output, truncated = await output_task
    finally:
        active_processes.discard(process)
    return {
        "exit_code": process.returncode,
        "output": output.decode("utf-8", errors="replace"),
        "timed_out": timed_out,
        "truncated": truncated,
    }


async def _read_file(path: object, limit: object) -> dict:
    target = _workspace_path(path)
    max_bytes = min(MAX_FILE_BYTES, max(1, int(limit)))
    if not target.is_file() or target.stat().st_size > max_bytes:
        raise ValueError("File is missing or exceeds the configured size limit")
    content = target.read_bytes()
    if len(content) > max_bytes:
        raise ValueError("File exceeds the configured size limit")
    return {"content": base64.b64encode(content).decode("ascii")}


async def _write_file(path: object, content: object) -> dict:
    target = _workspace_path(path)
    if not isinstance(content, str):
        raise ValueError("File content must be base64 text")
    try:
        data = base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("File content must be valid base64") from exc
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File exceeds the configured size limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"bytes_written": len(data)}


async def _reset() -> dict:
    for process in tuple(active_processes):
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for child in WORKSPACE.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            await asyncio.to_thread(shutil.rmtree, child)
    return {}


async def _dispatch(request: dict) -> dict:
    operation = request.get("operation")
    if operation == "ping":
        return {}
    if operation == "execute":
        return await _execute(
            request.get("command"),
            request.get("timeout_seconds", MAX_TIMEOUT_SECONDS),
            request.get("max_output_bytes", MAX_OUTPUT_BYTES),
        )
    if operation == "read_file":
        return await _read_file(request.get("path"), request.get("max_file_bytes", MAX_FILE_BYTES))
    if operation == "write_file":
        return await _write_file(request.get("path"), request.get("content"))
    if operation == "reset":
        return await _reset()
    raise ValueError("Unsupported computer operation")


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=5)
        if not line or len(line) > MAX_REQUEST_BYTES:
            return
        request = json.loads(line)
        if not isinstance(request, dict) or not isinstance(request.get("id"), str):
            return
        try:
            result = await _dispatch(request)
            response = {"id": request["id"], "success": True, **result}
        except (OSError, TypeError, ValueError, asyncio.TimeoutError) as exc:
            response = {"id": request["id"], "success": False, "error": str(exc)[:300]}
        writer.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
        await writer.drain()
    except (OSError, json.JSONDecodeError, asyncio.TimeoutError):
        return
    finally:
        writer.close()
        await writer.wait_closed()


async def serve(port: int = 1024) -> None:
    if not hasattr(socket, "AF_VSOCK"):
        raise RuntimeError("The guest kernel does not provide AF_VSOCK")
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    server_socket = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    server_socket.bind((socket.VMADDR_CID_ANY, port))
    server_socket.listen(128)
    server_socket.setblocking(False)
    server = await asyncio.start_server(_handle, sock=server_socket, limit=MAX_REQUEST_BYTES)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve())
