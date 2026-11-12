"""Reserved interface for private artifact registries and object stores."""

from pathlib import Path

from orchestrator.inference.sources.base import SourceError


class ArtifactStoreSource:
    async def resolve(self, locator: str) -> Path:
        raise SourceError(
            f"Artifact-store source is not configured for locator '{locator}'. "
            "Configure a private artifact source before using this model."
        )
