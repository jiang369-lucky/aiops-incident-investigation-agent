from __future__ import annotations

from pathlib import Path

import pytest

from incident_agent.domain import ToolAction
from incident_agent.harness import AgentHarness, HarnessConfig
from incident_agent.policies import HeuristicInvestigatorPolicy, parse_task
from incident_agent.skills import Skill
from incident_agent.tools import ToolRegistry

INSTANCE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
REQUEST = "req-11111111-1111-1111-1111-111111111111"
TASK = f"Investigate instance {INSTANCE} for request {REQUEST}"


def test_task_locks_instance_and_request_without_dataset() -> None:
    assert parse_task(TASK) == ("all", INSTANCE, REQUEST)
    assert parse_task(f"{TASK}; dataset=abnormal") == ("all", INSTANCE, REQUEST)
    with pytest.raises(ValueError, match="explicitly name"):
        parse_task(f"Investigate instance {INSTANCE}")


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
    result = await harness.run(TASK)
    assert result.status == "completed"
    assert result.report is not None
    assert result.report.verdict == "anomalous"
    assert result.report.dataset == "all"
    assert result.report.request_id == REQUEST
    assert result.report.evidence == ["abnormal:1"]
    assert result.report.counterevidence == ["abnormal:2"]
    assert result.report.requires_human_review is True


class RepeatingPolicy:
    async def next_action(self, task, observations, step):
        return ToolAction(
            "get_instance_summary",
            {"instance_id": INSTANCE, "request_id": REQUEST},
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
    result = await harness.run(TASK)
    assert result.status == "blocked"
    assert "Repeated identical tool call" in (result.error or "")


class CrossRequestPolicy:
    async def next_action(self, task, observations, step):
        return ToolAction(
            "search_logs",
            {"instance_id": INSTANCE, "request_id": "req-22222222-2222-2222-2222-222222222222"},
            "attempt to widen the operation scope",
        )


@pytest.mark.asyncio
async def test_harness_blocks_switching_requests(registry: ToolRegistry, tmp_path: Path) -> None:
    harness = AgentHarness(CrossRequestPolicy(), registry, tmp_path / "traces")
    result = await harness.run(TASK)
    assert result.status == "blocked"
    assert "locked instance/request scope" in (result.error or "")
    assert result.observations == []
