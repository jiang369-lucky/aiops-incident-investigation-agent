from incident_agent.api import InvestigationRequest
from incident_agent.cli import _parser

INSTANCE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
REQUEST = "req-11111111-1111-1111-1111-111111111111"


def test_cli_investigate_defaults_to_latest_request() -> None:
    arguments = _parser().parse_args(["investigate", INSTANCE])
    assert arguments.instance_id == INSTANCE
    assert arguments.request_id is None
    assert not hasattr(arguments, "dataset")


def test_api_request_defaults_to_latest_request() -> None:
    request = InvestigationRequest(instance_id=INSTANCE)
    assert request.instance_id == INSTANCE
    assert request.request_id is None
    assert "dataset" not in InvestigationRequest.model_fields


def test_entrypoints_accept_explicit_request_id() -> None:
    arguments = _parser().parse_args(["investigate", INSTANCE, REQUEST])
    request = InvestigationRequest(instance_id=INSTANCE, request_id=REQUEST)
    assert arguments.request_id == request.request_id == REQUEST
