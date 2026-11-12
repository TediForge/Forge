from pathlib import Path

from src.tools.registry import create_default_registry


ROOT = Path(__file__).resolve().parents[2]


def test_todo_and_memory_are_not_registered():
    names = set(create_default_registry().names())

    assert "todo" not in names
    assert "memory" not in names


def test_state_store_module_and_imports_are_absent():
    assert not (ROOT / "src" / "tools" / "state_store.py").exists()
    for source in (ROOT / "src").rglob("*.py"):
        assert "state_store" not in source.read_text(encoding="utf-8"), source
