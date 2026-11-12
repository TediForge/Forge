from pathlib import Path

from orchestrator.tools import definitions


def test_tool_definitions_do_not_configure_or_call_openai():
    directory = Path(definitions.__file__).parent
    prohibited = (
        "FORGE_OPENAI_API_KEY",
        "FORGE_OPENAI_BASE_URL",
        "api.openai.com",
        "from openai import",
    )
    for path in directory.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for marker in prohibited:
            assert marker not in source, f"{marker} found in {path.name}"
        if path.name != "weather.py":
            assert "httpx" not in source, f"HTTP client belongs only to its tool implementation: {path.name}"
