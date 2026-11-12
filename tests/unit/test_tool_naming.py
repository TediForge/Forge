import asyncio
import re
from pathlib import Path

import pytest

from orchestrator.tools.registry import ToolRegistry, create_default_registry


def test_registered_tool_names_are_one_lowercase_word_and_have_skills():
    registry = create_default_registry()

    assert registry.names()
    assert all(re.fullmatch(r"[a-z][a-z0-9]*", name) for name in registry.names())


def test_registry_rejects_nonconforming_tool_name():
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="one lowercase word"):
        registry.register("bad_tool", {}, lambda: None)


def test_registry_rejects_tool_without_skill():
    registry = ToolRegistry()

    with pytest.raises(FileNotFoundError, match="tools/notfound"):
        registry.register("notfound", {}, lambda: None)


def test_every_registered_tool_skill_has_examples_and_named_edge_cases():
    project_root = Path(__file__).parents[2]
    registry = create_default_registry()

    for name in registry.names():
        skill = (
            project_root / "src" / "orchestrator" / "skills" / "tools" / name / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert len(skill.splitlines()) < 500
        assert "## When to use" in skill
        assert "## When not to use" in skill
        assert "## How to call" in skill or "## Procedure and call" in skill
        assert "## Examples" in skill
        assert "## Edge cases" in skill
        examples = skill.split("## Examples", 1)[1].split("\n## ", 1)[0]
        edge_cases = skill.split("## Edge cases", 1)[1].split("\n## ", 1)[0]
        assert len(re.findall(r"(?m)^\d+\.", examples)) >= 5, name
        assert len(re.findall(r"(?m)^- \*\*.+?\*\*", edge_cases)) >= 5, name


def test_tool_skill_folders_match_registered_tool_names_exactly():
    project_root = Path(__file__).parents[2]
    skill_root = project_root / "src" / "orchestrator" / "skills" / "tools"
    registered = set(create_default_registry().names())
    skill_names = {
        directory.name for directory in skill_root.iterdir()
        if directory.is_dir() and (directory / "SKILL.md").is_file()
    }

    assert skill_names == registered


def test_registry_execute_async_awaits_async_handler():
    registry = ToolRegistry()

    async def handler():
        return "completed"

    registry.register("clock", {"type": "function", "function": {"name": "clock"}}, handler)

    assert asyncio.run(registry.executeAsync("clock")) == "completed"
