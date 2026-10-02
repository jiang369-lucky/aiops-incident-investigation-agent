from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from incident_agent.logstore import OpenStackLogStore
from incident_agent.runbooks import RunbookStore
from incident_agent.tools import ToolRegistry


@pytest.fixture()
def indexed_store(tmp_path: Path) -> Iterator[OpenStackLogStore]:
    test_url = os.getenv("PG_TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("Set PG_TEST_DATABASE_URL to run PostgreSQL integration tests")
    schema = f"test_{uuid.uuid4().hex}"
    with psycopg.connect(test_url) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    raw = tmp_path / "raw"
    raw.mkdir()
    abnormal = (
        "nova-compute.log 2017-05-14 21:08:12.571 2931 ERROR nova.compute.manager "
        "[req-11111111-1111-1111-1111-111111111111 - - - - -] "
        "[instance: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa] VM Stopped unexpectedly\n"
        "nova-compute.log 2017-05-14 21:08:19.735 2931 INFO nova.virt.driver "
        "[req-11111111-1111-1111-1111-111111111111 - - - - -] "
        "[instance: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa] Instance spawned successfully.\n"
        "nova-compute.log 2017-05-14 22:08:12.571 2931 ERROR nova.compute.manager "
        "[req-22222222-2222-2222-2222-222222222222 - - - - -] "
        "[instance: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa] Failure in another request\n"
    )
    normal = (
        "nova-compute.log 2017-05-14 21:08:19.735 2931 INFO nova.virt.driver "
        "[req-33333333-3333-3333-3333-333333333333 - - - - -] "
        "[instance: bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb] Instance spawned successfully.\n"
    )
    (raw / "openstack_abnormal.log").write_text(abnormal, encoding="utf-8")
    (raw / "openstack_normal1.log").write_text(normal, encoding="utf-8")
    (raw / "openstack_normal2.log").write_text(normal, encoding="utf-8")
    store = OpenStackLogStore(make_conninfo(test_url, options=f"-c search_path={schema}"))
    try:
        store.build(raw)
        yield store
    finally:
        with psycopg.connect(test_url) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture()
def registry(indexed_store: OpenStackLogStore, tmp_path: Path) -> ToolRegistry:
    runbooks = tmp_path / "runbooks"
    runbooks.mkdir()
    (runbooks / "vm.md").write_text(
        "# VM stopped\nInvestigate VM stopped lifecycle", encoding="utf-8"
    )
    return ToolRegistry(indexed_store, RunbookStore(runbooks))
