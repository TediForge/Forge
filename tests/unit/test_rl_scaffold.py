import json
from pathlib import Path


def test_offline_preference_fixture_is_valid_jsonl():
    projectRoot = Path(__file__).resolve().parents[2]
    fixturePath = projectRoot / "src" / "orchestrator" / "rl" / "fixtures" / "preferences.jsonl"
    records = [
        json.loads(line)
        for line in fixturePath.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(records) == 1
    record = records[0]
    assert record["schemaVersion"] == "1.0"
    assert record["exampleId"]
    assert record["prompt"]
    assert record["chosen"]
    assert record["rejected"]
