"""Validated application settings and environment variable mapping."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_MEDIA_BYTES = 20 * 1024 * 1024
DEFAULT_TRAJECTORY_EXPORT_DIR = Path("logs/trajectories")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    checkpoint_root: Path | None = None
    checkpoint_retention_days: int = Field(default=30, ge=1)
    audit_log_path: Path = Path("logs/forge-audit.jsonl")
    sandbox_root: Path | None = None
    media_allowed_hosts: str = ""
    model_cache_dir: Path = Path("data/models")
    inference_device: str = "cpu"
    inference_max_concurrency: int = Field(default=4, ge=1)
    inference_timeout_seconds: float = Field(default=120, gt=0)
    inference_default_backends: dict[str, str] = Field(default_factory=lambda: {
        "text": "transformers",
        "vision": "transformers",
        "embedding": "transformers",
        "image_gen": "diffusers",
        "speech": "piper",
        "transcription": "whisper",
        "video": "diffusers",
    })
    inference_model_backends: dict[str, str] = Field(default_factory=dict)
    inference_model_sources: dict[str, dict[str, str]] = Field(default_factory=dict)
    otlp_endpoint: str = Field(default="", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    hf_token: SecretStr | None = Field(default=None, validation_alias="HF_TOKEN")
    allow_anonymous: bool = False
    hf_repo_id: str = ""

    @property
    def resolved_checkpoint_root(self) -> Path:
        if self.checkpoint_root is not None:
            return self.checkpoint_root.expanduser().resolve()
        return (Path(__file__).resolve().parents[2] / "data" / "checkpoints").resolve()

    @property
    def resolved_sandbox_root(self) -> Path:
        if self.sandbox_root is not None:
            return self.sandbox_root.expanduser().resolve()
        return (Path(__file__).resolve().parent / "computer").resolve()

    @property
    def allowed_media_hosts(self) -> frozenset[str]:
        return frozenset(
            host.strip().casefold()
            for host in self.media_allowed_hosts.split(",")
            if host.strip()
        )


def get_settings() -> Settings:
    return Settings()
