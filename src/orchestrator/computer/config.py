"""Code-owned defaults for the Firecracker computer runtime."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ComputerConfig:
    firecracker_path: Path = Path("/usr/local/bin/firecracker")
    kernel_path: Path = Path("/var/lib/firecracker/vmlinux.bin")
    rootfs_path: Path = Path("/var/lib/firecracker/rootfs.ext4")
    min_warm: int = 5
    max_pool_size: int = 200
    pool_size: int | None = None
    max_instances: int | None = None
    scale_threshold: float = 0.2
    acquire_timeout_seconds: float = 30
    vcpu_count: int = 2
    memory_mb: int = 1024
    command_timeout_seconds: int = 30
    max_output_bytes: int = 1024 * 1024
    max_file_bytes: int = 1024 * 1024
    guest_agent_port: int = 1024

    def __post_init__(self) -> None:
        if self.warm_pool_size < 0 or self.instance_limit < 1:
            raise ValueError("Computer pool sizes must be non-negative and max_pool_size positive")
        if self.warm_pool_size > self.instance_limit:
            raise ValueError("min_warm cannot exceed max_pool_size")
        if not 0 < self.scale_threshold <= 1:
            raise ValueError("scale_threshold must be greater than 0 and at most 1")
        if self.acquire_timeout_seconds <= 0:
            raise ValueError("acquire_timeout_seconds must be positive")
        if self.vcpu_count < 1 or self.memory_mb < 128:
            raise ValueError("Computer vCPU and memory limits are invalid")
        if not 1 <= self.command_timeout_seconds <= 30:
            raise ValueError("command_timeout_seconds must be between 1 and 30")
        if not 1 <= self.max_output_bytes <= 1024 * 1024:
            raise ValueError("max_output_bytes must be between 1 byte and 1 MiB")
        if not 1 <= self.max_file_bytes <= 1024 * 1024:
            raise ValueError("max_file_bytes must be between 1 byte and 1 MiB")
        if not 1024 <= self.guest_agent_port <= 65535:
            raise ValueError("guest_agent_port must be between 1024 and 65535")

    @property
    def warm_pool_size(self) -> int:
        return self.pool_size if self.pool_size is not None else self.min_warm

    @property
    def instance_limit(self) -> int:
        return self.max_instances if self.max_instances is not None else self.max_pool_size


DEFAULT_COMPUTER_CONFIG = ComputerConfig()
