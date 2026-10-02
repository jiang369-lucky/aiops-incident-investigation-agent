from incident_agent.api import InvestigationRequest
from incident_agent.cli import _parser

INSTANCE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_cli_investigate_needs_only_instance_id() -> None:
    arguments = _parser().parse_args(["investigate", INSTANCE])
    assert arguments.instance_id == INSTANCE
    assert not hasattr(arguments, "dataset")


def test_api_request_needs_only_instance_id() -> None:
    request = InvestigationRequest(instance_id=INSTANCE)
    assert request.instance_id == INSTANCE
    assert "dataset" not in InvestigationRequest.model_fields
