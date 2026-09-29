from incident_agent.tools import ToolRegistry

INSTANCE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


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
