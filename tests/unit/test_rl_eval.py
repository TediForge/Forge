import json
from pathlib import Path

from orchestrator.rl.test_rl_eval import MockOfflinePolicy, evaluate_golden_tasks


def test_rl_mock_evaluation_loads_the_packaged_golden_dataset():
    fixture = Path(__file__).resolve().parents[2] / "src" / "orchestrator" / "rl" / "fixtures" / "golden_tasks.jsonl"
    tasks = [
        json.loads(line)
        for line in fixture.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    policy = MockOfflinePolicy({task["prompt"]: task["mockResponse"] for task in tasks})

    report = evaluate_golden_tasks(policy, fixture)

    assert report["taskCount"] == len(tasks)
    assert report["passed"] == len(tasks)
