"""Durable execution checkpoint storage."""

import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any

from orchestrator.settings import get_settings


class CheckpointStore:
    def __init__(self, root: str | Path | None = None, retention_days: int | None = None) -> None:
        settings = get_settings()
        self.root = Path(root or settings.resolved_checkpoint_root).resolve()
        self.retention_days = retention_days if retention_days is not None else settings.checkpoint_retention_days
        if self.retention_days < 1:
            raise ValueError("Checkpoint retention must be at least one day")
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_component(value: str, label: str) -> None:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
            raise ValueError(f"Invalid checkpoint {label}")

    def _path(self, tenant_id: str, run_id: str, checkpoint: str) -> Path:
        self._validate_component(tenant_id, "tenant ID")
        self._validate_component(run_id, "run ID")
        self._validate_component(checkpoint, "name")
        tenant_root = (self.root / tenant_id).resolve()
        try:
            tenant_root.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Checkpoint tenant path escapes storage root") from exc
        path = (tenant_root / f"{run_id}.{checkpoint}.json").resolve()
        try:
            path.relative_to(tenant_root)
        except ValueError as exc:
            raise ValueError("Checkpoint path escapes tenant storage") from exc
        return path

    def _prune_expired(self, tenant_root: Path) -> None:
        expiry = time.time() - self.retention_days * 86400
        for path in tenant_root.glob("*.json"):
            resolved_path = path.resolve()
            try:
                resolved_path.relative_to(tenant_root)
            except ValueError:
                continue
            try:
                if resolved_path.stat().st_mtime < expiry:
                    resolved_path.unlink()
            except FileNotFoundError:
                continue

    def save(self, tenant_id: str, run_id: str, checkpoint: str, state: dict[str, Any]) -> Path:
        path = self._path(tenant_id, run_id, checkpoint)
        tenant_root = path.parent
        tenant_root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, ensure_ascii=True, sort_keys=True, indent=2)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=tenant_root,
                prefix=f".{run_id}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        self._prune_expired(tenant_root)
        return path

    def load(self, tenant_id: str, run_id: str, checkpoint: str) -> dict[str, Any] | None:
        path = self._path(tenant_id, run_id, checkpoint)
        if not path.is_file():
            return None
        if path.stat().st_mtime < time.time() - self.retention_days * 86400:
            path.unlink()
            return None
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
