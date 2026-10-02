from pathlib import Path

import pytest

from incident_agent.logstore import OpenStackLogStore
from incident_agent.tools import ToolError, ToolRegistry

INSTANCE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
REQUEST = "req-11111111-1111-1111-1111-111111111111"
MULTI_PARTITION_INSTANCE = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
MULTI_PARTITION_REQUEST = "req-33333333-3333-3333-3333-333333333333"


def test_tools_return_citations_but_not_evaluation_labels(registry: ToolRegistry) -> None:
    result = registry.get_timeline("abnormal", INSTANCE, REQUEST, limit=10)
    assert result["count"] == 2
    assert result["events"][0]["citation"] == "abnormal:1"
    assert "expected_anomalous" not in str(result)
    assert "anomaly_labels" not in str(result)


def test_ticket_requires_human_approval(registry: ToolRegistry) -> None:
    ticket = {"instance_id": INSTANCE, "request_id": REQUEST, "summary": "draft"}
    denied = registry.save_ticket_draft(ticket, approved=False)
    assert denied["saved"] is False
    assert denied["requires_approval"] is True


def test_evidence_validation_rejects_wrong_instance(registry: ToolRegistry) -> None:
    valid = registry.validate_evidence("abnormal", INSTANCE, REQUEST, ["abnormal:1"])
    invalid = registry.validate_evidence(
        "abnormal", "cccccccc-cccc-cccc-cccc-cccccccccccc", REQUEST, ["abnormal:1"]
    )
    assert valid["all_valid"] is True
    assert invalid["all_valid"] is False


def test_global_lookup_combines_partitions_and_keeps_source_citations(
    registry: ToolRegistry,
) -> None:
    summary = registry.call(
        "get_instance_summary",
        {"instance_id": MULTI_PARTITION_INSTANCE, "request_id": MULTI_PARTITION_REQUEST},
    )
    timeline = registry.call(
        "get_timeline", {"instance_id": MULTI_PARTITION_INSTANCE, "request_id": MULTI_PARTITION_REQUEST}
    )
    assert summary["total_records"] == 2
    assert summary["matched_datasets"] == ["normal1", "normal2"]
    assert {event["citation"] for event in timeline["events"]} == {"normal1:1", "normal2:1"}
    assert registry.call(
        "validate_evidence",
        {
            "instance_id": MULTI_PARTITION_INSTANCE,
            "request_id": MULTI_PARTITION_REQUEST,
            "citations": ["normal1:1", "normal2:1"],
        },
    )["all_valid"] is True


def test_agent_tool_rejects_partition_specific_lookup(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="search all log partitions"):
        registry.call(
            "get_instance_summary", {"dataset": "abnormal", "instance_id": INSTANCE, "request_id": REQUEST}
        )


def test_postgres_import_is_idempotent(indexed_store: OpenStackLogStore, tmp_path: Path) -> None:
    expected = {"abnormal": 3, "normal1": 1, "normal2": 1}
    assert indexed_store.build(tmp_path / "raw") == expected
    assert indexed_store.build(tmp_path / "raw", force=True) == expected
    assert indexed_store.is_ready() is True
    assert len(indexed_store.search(dataset="abnormal", instance_id=INSTANCE, request_id=REQUEST)) == 2


def test_request_scope_excludes_other_operations(registry: ToolRegistry) -> None:
    summary = registry.call("get_instance_summary", {"instance_id": INSTANCE, "request_id": REQUEST})
    assert summary["total_records"] == 2
    assert summary["level_counts"]["ERROR"] == 1
    check = registry.validate_evidence("all", INSTANCE, REQUEST, ["abnormal:3"])
    assert check["all_valid"] is False


def test_scoped_tools_require_request_id(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="Invalid arguments"):
        registry.call("get_instance_summary", {"instance_id": INSTANCE})
