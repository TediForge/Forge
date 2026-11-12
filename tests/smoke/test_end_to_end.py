import asyncio
from types import SimpleNamespace

from src.api.v1.responses.routes import ForgeEngine
from src.core.security.audit import AuditLog
from src.core.security.durability import CheckpointStore


INTENT = (
    '{"reasoning":"Direct text request","modalities_involved":["text"],'
    '"primary_capability":"chat","requires_multistep":false,'
    '"requires_tools":false,"extracted_prompt":"say hi"}'
)


def test_forge_engine_runs_end_to_end(tmp_path):
    def generate(prompt=None, **kwargs):
        return INTENT if "Analyze intent" in (prompt or "") else "Hi there."

    provider = SimpleNamespace(generate=generate, generate_text=generate)
    engine = ForgeEngine(
        text_dispatcher=provider,
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
    )

    response = asyncio.run(
        engine.run(
            prompt="say hi",
            sessionId="test",
            user_id="u1",
            tenant_id="t1",
        )
    )

    assert response.content
    assert response.runId.startswith("run_")
