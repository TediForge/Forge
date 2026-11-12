import re
from pathlib import Path

from orchestrator.tools.registry import create_default_registry


SKILLS = Path(__file__).resolve().parents[2] / "src" / "orchestrator" / "skills" / "tools"


def test_one_skill_per_registered_tool():
    toolNames = set(create_default_registry().names())
    skillDirectories = {path.name for path in SKILLS.iterdir() if path.is_dir()}
    assert toolNames == skillDirectories, f"tool/skill mismatch: {toolNames ^ skillDirectories}"


def test_one_skill_md_per_folder():
    for folder in SKILLS.iterdir():
        if folder.is_dir():
            assert (folder / "SKILL.md").is_file(), f"missing SKILL.md in {folder}"
            assert list(folder.glob("*.md")) == [folder / "SKILL.md"], f"extra Markdown file in {folder}"


def _skillOperations(toolName: str) -> set[str]:
    content = (SKILLS / toolName / "SKILL.md").read_text(encoding="utf-8")
    section = re.search(r"^## Operations\s*$([\s\S]*?)(?=^## |\Z)", content, re.MULTILINE)
    assert section is not None, f"{toolName} skill must document an Operations table"
    operations = set(re.findall(r"^\| `([^`]+)` \|", section.group(1), re.MULTILINE))
    operations.discard("operation")
    return operations


def test_domain_tool_schemas_match_documented_operations():
    registry = create_default_registry()
    for toolName in ("data", "image", "video"):
        definition = registry.get(toolName)
        assert definition is not None
        parameters = definition["function"]["parameters"]
        operationSchema = parameters["properties"].get("operation")
        if operationSchema is not None and "enum" in operationSchema:
            schemaOperations = set(operationSchema["enum"])
        else:
            schemaOperations = {
                branch["properties"]["operation"]["const"]
                for branch in parameters["oneOf"]
            }
        assert schemaOperations == _skillOperations(toolName)
