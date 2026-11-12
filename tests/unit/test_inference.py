import asyncio

import pytest

from orchestrator.inference.backends.base import Backend, BackendUnavailableError
from orchestrator.inference.gateway import InferenceGateway
from orchestrator.inference.protocols import InferenceRequest
from orchestrator.inference.registry import ModelRegistration
from orchestrator.inference.sources import LocalPathSource
from orchestrator.inference.registry import MODELS
from orchestrator.settings import Settings


class FakeBackend(Backend):
    backend_id = "fake"
    modalities = frozenset({"text"})

    def __init__(self):
        self.closed = False
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        return f"answer: {request.input}"

    async def health(self):
        return not self.closed

    async def close(self):
        self.closed = True


def _entry(source_type="localpath", locator="unused"):
    return ModelRegistration(
        model_id="test",
        modalities=("text",),
        default_backend="fake",
        source_type=source_type,
        locator=locator,
        definition=MODELS["text"],
    )


def test_local_source_resolves_without_network_and_gateway_caches_backend(tmp_path, monkeypatch):
    model_path = tmp_path / "weights"
    model_path.mkdir()
    monkeypatch.setattr("socket.getaddrinfo", lambda *_args, **_kwargs: pytest.fail("network used"))
    settings = Settings(
        inference_model_sources={"test": {"type": "localpath", "locator": str(model_path)}},
        inference_default_backends={"text": "fake"},
    )
    backend = FakeBackend()
    gateway = InferenceGateway(
        registry={"test": _entry()},
        source_factory=lambda _entry: LocalPathSource(),
        backend_factories={"fake": lambda *_args: backend},
        settings=settings,
    )

    async def scenario():
        results = await asyncio.gather(*[
            gateway.infer(InferenceRequest("test", "text", f"prompt-{index}"))
            for index in range(4)
        ])
        assert [result.output for result in results] == [
            f"answer: prompt-{index}" for index in range(4)
        ]
        assert all(result.backend_id == "fake" for result in results)
        assert await gateway.health()
        await gateway.close()
        assert backend.closed

    asyncio.run(scenario())
    with pytest.raises(RuntimeError, match="closed"):
        asyncio.run(gateway.infer(InferenceRequest("test", "text", "after close")))


def test_gateway_reports_unknown_optional_backend_before_loading(tmp_path):
    settings = Settings(inference_default_backends={"text": "missing"})
    gateway = InferenceGateway(
        registry={"test": _entry()},
        settings=settings,
    )
    with pytest.raises(BackendUnavailableError, match="configured.*unavailable"):
        asyncio.run(gateway.resolve("test", "text"))


def test_gateway_rejects_unsupported_model_modality(tmp_path):
    gateway = InferenceGateway(registry={"test": _entry()})
    with pytest.raises(ValueError, match="does not support modality"):
        asyncio.run(gateway.resolve("test", "vision"))


def test_local_path_source_fails_explicitly_for_missing_path(tmp_path):
    with pytest.raises(Exception, match="does not exist"):
        asyncio.run(LocalPathSource().resolve(str(tmp_path / "missing")))


def test_responses_suggestions_are_optional_bounded_and_status_scoped():
    from orchestrator.schemas.v1.responses import (
        ContentBlock,
        FollowUpSuggestion,
        UnifiedOrchestratorResponse,
    )

    assert UnifiedOrchestratorResponse(runId="r").suggestions == []
    with pytest.raises(ValueError):
        FollowUpSuggestion(prompt="")
    with pytest.raises(ValueError):
        UnifiedOrchestratorResponse(
            runId="r",
            suggestions=[FollowUpSuggestion(prompt="one")] * 5,
        )
    with pytest.raises(ValueError):
        UnifiedOrchestratorResponse(
            runId="r",
            status="requires_action",
            suggestions=[
                FollowUpSuggestion(prompt="one"),
                FollowUpSuggestion(prompt="two"),
            ],
        )
    response = UnifiedOrchestratorResponse(
        runId="r",
        content=[ContentBlock(type="text", text="answer")],
        suggestions=[
            FollowUpSuggestion(prompt="Show a comparison", title="Compare"),
            FollowUpSuggestion(prompt="Explain the tradeoffs"),
        ],
    )
    assert len(response.suggestions) == 2
