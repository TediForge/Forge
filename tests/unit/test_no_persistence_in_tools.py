import re
from pathlib import Path


DEFINITIONS = (
    Path(__file__).resolve().parents[2]
    / "src" / "orchestrator" / "tools" / "definitions"
)
PERSISTENCE_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(?:sqlite3|redis|psycopg|sqlalchemy)\b",
    re.MULTILINE,
)


def test_tools_do_not_import_persistence_libraries():
    for source in DEFINITIONS.glob("*.py"):
        if source.name == "data.py":
            continue
        assert not PERSISTENCE_IMPORT.search(source.read_text(encoding="utf-8")), source.name
