from pathlib import Path

import pytest

from incident_agent.logstore import OpenStackLogStore
from incident_agent.tools import ToolError, ToolRegistry

INSTANCE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MULTI_PARTITION_INSTANCE = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_tools_return_citations_but_not_evaluation_labels(registry: ToolRegistry) -> None:
    result = registry.get_timeline("abnormal", INSTANCE, limit=10)
    assert result["count"] == 2
    assert result["events"][0]["citation"] == "abnormal:1"
    assert "expected_anomalous" not in str(result)
    assert "anomaly_labels" not in str(result)


def test_ticket_requires_human_approval(registry: ToolRegistry) -> None:
    ticket = {"instance_id": INSTANCE, "summary": "draft"}
    denied = registry.save_ticket_draft(ticket, approved=False)
    assert denied["saved"] is False
    assert denied["requires_approval"] is True


def test_evidence_validation_rejects_wrong_instance(registry: ToolRegistry) -> None:
    valid = registry.validate_evidence("abnormal", INSTANCE, ["abnormal:1"])
    invalid = registry.validate_evidence(
        "abnormal", "cccccccc-cccc-cccc-cccc-cccccccccccc", ["abnormal:1"]
    )
    assert valid["all_valid"] is True
    assert invalid["all_valid"] is False


def test_global_lookup_combines_partitions_and_keeps_source_citations(
    registry: ToolRegistry,
) -> None:
    summary = registry.call(
        "get_instance_summary", {"instance_id": MULTI_PARTITION_INSTANCE}
    )
    timeline = registry.call("get_timeline", {"instance_id": MULTI_PARTITION_INSTANCE})
    assert summary["total_records"] == 2
    assert summary["matched_datasets"] == ["normal1", "normal2"]
    assert {event["citation"] for event in timeline["events"]} == {"normal1:1", "normal2:1"}
    assert registry.call(
        "validate_evidence",
        {
            "instance_id": MULTI_PARTITION_INSTANCE,
            "citations": ["normal1:1", "normal2:1"],
        },
    )["all_valid"] is True


def test_agent_tool_rejects_partition_specific_lookup(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="search all log partitions"):
        registry.call(
            "get_instance_summary", {"dataset": "abnormal", "instance_id": INSTANCE}
        )


def test_postgres_import_is_idempotent(indexed_store: OpenStackLogStore, tmp_path: Path) -> None:
    expected = {"abnormal": 2, "normal1": 1, "normal2": 1}
    assert indexed_store.build(tmp_path / "raw") == expected
    assert indexed_store.build(tmp_path / "raw", force=True) == expected
    assert indexed_store.is_ready() is True
    assert len(indexed_store.search(dataset="abnormal", instance_id=INSTANCE)) == 2
