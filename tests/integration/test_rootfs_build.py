import os
from pathlib import Path
import shutil
import sys

import pytest

from orchestrator.computer.images.builder import build_rootfs


_REQUIRED_COMMANDS = ("docker", "truncate", "mkfs.ext4", "mount", "tar", "umount")
_CAN_BUILD_ROOTFS = (
    sys.platform.startswith("linux")
    and hasattr(os, "geteuid")
    and os.geteuid() == 0
    and all(shutil.which(command) for command in _REQUIRED_COMMANDS)
)


@pytest.mark.skipif(
    not _CAN_BUILD_ROOTFS or os.environ.get("FORGE_RUN_ROOTFS_BUILD_TESTS") != "1",
    reason="Opt-in test requires Linux root, Docker, ext4 tools, and FORGE_RUN_ROOTFS_BUILD_TESTS=1",
)
def test_builds_ext4_rootfs_over_500mb(tmp_path: Path) -> None:
    output = build_rootfs("python-only", tmp_path / "computer.ext4")

    assert output.is_file()
    assert output.stat().st_size > 500 * 1024 * 1024
    with output.open("rb") as image:
        image.seek(1024 + 56)
        assert image.read(2) == b"\x53\xef"
