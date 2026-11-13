import asyncio

import pytest

from orchestrator.export.trajectory import TrajectoryExporter
from orchestrator.settings import (
    DEFAULT_TRAJECTORY_EXPORT_DIR,
    MAX_ATTACHMENT_BYTES,
    MAX_MEDIA_BYTES,
    Settings,
)


def test_safety_limits_are_not_environment_settings(monkeypatch):
    monkeypatch.setenv("FORGE_ATTACHMENT_MAX_BYTES", "1")
    monkeypatch.setenv("FORGE_MEDIA_MAX_BYTES", "1")
    monkeypatch.setenv("FORGE_MODEL_DEVICE", "cuda")
    monkeypatch.setenv("FORGE_INFERENCE_DEVICE", "cpu")
    settings = Settings()

    assert not hasattr(settings, "attachment_max_bytes")
    assert not hasattr(settings, "media_max_bytes")
    assert settings.inference_device == "cpu"
    assert MAX_ATTACHMENT_BYTES == 10 * 1024 * 1024
    assert MAX_MEDIA_BYTES == 20 * 1024 * 1024


def test_trajectory_export_is_enabled_by_code_and_opted_in_per_request(monkeypatch):
    monkeypatch.setenv("FORGE_TRAJECTORY_EXPORT_ENABLED", "false")
    monkeypatch.setenv("HF_TOKEN", "")
    monkeypatch.setenv("FORGE_HF_REPO_ID", "")

    exporter = TrajectoryExporter.from_environment()
    try:
        assert exporter.enabled is True
        assert exporter.output_dir == DEFAULT_TRAJECTORY_EXPORT_DIR
    finally:
        asyncio.run(exporter.shutdown())


def test_huggingface_upload_requires_token_when_repository_is_configured(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "")
    monkeypatch.setenv("FORGE_HF_REPO_ID", "owner/dataset")

    with pytest.raises(ValueError, match="HF_TOKEN is required"):
        TrajectoryExporter.from_environment()


def test_huggingface_download_token_does_not_require_upload_repository(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "download-token")
    monkeypatch.setenv("FORGE_HF_REPO_ID", "")

    exporter = TrajectoryExporter.from_environment()
    try:
        assert exporter.enabled is True
        assert exporter._huggingface_sync is None
    finally:
        asyncio.run(exporter.shutdown())


def test_huggingface_upload_reuses_hub_token(monkeypatch):
    received = {}

    class FakeHuggingFaceSync:
        def __init__(self, token, repo_id):
            received["token"] = token
            received["repo_id"] = repo_id

    monkeypatch.setattr(
        "orchestrator.export.trajectory.HuggingFaceSync",
        FakeHuggingFaceSync,
    )
    monkeypatch.setenv("HF_TOKEN", "shared-token")
    monkeypatch.setenv("FORGE_HF_REPO_ID", "owner/dataset")

    exporter = TrajectoryExporter.from_environment()
    try:
        assert received == {"token": "shared-token", "repo_id": "owner/dataset"}
    finally:
        asyncio.run(exporter.shutdown())
