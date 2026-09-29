from __future__ import annotations

from pathlib import Path

import pytest

from incident_agent.domain import ToolAction
from incident_agent.harness import AgentHarness, HarnessConfig
from incident_agent.policies import HeuristicInvestigatorPolicy
from incident_agent.skills import Skill
from incident_agent.tools import ToolRegistry

INSTANCE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.mark.asyncio
async def test_end_to_end_harness_returns_grounded_report(
    registry: ToolRegistry, tmp_path: Path
) -> None:
    skills = [Skill("test", "test skill", "cite evidence", tmp_path / "SKILL.md")]
    harness = AgentHarness(
        HeuristicInvestigatorPolicy(skills),
        registry,
        tmp_path / "traces",
        HarnessConfig(max_steps=8),
    )
    result = await harness.run(f"Investigate {INSTANCE}; dataset=abnormal")
    assert result.status == "completed"
    assert result.report is not None
    assert result.report.verdict == "anomalous"
    assert result.report.evidence == ["abnormal:1"]
    assert result.report.requires_human_review is True


class RepeatingPolicy:
    async def next_action(self, task, observations, step):
        return ToolAction(
            "get_instance_summary",
            {"dataset": "abnormal", "instance_id": INSTANCE},
            "repeat",
        )


@pytest.mark.asyncio
async def test_harness_breaks_repeated_tool_loop(registry: ToolRegistry, tmp_path: Path) -> None:
    harness = AgentHarness(
        RepeatingPolicy(),
        registry,
        tmp_path / "traces",
        HarnessConfig(max_steps=8, max_repeated_call=1),
    )
    result = await harness.run("loop test")
    assert result.status == "blocked"
    assert "Repeated identical tool call" in (result.error or "")
