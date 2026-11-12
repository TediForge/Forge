import asyncio

import pytest

from orchestrator.context.limits import ExecutionBudget, ExecutionLimitError, ExecutionLimits
from orchestrator.security.durability import CheckpointStore


def test_tool_call_count_limit_and_duplicate_fingerprint():
    budget = ExecutionBudget(ExecutionLimits(max_tool_calls=20))
    for index in range(20):
        budget.record_tool_call(f"tool-{index}", {"index": index})
    with pytest.raises(ExecutionLimitError):
        budget.record_tool_call("overflow", {})

    duplicate_budget = ExecutionBudget()
    for _ in range(3):
        duplicate_budget.record_tool_call("lookup", {"id": 1})
    with pytest.raises(ExecutionLimitError, match="Duplicate"):
        duplicate_budget.record_tool_call("lookup", {"id": 1})


def test_external_function_suspension_does_not_consume_internal_budget(tmp_path):
    from orchestrator.engine.engine import ForgeEngine, SuspensionSignal
    from orchestrator.context.state import ExecutionState
    from orchestrator.security.audit import AuditLog

    engine = ForgeEngine(
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
    )
    state = ExecutionState("run-1", {
        "tenantId": "tenant-1",
        "userId": "user-1",
        "topology": "interactive",
        "externalToolNames": ["caller_tool"],
        "currentStepId": 1,
        "currentToolArguments": {"value": "ok"},
    })
    budget = ExecutionBudget(ExecutionLimits(max_tool_calls=0))
    with pytest.raises(SuspensionSignal):
        asyncio.run(engine._executeToolCall("caller_tool", state, budget))
    assert budget.tool_calls == 0
    assert engine.checkpointStore.load("tenant-1", "run-1", "suspended")["status"] == "suspended"
    asyncio.run(engine.mediaConverter.close())


def test_tool_budget_breach_fails_run_and_writes_audit(tmp_path):
    from orchestrator.engine.engine import ExecutionPlan, ExecutionStep, ForgeEngine
    from orchestrator.context.state import ExecutionState
    from orchestrator.security.audit import AuditLog

    class Registry:
        def names(self):
            return ["internal_tool"]

        def actionFor(self, name, arguments):
            return {
                "actionId": "A123AB",
                "actionType": "tool",
                "toolName": name,
                "message": f"Running {name}",
                "metadata": {},
            }

    audit = AuditLog(tmp_path / "audit.jsonl")
    engine = ForgeEngine(audit_log=audit)
    engine.toolRegistry = Registry()
    state = ExecutionState("run-limit", {
        "tenantId": "tenant-1",
        "userId": "user-1",
        "toolArguments": {"internal_tool": {}},
    })
    plan = ExecutionPlan(
        reasoning="test",
        steps=[ExecutionStep(
            step_id=1,
            modality="text",
            capability="integration",
            task_instruction="Run tool",
            tool_calls=["internal_tool"],
        )],
    )
    budget = ExecutionBudget(ExecutionLimits(max_tool_calls=0))
    asyncio.run(engine._executeGraphStatic(plan, state, budget))

    assert budget.termination_reason == "tool_call_limit"
    assert any(event.get("status") == "failed" for event in state.getVariable("events", []))
    assert '"run.failed"' in (tmp_path / "audit.jsonl").read_text()
    asyncio.run(engine.mediaConverter.close())
