"""Optional Hugging Face Hub source."""

import asyncio
from pathlib import Path
from typing import Sequence

from huggingface_hub import snapshot_download

from orchestrator.inference.sources.base import SourceError
from orchestrator.settings import get_settings


class HuggingFaceSource:
    def __init__(
        self,
        cache_dir: str | Path | None = None,
        token: str | None = None,
        allow_patterns: Sequence[str] | None = None,
    ) -> None:
        settings = get_settings()
        configured_token = settings.hf_token
        self.cache_dir = Path(cache_dir or settings.model_cache_dir).expanduser()
        self.token = token if token is not None else (
            configured_token.get_secret_value() if configured_token is not None else None
        )
        self.allow_patterns = tuple(allow_patterns) if allow_patterns is not None else None

    async def resolve(self, locator: str) -> Path:
        try:
            path = await asyncio.to_thread(
                snapshot_download,
                repo_id=locator,
                local_dir=str(self.cache_dir),
                token=self.token,
                allow_patterns=list(self.allow_patterns) if self.allow_patterns else None,
            )
        except Exception as exc:
            raise SourceError(f"Could not resolve model artifact from Hugging Face: {locator}") from exc
        return Path(path)
