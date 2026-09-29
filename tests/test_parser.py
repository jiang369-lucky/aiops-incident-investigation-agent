from incident_agent.parser import parse_openstack_line


def test_parse_openstack_line_extracts_identity() -> None:
    parsed = parse_openstack_line(
        "nova-compute.log 2017-05-14 21:08:12.571 2931 WARNING nova.compute.manager "
        "[req-11111111-1111-1111-1111-111111111111 - - - - -] "
        "[instance: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa] VM Paused"
    )
    assert parsed.timestamp == "2017-05-14T21:08:12.571"
    assert parsed.level == "WARNING"
    assert parsed.request_id == "req-11111111-1111-1111-1111-111111111111"
    assert parsed.instance_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
