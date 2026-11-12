import asyncio
import json

from orchestrator.tools.executor import ToolExecutor, ToolResult


class SchemaRegistry:
    def __init__(self):
        self.calls = []
        self.definition = {
            "type": "function",
            "function": {
                "name": "lookup",
                "parameters": {
                    "type": "object",
                    "properties": {"mode": {"type": "string", "enum": ["fast", "safe"]}},
                    "required": ["mode"],
                    "additionalProperties": False,
                },
            },
        }

    def get(self, name):
        return self.definition if name == "lookup" else None

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return {"success": True, "data": "ok"}


def test_executor_validates_required_type_enum_and_unknown_tools():
    registry = SchemaRegistry()
    executor = ToolExecutor(registry=registry)
    valid = asyncio.run(executor.executeAsync({
        "function": {"name": "lookup", "arguments": {"mode": "safe"}},
    }))
    assert valid["success"] is True
    assert len(registry.calls) == 1

    for arguments in ({}, {"mode": 1}, {"mode": "unsafe"}):
        result = asyncio.run(executor.executeAsync({
            "function": {"name": "lookup", "arguments": arguments},
        }))
        assert isinstance(result, ToolResult)
        assert result.code == "INVALID_ARGUMENTS"
    unknown = asyncio.run(executor.executeAsync({"function": {"name": "missing", "arguments": {}}}))
    assert unknown.code == "UNKNOWN_TOOL"
    assert len(registry.calls) == 1


def test_audit_error_details_do_not_include_raw_arguments(tmp_path):
    from orchestrator.engine.engine import ForgeEngine
    from orchestrator.context.state import ExecutionState
    from orchestrator.security.audit import AuditLog

    registry = SchemaRegistry()
    engine = ForgeEngine(audit_log=AuditLog(tmp_path / "audit.jsonl"))
    engine.toolRegistry = registry
    engine.toolExecutor = ToolExecutor(registry=registry, mediaConverter=engine.mediaConverter)
    state = ExecutionState("run-1", {
        "tenantId": "tenant-1",
        "userId": "user-1",
        "toolArguments": {"lookup": {"mode": "secret-value"}},
    })
    result = asyncio.run(engine._executeToolCall("lookup", state))
    assert result["code"] == "INVALID_ARGUMENTS"
    action = engine._actionEvent(
        "lookup",
        {"actionId": "A123AB", "actionType": "tool", "toolName": "lookup", "message": "Lookup"},
        "failed",
        "start",
        "end",
        result,
    )["data"]
    assert action["status"] == "failed"
    assert action["error"]["code"] == "INVALID_ARGUMENTS"
    line = (tmp_path / "audit.jsonl").read_text()
    assert '"action.invalid_arguments"' in line
    assert '"toolName": "lookup"' in line
    assert "secret-value" not in line
