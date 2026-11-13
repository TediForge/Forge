"""Firecracker microVM lifecycle driver."""

import asyncio
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any
import uuid

import httpx

from orchestrator.computer.config import ComputerConfig, DEFAULT_COMPUTER_CONFIG
from orchestrator.computer.errors import ComputerUnavailableError
from orchestrator.computer.instance import ComputerInstance


class FirecrackerDriver:
    def __init__(self, config: ComputerConfig = DEFAULT_COMPUTER_CONFIG) -> None:
        self.config = config

    async def boot(self) -> ComputerInstance:
        self._validate_host()
        runtime_dir = Path(tempfile.mkdtemp(prefix="forge-computer-"))
        api_socket = runtime_dir / "api.sock"
        vsock_socket = runtime_dir / "vsock.sock"
        vm_id = uuid.uuid4().hex
        process: asyncio.subprocess.Process | None = None
        client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=str(api_socket)),
            base_url="http://firecracker",
            timeout=10,
        )

        async def destroy() -> None:
            await client.aclose()
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            shutil.rmtree(runtime_dir, ignore_errors=False)

        try:
            process = await asyncio.create_subprocess_exec(
                str(self.config.firecracker_path),
                "--api-sock",
                str(api_socket),
                "--id",
                vm_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await self._wait_for_api(api_socket, process)
            await self._put(client, "/machine-config", {
                "vcpu_count": self.config.vcpu_count,
                "mem_size_mib": self.config.memory_mb,
                "smt": False,
            })
            await self._put(client, "/boot-source", {
                "kernel_image_path": str(self.config.kernel_path),
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda ro",
            })
            await self._put(client, "/drives/rootfs", {
                "drive_id": "rootfs",
                "path_on_host": str(self.config.rootfs_path),
                "is_root_device": True,
                "is_read_only": True,
            })
            await self._put(client, "/vsock", {
                "guest_cid": 3,
                "uds_path": str(vsock_socket),
            })
            await self._put(client, "/actions", {"action_type": "InstanceStart"})
            instance = ComputerInstance(
                str(vsock_socket),
                self.config,
                destroy,
            )
            await instance.wait_ready()
            return instance
        except (OSError, httpx.HTTPError, asyncio.TimeoutError, ComputerUnavailableError) as exc:
            await destroy()
            if isinstance(exc, ComputerUnavailableError):
                raise
            raise ComputerUnavailableError("Firecracker could not boot a computer instance") from exc

    def _validate_host(self) -> None:
        if sys.platform != "linux":
            raise ComputerUnavailableError("Firecracker computer execution requires a Linux host")
        if not Path("/dev/kvm").exists():
            raise ComputerUnavailableError("Firecracker computer execution requires /dev/kvm")
        for path, label in (
            (self.config.firecracker_path, "Firecracker binary"),
            (self.config.kernel_path, "computer kernel"),
            (self.config.rootfs_path, "computer root filesystem"),
        ):
            if not path.is_file():
                raise ComputerUnavailableError(f"Configured {label} is unavailable: {path}")
        if not shutil.which(str(self.config.firecracker_path)):
            raise ComputerUnavailableError("Firecracker binary is not executable")

    async def _wait_for_api(
        self,
        api_socket: Path,
        process: asyncio.subprocess.Process,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + 10
        while not api_socket.exists():
            if process.returncode is not None:
                raise ComputerUnavailableError("Firecracker exited before opening its API socket")
            if asyncio.get_running_loop().time() >= deadline:
                raise ComputerUnavailableError("Firecracker API socket did not become ready")
            await asyncio.sleep(0.05)

    async def _put(self, client: httpx.AsyncClient, endpoint: str, body: dict[str, Any]) -> None:
        response = await client.put(endpoint, json=body)
        if response.is_error:
            raise ComputerUnavailableError(
                f"Firecracker rejected computer configuration ({response.status_code})"
            )
