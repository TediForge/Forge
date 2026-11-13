import asyncio
from pathlib import Path
import sys

import pytest

from orchestrator.computer.config import DEFAULT_COMPUTER_CONFIG
from orchestrator.computer.manager import ComputerManager


def _runtime_available() -> bool:
    return (
        sys.platform == "linux"
        and Path("/dev/kvm").exists()
        and DEFAULT_COMPUTER_CONFIG.firecracker_path.is_file()
        and DEFAULT_COMPUTER_CONFIG.kernel_path.is_file()
        and DEFAULT_COMPUTER_CONFIG.rootfs_path.is_file()
    )


@pytest.mark.skipif(not _runtime_available(), reason="Firecracker, KVM, or prepared guest image unavailable")
def test_concurrent_microvm_commands_and_workspace_files():
    async def run():
        manager = ComputerManager()
        try:
            instances = await asyncio.gather(*(manager.acquire() for _ in range(3)))
            outputs = await asyncio.gather(*(instance.execute("printf hello") for instance in instances))
            assert outputs == ["hello", "hello", "hello"]
            await asyncio.gather(*(
                instance.write_file("outputs/isolation.txt", f"vm-{index}".encode())
                for index, instance in enumerate(instances)
            ))
            contents = await asyncio.gather(*(
                instance.read_file("outputs/isolation.txt")
                for index, instance in enumerate(instances)
            ))
            assert contents == [b"vm-0", b"vm-1", b"vm-2"]
        finally:
            await manager.close()

    asyncio.run(run())
