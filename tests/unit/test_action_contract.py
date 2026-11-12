import re
from pathlib import Path

from orchestrator.tools.registry import create_default_registry


def _operations_for(definition: dict) -> list[str]:
    function = definition.get("function", definition)
    parameters = function.get("parameters", {})
    return parameters["properties"]["operation"]["enum"]


def _arguments_for_operation(tool_name: str, operation: str) -> dict:
    arguments = {"operation": operation}
    if tool_name in {"search"}:
        arguments["query"] = "test"
    elif tool_name in {"sheet", "audio", "image"} and operation != "generate":
        arguments["path"] = "test"
    elif tool_name == "image" and operation == "generate":
        arguments.update({"prompt": "test", "output_path": "test.png"})
    elif tool_name == "summarize" and operation == "url":
        arguments["url"] = "https://example.com"
    elif tool_name == "data":
        arguments.update({
            "path": "test",
            "options": {"operation": "profile"},
            "connection": "sqlite:test.db",
            "query": "SELECT 1",
            "left_path": "left.csv",
            "right_path": "right.csv",
            "left_key": "id",
            "title": "test",
            "sections": [],
            "chart_type": "bar",
            "x_column": "x",
            "y_column": "y",
        })
    return arguments


def test_registered_action_ids_are_unique_and_documented():
    registry = create_default_registry()
    documented = set(re.findall(
        r"`(A[A-Z0-9]{5})`",
        (Path(__file__).parents[2] / "docs" / "references" / "action-ids.md").read_text(encoding="utf-8"),
    ))
    seen = {}

    for definition in registry.definitions():
        function = definition.get("function", definition)
        name = function["name"]
        for operation in _operations_for(definition):
            arguments = _arguments_for_operation(name, operation)
            action = registry.actionFor(name, arguments)
            action_id = action["actionId"]
            assert re.fullmatch(r"A[A-Z0-9]{5}", action_id)
            assert action_id in documented
            assert action_id not in seen, f"{name} and {seen.get(action_id)} share {action_id}"
            seen[action_id] = f"{name}(operation={operation})"


def test_every_operation_has_action_id():
    registry = create_default_registry()
    content = (Path(__file__).parents[2] / "docs" / "references" / "action-ids.md").read_text(encoding="utf-8")
    for definition in registry.definitions():
        function = definition.get("function", definition)
        name = function["name"]
        for operation in _operations_for(definition):
            assert f"`{name}(operation={operation})`" in content


def test_no_not_implemented_in_handlers():
    definitions = Path(__file__).parents[2] / "src" / "orchestrator" / "tools" / "definitions"
    for source in definitions.glob("*.py"):
        assert "NOT_IMPLEMENTED" not in source.read_text(encoding="utf-8"), source


def test_thought_id_literals_are_documented():
    project_root = Path(__file__).parents[2]
    documented = set(re.findall(
        r"`(T[A-Z0-9]{5})`",
        (project_root / "docs" / "references" / "thought-ids.md").read_text(encoding="utf-8"),
    ))
    emitted_literals = set()
    for source in (project_root / "src").glob("**/*.py"):
        emitted_literals.update(re.findall(
            r"""["'](T[A-Z0-9]{5})["']""",
            source.read_text(encoding="utf-8"),
        ))
    assert emitted_literals <= documented
