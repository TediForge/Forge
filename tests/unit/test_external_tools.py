import asyncio

from src.api.v1.responses.routes import ExecutionPlan, ExecutionStep, ForgeEngine, IntentResult, RefinedPrompt
from src.core.schemas.input import ExternalToolDefinition, FunctionCallOutput, OrchestratorRequest
from src.core.security.audit import AuditLog
from src.core.security.durability import CheckpointStore


def _external_tool(name="getweather"):
    return ExternalToolDefinition(
        name=name,
        description="Get current weather",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}},
    )


class ScriptedDispatcher:
    def __init__(self, plan):
        self.plan = plan
        self.generated = 0

    def generate_structured(self, *, response_schema, **kwargs):
        if response_schema is IntentResult:
            return {
                "reasoning": "A tool is needed",
                "modalities_involved": ["text"],
                "primary_capability": "research",
                "requires_multistep": True,
                "requires_tools": False,
                "extracted_prompt": "Check weather",
            }
        if response_schema is RefinedPrompt:
            return {
                "original_prompt": "Check weather",
                "refined_prompt": "Check the requested weather",
                "objective": "Return an answer",
                "modality_profile": "research",
            }
        if response_schema is ExecutionPlan:
            return self.plan
        raise AssertionError(f"Unexpected structured response: {response_schema}")

    async def generate(self, prompt, **kwargs):
        self.generated += 1
        return "The temperature is 72 degrees."


def _plan(*steps):
    return {
        "reasoning": "Test plan",
        "is_sequential": True,
        "steps": [step.model_dump() for step in steps],
    }


def _engine(tmp_path, plan, dispatcher=None):
    return ForgeEngine(
        text_dispatcher=dispatcher or ScriptedDispatcher(plan),
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
    )


def test_external_tool_suspends_and_resume_completes(tmp_path):
    plan = _plan(
        ExecutionStep(
            step_id=1,
            modality="text",
            capability="integration",
            task_instruction="Get weather",
            tool_calls=["getweather"],
            tool_arguments={"getweather": {"city": "Lagos"}},
        ),
        ExecutionStep(
            step_id=2,
            modality="text",
            capability="unknown_for_test",
            task_instruction="Summarize the result",
            depends_on=[1],
        ),
    )
    dispatcher = ScriptedDispatcher(plan)
    engine = _engine(tmp_path, plan, dispatcher)
    response = asyncio.run(engine.run(
        "Check weather",
        "session-1",
        principal=_principal(),
        external_tools=[_external_tool()],
    ))

    assert response.status == "requires_action"
    assert response.functionCalls[0].name == "getweather"
    assert response.functionCalls[0].call_id.startswith("call_")
    assert response.functionCalls[0].arguments == '{"city":"Lagos"}'
    assert engine.checkpointStore.load("tenant-a", response.runId, "suspended")["status"] == "suspended"

    result = asyncio.run(engine.resume(
        response.runId,
        [FunctionCallOutput(call_id=response.functionCalls[0].call_id, output='{"temp": 72}')],
        principal=_principal(),
    ))
    assert result.status == "completed"
    assert "72" in "".join(block.text or "" for block in result.content)


def test_internal_tool_runs_autonomously_with_external_tools_available(tmp_path):
    plan = _plan(
        ExecutionStep(
            step_id=1,
            modality="text",
            capability="integration",
            task_instruction="Calculate",
            tool_calls=["calculate"],
            tool_arguments={"calculate": {"operation": "evaluate", "expression": "40 + 2"}},
        ),
        ExecutionStep(
            step_id=2,
            modality="text",
            capability="unknown_for_test",
            task_instruction="Answer",
            depends_on=[1],
        ),
    )
    engine = _engine(tmp_path, plan)
    response = asyncio.run(engine.run(
        "Calculate and answer",
        "session-2",
        principal=_principal(),
        external_tools=[_external_tool()],
    ))
    assert response.status == "completed"
    assert response.functionCalls is None
    assert "temperature" in "".join(block.text or "" for block in response.content)


def test_mixed_plan_completes_internal_tool_before_external_suspend(tmp_path):
    plan = _plan(
        ExecutionStep(
            step_id=1,
            modality="text",
            capability="integration",
            task_instruction="Calculate",
            tool_calls=["calculate"],
            tool_arguments={"calculate": {"operation": "evaluate", "expression": "1 + 1"}},
        ),
        ExecutionStep(
            step_id=2,
            modality="text",
            capability="integration",
            task_instruction="Get weather",
            depends_on=[1],
            tool_calls=["getweather"],
            tool_arguments={"getweather": {"city": "Lagos"}},
        ),
        ExecutionStep(
            step_id=3,
            modality="text",
            capability="unknown_for_test",
            task_instruction="Summarize",
            depends_on=[2],
        ),
    )
    engine = _engine(tmp_path, plan)
    pending = asyncio.run(engine.run(
        "Calculate then check weather",
        "session-3",
        principal=_principal(),
        external_tools=[_external_tool()],
    ))
    checkpoint = engine.checkpointStore.load("tenant-a", pending.runId, "suspended")
    assert checkpoint["variables"]["completedToolCalls"]["1:calculate"]["result"] == 2
    completed = asyncio.run(engine.resume(
        pending.runId,
        [FunctionCallOutput(call_id=pending.functionCalls[0].call_id, output="72")],
        principal=_principal(),
    ))
    assert "72" in "".join(block.text or "" for block in completed.content)


def test_resume_is_idempotent_and_checkpoint_can_be_loaded_by_new_engine(tmp_path):
    plan = _plan(
        ExecutionStep(
            step_id=1,
            modality="text",
            capability="integration",
            task_instruction="Get weather",
            tool_calls=["getweather"],
            tool_arguments={"getweather": {"city": "Lagos"}},
        ),
        ExecutionStep(
            step_id=2,
            modality="text",
            capability="unknown_for_test",
            task_instruction="Summarize",
            depends_on=[1],
        ),
    )
    dispatcher = ScriptedDispatcher(plan)
    engine = _engine(tmp_path, plan, dispatcher)
    pending = asyncio.run(engine.run("Check weather", "session-4", principal=_principal(), external_tools=[_external_tool()]))
    output = FunctionCallOutput(call_id=pending.functionCalls[0].call_id, output="72")
    restarted = _engine(tmp_path, plan, dispatcher)

    first = asyncio.run(restarted.resume(pending.runId, [output], principal=_principal()))
    generated_after_first = dispatcher.generated
    second = asyncio.run(restarted.resume(pending.runId, [output], principal=_principal()))

    assert first.content == second.content
    assert dispatcher.generated == generated_after_first == 1


def test_external_tool_name_collision_is_rejected(tmp_path):
    engine = _engine(tmp_path, _plan())
    with __import__("pytest").raises(ValueError, match="collide with internal tools"):
        asyncio.run(engine.run(
            "Check weather",
            "session-collision",
            principal=_principal(),
            external_tools=[_external_tool("calculate")],
        ))


def test_resuming_wrong_call_id_is_rejected(tmp_path):
    plan = _plan(ExecutionStep(
        step_id=1,
        modality="text",
        capability="integration",
        task_instruction="Get weather",
        tool_calls=["getweather"],
    ))
    engine = _engine(tmp_path, plan)
    pending = asyncio.run(engine.run("Check weather", "session-id", principal=_principal(), external_tools=[_external_tool()]))
    with __import__("pytest").raises(ValueError, match="does not match"):
        asyncio.run(engine.resume(
            pending.runId,
            [FunctionCallOutput(call_id="call_wrong", output="72")],
            principal=_principal(),
        ))


def test_stream_suspension_emits_function_call_and_complete_payload(tmp_path):
    plan = _plan(ExecutionStep(
        step_id=1,
        modality="text",
        capability="integration",
        task_instruction="Get weather",
        tool_calls=["getweather"],
        tool_arguments={"getweather": {"city": "Lagos"}},
    ))
    engine = _engine(tmp_path, plan)

    async def collect():
        generator = await engine.run(
            "Check weather",
            "session-stream",
            stream=True,
            principal=_principal(),
            external_tools=[_external_tool()],
        )
        return [frame async for frame in generator]

    events = asyncio.run(collect())
    assert any(frame.startswith("event: function_call\n") for frame in events)
    assert any('"status":"requires_action"' in frame for frame in events)
    complete = next(frame for frame in events if frame.startswith("event: complete\n"))
    assert '"functionCalls"' in complete
    assert '"call_id"' in complete


def _principal():
    from src.core.security.identity import Principal

    return Principal(user_id="user-1", tenant_id="tenant-a", roles=("operator",))


def test_request_carries_external_tools_without_client_controlled_topology():
    inferred = OrchestratorRequest.model_validate({
        "messages": [{"role": "user", "content": "Check weather"}],
        "tools": [{"name": "getweather", "description": "Get weather"}],
    })
    ordinary = OrchestratorRequest.model_validate({
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert inferred.tools[0].name == "getweather"
    assert ordinary.tools == []
    assert not hasattr(inferred, "topology")
