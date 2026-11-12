"""Small helper for resolving model artifacts before backend initialization."""

from pathlib import Path

from orchestrator.inference.sources.base import Source


async def resolve_artifact(source: Source, locator: str) -> Path:
    return await source.resolve(locator)
