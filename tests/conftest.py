import json
from pathlib import Path

import pytest


@pytest.fixture
def sandboxWorkspace(tmp_path, monkeypatch):
    projectRoot = Path(__file__).resolve().parents[1]
    sandboxRoot = tmp_path / "sandbox"
    workspaceRoot = sandboxRoot / "workspace"
    for directoryName in ("uploads", "outputs", "tmp"):
        (workspaceRoot / directoryName).mkdir(parents=True, exist_ok=True)
    policy = json.loads(
        (projectRoot / "src" / "orchestrator" / "sandbox" / "policy.json").read_text(encoding="utf-8")
    )
    (sandboxRoot / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setenv("FORGE_SANDBOX_ROOT", str(sandboxRoot))
    return workspaceRoot
