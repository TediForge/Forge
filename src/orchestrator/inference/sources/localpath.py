"""Explicit local filesystem model source; this source never uses the network."""

import asyncio
from pathlib import Path

from orchestrator.inference.sources.base import SourceError


class LocalPathSource:
    async def resolve(self, locator: str) -> Path:
        return await asyncio.to_thread(self._resolve, locator)

    @staticmethod
    def _resolve(locator: str) -> Path:
        path = Path(locator).expanduser()
        try:
            return path.resolve(strict=True)
        except OSError as exc:
            raise SourceError(f"Local model path does not exist or cannot be accessed: {path}") from exc
