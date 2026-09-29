from pathlib import Path

from incident_agent.skills import SkillCatalog


def test_skill_catalog_loads_front_matter(tmp_path: Path) -> None:
    path = tmp_path / "triage"
    path.mkdir()
    (path / "SKILL.md").write_text(
        "---\nname: triage\ndescription: Triage logs\n---\n\nUse evidence.",
        encoding="utf-8",
    )
    skill = SkillCatalog(tmp_path).load(["triage"])[0]
    assert skill.name == "triage"
    assert "evidence" in skill.instructions
