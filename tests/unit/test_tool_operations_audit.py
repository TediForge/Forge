import re
from pathlib import Path

import pytest

from orchestrator.tools.executor import ToolExecutor
from orchestrator.tools.registry import create_default_registry


SKILLS = Path(__file__).resolve().parents[2] / "src" / "orchestrator" / "skills" / "tools"


def _documented_operations(tool_name: str) -> set[str]:
    content = (SKILLS / tool_name / "SKILL.md").read_text(encoding="utf-8")
    section = re.search(r"^## Operations\s*$([\s\S]*?)(?=^## |\Z)", content, re.MULTILINE)
    assert section is not None, f"{tool_name} skill must document an Operations table"
    operations = set(re.findall(r"^\| `([^`]+)` \|", section.group(1), re.MULTILINE))
    operations.discard("operation")
    return operations


def _operation_rows(tool_name: str) -> list[str]:
    content = (SKILLS / tool_name / "SKILL.md").read_text(encoding="utf-8")
    section = re.search(r"^## Operations\s*$([\s\S]*?)(?=^## |\Z)", content, re.MULTILINE)
    assert section is not None, f"{tool_name} skill must document an Operations table"
    return [
        line for line in section.group(1).splitlines()
        if re.match(r"^\| `[^`]+` \|", line)
        and line.split("|")[1].strip() != "`operation`"
    ]


def test_every_tool_has_operation():
    registry = create_default_registry()
    for name in registry.names():
        definition = registry.get(name)
        assert definition is not None
        schema = definition["function"]["parameters"]
        assert "operation" in schema["properties"], f"{name} is missing operation"
        assert "operation" in schema["required"], f"{name} must require operation"
        assert schema["properties"]["operation"].get("enum"), f"{name} needs at least one operation"


def test_operation_enum_matches_skill():
    registry = create_default_registry()
    for name in registry.names():
        definition = registry.get(name)
        assert definition is not None
        operations = set(definition["function"]["parameters"]["properties"]["operation"]["enum"])
        assert operations == _documented_operations(name), name
        rows = _operation_rows(name)
        assert all(row.split("|")[-2].strip() == "implemented" for row in rows), name


def test_no_placeholder_operations_in_skills():
    for skill in SKILLS.glob("*/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        assert "placeholder" not in text.lower(), f"{skill} still documents a placeholder"
        assert all(row.split("|")[-2].strip() == "implemented" for row in _operation_rows(skill.parent.name))


def test_skill_quality_bar():
    for skill in SKILLS.glob("*/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        description = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        assert description is not None
        assert "use" in description.group(1).lower()
        assert "not use" in description.group(1).lower()
        sections = {
            match.group(1).strip().lower(): match.group(2)
            for match in re.finditer(r"^## (.+?)\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
        }
        assert len(re.findall(r"^\s*-\s+", sections.get("when to use", ""), re.MULTILINE)) >= 3, skill
        assert len(re.findall(r"^\s*-\s+", sections.get("when not to use", ""), re.MULTILINE)) >= 3, skill
        examples = sections.get("examples", "")
        assert len(re.findall(r"^\s*\d+\.\s+", examples, re.MULTILINE)) >= 5, skill
        assert re.search(r"wrong operation", examples, re.IGNORECASE), skill
        assert len(re.findall(r"^\s*-\s+\*\*", sections.get("edge cases", ""), re.MULTILINE)) >= 5, skill
        assert all(row.count("|") == 5 for row in _operation_rows(skill.parent.name)), skill


class _SearchProvider:
    def search(self, operation, query, max_results, extract_results=0):
        return {"results": [], "errors": []} if operation == "web" else {"results": []}


class _WeatherProvider:
    async def get(self, operation, latitude, longitude, days):
        return {"current": {}, "daily": {}, "timezone": "UTC"}


class _TextDispatcher:
    async def generate(self, prompt, **options):
        return "translated"


class _SpeechDispatcher:
    async def synthesize(self, **options):
        return b"audio"

    async def generate(self, prompt, **options):
        return {"mediaType": "audio", "mediaData": "YXVkaW8=", "mimeType": "audio/wav"}


class _TranscriptionDispatcher:
    async def transcribe(self, **options):
        return {"text": "spoken words", "language": "en", "segments": []}


def _valid_arguments(tool_name: str, operation: str) -> dict:
    arguments = {"operation": operation}
    if tool_name == "audio":
        arguments.update(path="uploads/missing.wav")
        if operation == "trim":
            arguments.update(output_path="outputs/clip.wav", start_seconds=0, duration_seconds=1)
        if operation == "convert":
            arguments.update(output_path="outputs/clip.mp3", output_format="mp3")
    elif tool_name == "calculate":
        arguments["expression"] = "1 + 1"
    elif tool_name == "clock" and operation == "convert":
        arguments.update(from_timezone="UTC", to_timezone="Europe/London", timestamp="2025-01-01T12:00:00")
    elif tool_name == "data":
        if operation == "table":
            arguments.update(path="uploads/missing.csv", options={"operation": "head"})
        elif operation == "sql":
            arguments.update(connection="sqlite:missing.db", query="SELECT 1")
        elif operation == "profile":
            arguments["path"] = "uploads/missing.csv"
        elif operation == "join":
            arguments.update(left_path="uploads/missing.csv", right_path="uploads/missing.csv", left_key="id", right_key="id")
        elif operation == "report":
            arguments.update(title="test", sections=[])
        else:
            arguments.update(path="uploads/missing.csv", chart_type="bar", x_column="x", y_column="y")
    elif tool_name == "extract":
        arguments["text"] = "name,value\nAda,1"
        if operation == "json":
            arguments["schema"] = {"type": "object"}
    elif tool_name == "fetch":
        arguments["url"] = "https://example.org/resource"
    elif tool_name == "generate":
        arguments["prompt"] = "A simple test"
        if operation == "image":
            arguments["output_path"] = "outputs/generated.png"
    elif tool_name == "image":
        if operation in {"info", "resize", "ocr"}:
            arguments["path"] = "uploads/missing.png"
        if operation == "resize":
            arguments.update(output_path="outputs/resized.png", width=10, height=10)
        if operation == "generate":
            arguments.update(prompt="A simple test", output_path="outputs/generated.png")
    elif tool_name == "pdf":
        arguments["path"] = "uploads/missing.pdf"
    elif tool_name == "search":
        arguments["query"] = "test"
    elif tool_name == "sheet":
        arguments.update(path="uploads/missing.csv", headers=["value"], rows=[["x"]])
    elif tool_name == "speak":
        arguments["text"] = "hello"
    elif tool_name == "summarize":
        arguments["text" if operation == "text" else "url"] = "A short sentence." if operation == "text" else "https://example.org/"
    elif tool_name == "transcribe":
        arguments.update(mediaData="YQ==", mimeType="audio/wav")
    elif tool_name == "translate":
        arguments["target_language"] = "French"
        if operation == "text":
            arguments["text"] = "hello"
        else:
            arguments["path"] = "uploads/missing.txt"
    elif tool_name == "video":
        arguments["path"] = "uploads/missing.mp4"
        if operation == "sample":
            arguments.update(timestamps=[0], output_directory="outputs/frames")
        if operation == "keyframe":
            arguments["output_directory"] = "outputs/frames"
    elif tool_name == "weather":
        arguments.update(latitude=0, longitude=0)
        if operation == "forecast":
            arguments["days"] = 1
    return arguments


@pytest.mark.asyncio
async def test_every_operation_is_implemented(sandboxWorkspace):
    registry = create_default_registry()
    executor = ToolExecutor(
        registry=registry,
        toolDependencies={
            "search": {"provider": _SearchProvider()},
            "weather": {"provider": _WeatherProvider()},
            "translate": {"dispatcher": _TextDispatcher()},
            "speak": {"dispatcher": _SpeechDispatcher()},
            "transcribe": {"dispatcher": _TranscriptionDispatcher()},
        },
    )
    for definition in registry.definitions():
        name = definition["function"]["name"]
        operations = definition["function"]["parameters"]["properties"]["operation"]["enum"]
        for operation in operations:
            result = await executor.executeAsync(
                {"function": {"name": name, "arguments": _valid_arguments(name, operation)}},
                context={"tenant_id": "test-tenant", "user_id": "test-user"},
            )
            assert isinstance(result, dict), f"{name}({operation}) returned {type(result).__name__}"
            assert result.get("errorCode") != "NOT_IMPLEMENTED", f"{name}({operation}) is a placeholder"
