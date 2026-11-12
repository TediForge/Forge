import os
import time

import pytest

from src.core.security.durability import CheckpointStore


def test_checkpoint_store_rejects_traversal_components(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoints")
    with pytest.raises(ValueError, match="tenant ID"):
        store.save("..", "run-1", "suspended", {})
    with pytest.raises(ValueError, match="run ID"):
        store.load("tenant-a", "..\\outside", "suspended")
    with pytest.raises(ValueError, match="name"):
        store.save("tenant-a", "run-1", "../outside", {})


def test_checkpoint_store_writes_and_loads_atomically_under_tenant_root(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoints")
    saved = store.save("tenant-a", "run-1", "suspended", {"status": "suspended"})
    assert saved.parent == tmp_path / "checkpoints" / "tenant-a"
    assert store.load("tenant-a", "run-1", "suspended") == {"status": "suspended"}
    assert not list(saved.parent.glob("*.tmp"))


def test_checkpoint_retention_expires_old_files(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoints", retention_days=1)
    saved = store.save("tenant-a", "run-expired", "suspended", {"status": "suspended"})
    old_time = time.time() - 2 * 86400
    os.utime(saved, (old_time, old_time))
    assert store.load("tenant-a", "run-expired", "suspended") is None
    assert not saved.exists()
