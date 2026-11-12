import asyncio
import json
from types import SimpleNamespace

from orchestrator.engine.engine import ForgeEngine
from orchestrator.security.audit import AuditLog
from orchestrator.security.durability import CheckpointStore


INTENT = json.dumps({
    "reasoning": "Direct chat request",
    "modalities_involved": ["text"],
    "primary_capability": "chat",
    "requires_multistep": False,
    "requires_tools": False,
    "extracted_prompt": "hello",
})


def test_responses_run_calls_tmp_cleanup_and_continues_if_cleanup_fails(monkeypatch, tmp_path):
    cleanupCalls = []

    def failCleanup():
        cleanupCalls.append(True)
        raise OSError("temporary storage unavailable")

    def generate(prompt=None, **kwargs):
        return INTENT if "Analyze intent" in (prompt or "") else "answer"

    provider = SimpleNamespace(generate=generate)
    provider.generate_text = generate
    monkeypatch.setattr("orchestrator.engine.engine.cleanupTmp", failCleanup)
    engine = ForgeEngine(
        text_dispatcher=provider,
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
    )

    result = asyncio.run(engine.run("hello", "sandbox-cleanup-test", user_id="user-1", tenant_id="tenant-a"))

    assert cleanupCalls == [True]
    assert "".join(block.text or "" for block in result.content) == "answer"
