import asyncio

import pytest

from src.api.v1.responses.routes import ForgeEngine, IntentResult, RefinedPrompt
from src.core.schemas.input import ExternalToolDefinition
from src.core.security.audit import AuditLog
from src.core.security.durability import CheckpointStore


class DirectDispatcher:
    def generate_structured(self, *, response_schema, **kwargs):
        if response_schema is IntentResult:
            return {
                "reasoning": "Direct response",
                "modalities_involved": ["text"],
                "primary_capability": "unmatched_test_capability",
                "requires_multistep": False,
                "requires_tools": False,
                "extracted_prompt": "hello",
            }
        if response_schema is RefinedPrompt:
            return {
                "original_prompt": "hello",
                "refined_prompt": "hello",
                "objective": "Answer",
                "modality_profile": "text",
            }
        raise AssertionError(f"Unexpected planner call: {response_schema}")

    async def generate(self, prompt, **kwargs):
        return "answer"


def _engine(tmp_path):
    return ForgeEngine(
        text_dispatcher=DirectDispatcher(),
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
    )


def _principal():
    from src.core.security.identity import Principal

    return Principal("user-1", "tenant-a", roles=("operator",))


def _run(engine, **kwargs):
    return asyncio.run(engine.run(
        "hello",
        "session-training",
        principal=_principal(),
        **kwargs,
    ))


async def _run_and_shutdown(engine, **kwargs):
    response = await engine.run(
        "hello",
        "session-training",
        principal=_principal(),
        **kwargs,
    )
    await engine.trainingExporter.shutdown()
    return response


def test_training_export_is_per_request_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_ENABLED", "true")
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_DIR", str(tmp_path / "exports"))
    engine = _engine(tmp_path)
    response = asyncio.run(_run_and_shutdown(engine))
    assert response.status == "completed"
    assert not list((tmp_path / "exports").glob("*.jsonl"))


def test_opted_in_completed_autonomous_run_is_exported(tmp_path, monkeypatch):
    export_dir = tmp_path / "exports"
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_ENABLED", "true")
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_DIR", str(export_dir))
    engine = _engine(tmp_path)
    response = asyncio.run(_run_and_shutdown(engine, training_export=True))
    assert response.status == "completed"
    assert len(list(export_dir.glob("*.jsonl"))) == 1


def test_export_request_is_rejected_when_server_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_ENABLED", "false")
    engine = _engine(tmp_path)
    with pytest.raises(ValueError, match="trainingExport requested but training export is disabled server-side"):
        _run(engine, training_export=True)


def test_interactive_training_export_is_rejected_even_with_external_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_ENABLED", "true")
    engine = _engine(tmp_path)
    external = [ExternalToolDefinition(name="getweather", description="Get weather")]
    with pytest.raises(ValueError, match="not supported for interactive runs"):
        _run(
            engine,
            training_export=True,
            external_tools=external,
        )


def test_failed_run_is_not_exported(tmp_path, monkeypatch):
    export_dir = tmp_path / "exports"
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_ENABLED", "true")
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_DIR", str(export_dir))
    engine = _engine(tmp_path)

    async def failed_graph(plan, state, budget):
        budget.terminal_status = "failed"
        budget.termination_reason = "test failure"
        return "", [], [], [], []

    engine._executeGraphStatic = failed_graph
    response = asyncio.run(_run_and_shutdown(engine, training_export=True))
    assert response.status == "failed"
    assert not list(export_dir.glob("*.jsonl"))
