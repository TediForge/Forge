import re
from pathlib import Path


DOCS = Path(__file__).resolve().parents[2] / "docs"


def _indexed_files(section: str, folder: str) -> set[str]:
    content = (DOCS / "README.md").read_text(encoding="utf-8")
    match = re.search(
        rf"^## {section}\s*$([\s\S]*?)(?=^## |\Z)",
        content,
        flags=re.MULTILINE,
    )
    assert match is not None, f"Missing {section} index"
    return set(re.findall(rf"\]\(\./{folder}/([^)\s]+\.md)\)", match.group(1)))


def test_decision_and_research_indexes_match_documents():
    for folder, section in (("decisions", "Decisions"), ("research", "Research")):
        indexed = _indexed_files(section, folder)
        actual = {path.name for path in (DOCS / folder).glob("*.md")}
        assert indexed == actual
        assert all((DOCS / folder / name).is_file() for name in indexed)
        numbers = [int(re.match(r"[DR]-(\d{3})-", name).group(1)) for name in indexed]
        assert len(numbers) == len(set(numbers))
