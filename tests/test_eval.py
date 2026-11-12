"""Deterministic golden-task evaluation tests for Forge planning behavior."""

import json
from pathlib import Path

from src.api.v1.responses.routes import IntentResult, ExecutionPlanner
from src.core.schemas.input import ExternalToolDefinition
from src.tools.registry import create_default_registry


class GoldenPlanDispatcher:
    def generate_structured(self, system_prompt, prompt, response_schema):
        assert "issue" in prompt
        return {
            "reasoning": "Prepare issue details, then suspend for the caller-owned tool.",
            "is_sequential": True,
            "steps": [
                {"step_id": 1, "modality": "text", "capability": "research", "task_instruction": "Prepare issue details"},
                {"step_id": 2, "modality": "text", "capability": "external_tool", "task_instruction": "Create an issue", "depends_on": [1], "tool_calls": ["issue"]},
            ],
        }


def run_eval() -> dict:
    fixture_path = Path(__file__).with_name("golden_tasks.json")
    tasks = json.loads(fixture_path.read_text(encoding="utf-8"))
    failures = []
    results = []
    planner = ExecutionPlanner(
        text_dispatcher=GoldenPlanDispatcher(),
        toolRegistry=create_default_registry(),
    )
    external_tools = [ExternalToolDefinition(
        name="issue",
        description="Create an issue through the caller-owned service.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    )]

    for task in tasks:
        intent = IntentResult.model_validate(task["intent"])
        plan = planner.create_plan(
            intent,
            external_tools=external_tools if intent.requires_tools else None,
        )
        step_count = len(plan.steps)
        errors = []

        if not task["min_steps"] <= step_count <= task["max_steps"]:
            errors.append(f"expected {task['min_steps']}..{task['max_steps']} steps, got {step_count}")

        dependency_pair = task.get("required_dependency")
        if dependency_pair:
            parent_id, child_id = dependency_pair
            child = next((step for step in plan.steps if step.step_id == child_id), None)
            if child is None or parent_id not in (child.depends_on or []):
                errors.append(f"step {child_id} must depend on step {parent_id}")

        if errors:
            failures.extend(f"{task['id']}: {error}" for error in errors)
        results.append({"id": task["id"], "steps": step_count, "passed": not errors})

    return {"tasks": results, "failed": failures, "passed": len(results) - len(failures)}


def test_golden_tasks():
    report = run_eval()
    assert not report["failed"], "\n".join(report["failed"])
    assert report["passed"] == len(report["tasks"])
