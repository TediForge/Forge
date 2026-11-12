import asyncio

from orchestrator.engine.engine import ExecutionPlan, ExecutionPlanner, ExecutionStep, ForgeEngine, IntentResult, RefinedPrompt
from orchestrator.schemas.v1.responses import ExternalToolDefinition, OrchestratorRequest
from orchestrator.security.audit import AuditLog
from orchestrator.security.durability import CheckpointStore


class PlanDispatcher:
    def __init__(self):
        self.planner_prompt = ""

    def generate_structured(self, *, response_schema, prompt, **kwargs):
        if response_schema is IntentResult:
            return {
                "reasoning": "Tool path",
                "modalities_involved": ["text"],
                "primary_capability": "research",
                "requires_multistep": True,
                "requires_tools": False,
                "extracted_prompt": "check",
            }
        if response_schema is RefinedPrompt:
            return {
                "original_prompt": "check",
                "refined_prompt": "check",
                "objective": "answer",
                "modality_profile": "research",
            }
        if response_schema is ExecutionPlan:
            self.planner_prompt = prompt
            return {
                "reasoning": "external action",
                "steps": [{
                    "step_id": 1,
                    "modality": "text",
                    "capability": "integration",
                    "task_instruction": "invoke caller tool",
                    "tool_calls": ["externallookup"],
                    "tool_arguments": {"externallookup": {"query": "q"}},
                }],
            }
        raise AssertionError(response_schema)

    async def generate(self, prompt, **kwargs):
        return "answer"


def _principal():
    from orchestrator.security.identity import Principal

    return Principal("user-1", "tenant-a", roles=("operator",))


def test_effort_is_nested_and_topology_is_derived_from_tools():
    expert = OrchestratorRequest.model_validate({
        "messages": [{"role": "user", "content": "hello"}],
        "reasoning": {"effort": "high"},
    })
    fast_interactive = OrchestratorRequest.model_validate({
        "messages": [{"role": "user", "content": "check"}],
        "reasoning": {"effort": "low"},
        "tools": [{"name": "externallookup", "description": "lookup"}],
    })
    assert expert.reasoning.effort == "high"
    assert fast_interactive.reasoning.effort == "low"
    assert fast_interactive.tools[0].name == "externallookup"
    assert not hasattr(expert, "topology")


def test_planner_receives_effort_and_interactive_run_suspends_independently(tmp_path):
    dispatcher = PlanDispatcher()
    engine = ForgeEngine(
        text_dispatcher=dispatcher,
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
    )
    pending = asyncio.run(engine.run(
        "check",
        "session-mode",
        principal=_principal(),
        external_tools=[ExternalToolDefinition(name="externallookup", description="lookup")],
        reasoning_effort="low",
    ))
    assert "Execution effort: low" in dispatcher.planner_prompt
    assert pending.status == "requires_action"


def test_expert_effort_with_autonomous_topology_does_not_suspend(tmp_path):
    class InternalToolDispatcher(PlanDispatcher):
        def generate_structured(self, *, response_schema, prompt, **kwargs):
            if response_schema is ExecutionPlan:
                self.planner_prompt = prompt
                return {
                    "reasoning": "Use an internal tool autonomously.",
                    "steps": [
                        {
                            "step_id": 1,
                            "modality": "text",
                            "capability": "integration",
                            "task_instruction": "calculate",
                            "tool_calls": ["calculate"],
                            "tool_arguments": {"calculate": {"operation": "evaluate", "expression": "40 + 2"}},
                        },
                        {
                            "step_id": 2,
                            "modality": "text",
                            "capability": "unmatched_test_capability",
                            "task_instruction": "answer",
                            "depends_on": [1],
                        },
                    ],
                }
            return super().generate_structured(response_schema=response_schema, prompt=prompt, **kwargs)

    dispatcher = InternalToolDispatcher()
    engine = ForgeEngine(
        text_dispatcher=dispatcher,
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
    )
    response = asyncio.run(engine.run(
        "calculate then answer",
        "session-expert",
        principal=_principal(),
        reasoning_effort="high",
    ))
    assert "Execution effort: high" in dispatcher.planner_prompt
    assert response.status == "completed"
    assert response.functionCalls is None


def test_expert_effort_with_interactive_topology_still_suspends(tmp_path):
    dispatcher = PlanDispatcher()
    engine = ForgeEngine(
        text_dispatcher=dispatcher,
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
    )
    pending = asyncio.run(engine.run(
        "check",
        "session-expert-interactive",
        principal=_principal(),
        external_tools=[ExternalToolDefinition(name="externallookup", description="lookup")],
        reasoning_effort="high",
    ))
    assert "Execution effort: high" in dispatcher.planner_prompt
    assert pending.status == "requires_action"
