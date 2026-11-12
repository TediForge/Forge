import json
from pathlib import Path

from orchestrator.api import app


def test_committed_openapi_matches_api_schema():
    project_root = Path(__file__).resolve().parents[2]
    committed = json.loads(
        (project_root / "docs" / "openapi.json").read_text(encoding="utf-8")
    )

    assert committed == app.openapi()
