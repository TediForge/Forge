"""Load and validate categorized Markdown skills."""

import re
from pathlib import Path
from typing import Any

import yaml


SKILLS_ROOT = Path(__file__).resolve().parent
_CATEGORIES = {"tools": "tool", "agents": "agent", "general": "general"}


def _splitFrontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise ValueError("Skill must start with YAML frontmatter")
    frontmatter, separator, body = text[4:].partition("\n---")
    if not separator:
        raise ValueError("Skill YAML frontmatter is not closed")
    try:
        metadata = yaml.safe_load(frontmatter)
    except yaml.YAMLError as exc:
        raise ValueError("Skill YAML frontmatter is malformed") from exc
    if not isinstance(metadata, dict):
        raise ValueError("Skill frontmatter must be a YAML mapping")
    return metadata, body.lstrip()


def loadSkillMeta(name: str, category: str) -> dict[str, Any]:
    if re.fullmatch(r"[a-z][a-z0-9]*", name) is None:
        raise ValueError(f"Invalid skill name: {name}")
    if category not in _CATEGORIES:
        raise ValueError(f"Unknown skill category: {category}")
    path = SKILLS_ROOT / category / name / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"Skill not found: {category}/{name}")
    metadata, _ = _splitFrontmatter(path.read_text(encoding="utf-8"))
    expected_category = _CATEGORIES[category]
    if metadata.get("name") != name or metadata.get("category") != expected_category:
        raise ValueError(f"Skill frontmatter identity does not match {category}/{name}")
    if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
        raise ValueError(f"Skill description is missing: {category}/{name}")
    return metadata


def loadSkillBody(name: str, category: str) -> str:
    loadSkillMeta(name, category)
    path = SKILLS_ROOT / category / name / "SKILL.md"
    _, body = _splitFrontmatter(path.read_text(encoding="utf-8"))
    return body


def loadAgentSkill(name: str) -> str:
    return loadSkillBody(name, "agents")
