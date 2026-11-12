"""Deterministic mock evaluation for the offline post-training scaffold."""

import json
from pathlib import Path
from typing import Any


GOLDEN_TASKS = Path(__file__).parent / "fixtures" / "golden_tasks.jsonl"


class MockOfflinePolicy:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        try:
            return self.responses[prompt]
        except KeyError as exc:
            raise ValueError(f"No mock response configured for prompt: {prompt}") from exc


def evaluate_golden_tasks(
    policy: Any,
    dataset_path: Path = GOLDEN_TASKS,
) -> dict[str, Any]:
    tasks = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    task_ids: set[str] = set()
    results = []
    for task in tasks:
        if task.get("schemaVersion") != "1.0":
            raise ValueError("Unsupported golden-task schema version")
        task_id = task.get("taskId")
        prompt = task.get("prompt")
        expected = task.get("expected")
        if not all(isinstance(value, str) and value.strip() for value in (task_id, prompt, expected)):
            raise ValueError("Golden tasks require non-empty taskId, prompt, and expected fields")
        if task_id in task_ids:
            raise ValueError(f"Duplicate golden-task ID: {task_id}")
        task_ids.add(task_id)
        actual = policy.generate(prompt)
        passed = isinstance(actual, str) and actual.strip() == expected.strip()
        results.append({"taskId": task_id, "passed": passed})

    if not results:
        raise ValueError("Golden-task dataset is empty")
    passed_count = sum(result["passed"] for result in results)
    return {
        "taskCount": len(results),
        "passed": passed_count,
        "passRate": passed_count / len(results),
        "results": results,
    }


def test_golden_dataset_runs_through_mock_offline_evaluation():
    tasks = [
        json.loads(line)
        for line in GOLDEN_TASKS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    policy = MockOfflinePolicy({task["prompt"]: task["mockResponse"] for task in tasks})

    report = evaluate_golden_tasks(policy)

    assert report["taskCount"] == 2
    assert report["passed"] == 2
    assert report["passRate"] == 1.0
    assert len(policy.calls) == 2


def test_golden_evaluator_detects_incorrect_policy_outputs():
    class IncorrectPolicy:
        def generate(self, _prompt: str) -> str:
            return "incorrect"

    report = evaluate_golden_tasks(IncorrectPolicy())

    assert report["passed"] == 0
    assert report["passRate"] == 0.0
