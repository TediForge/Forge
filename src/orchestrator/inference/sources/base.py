"""Source contract for resolving immutable model artifacts."""

from pathlib import Path
from typing import Protocol


class SourceError(RuntimeError):
    """Raised when an artifact cannot be resolved from its configured source."""


class Source(Protocol):
    async def resolve(self, locator: str) -> Path: ...
