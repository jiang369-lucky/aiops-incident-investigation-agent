from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    instructions: str
    path: Path


class SkillCatalog:
    """Loads reusable operating procedures without coupling the harness to files."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def load(self, names: list[str] | None = None) -> list[Skill]:
        selected = set(names or [])
        skills: list[Skill] = []
        for path in sorted(self.root.glob("*/SKILL.md")):
            skill = self._parse(path)
            if not selected or skill.name in selected:
                skills.append(skill)
        missing = selected - {skill.name for skill in skills}
        if missing:
            raise KeyError(f"Unknown skills: {', '.join(sorted(missing))}")
        return skills

    @staticmethod
    def _parse(path: Path) -> Skill:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise ValueError(f"Skill front matter missing: {path}")
        _, header, body = text.split("---", 2)
        fields: dict[str, str] = {}
        for line in header.splitlines():
            match = re.match(r"^([a-z_]+):\s*(.*)$", line.strip())
            if match:
                fields[match.group(1)] = match.group(2).strip().strip('"')
        if not fields.get("name") or not fields.get("description"):
            raise ValueError(f"Skill name/description missing: {path}")
        return Skill(
            name=fields["name"],
            description=fields["description"],
            instructions=body.strip(),
            path=path,
        )

    @staticmethod
    def prompt_text(skills: list[Skill]) -> str:
        return "\n\n".join(
            f"## Skill: {skill.name}\n{skill.description}\n{skill.instructions}" for skill in skills
        )
