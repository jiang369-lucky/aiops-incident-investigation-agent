from __future__ import annotations

from pathlib import Path

import pytest

from incident_agent.logstore import OpenStackLogStore
from incident_agent.runbooks import RunbookStore
from incident_agent.tools import ToolRegistry


@pytest.fixture()
def indexed_store(tmp_path: Path) -> OpenStackLogStore:
    raw = tmp_path / "raw"
    raw.mkdir()
    abnormal = "nova-compute.log 2017-05-14 21:08:12.571 2931 ERROR nova.compute.manager [req-11111111-1111-1111-1111-111111111111 - - - - -] [instance: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa] VM Stopped unexpectedly\nnova-compute.log 2017-05-14 21:08:19.735 2931 INFO nova.virt.driver [-] [instance: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa] Instance spawned successfully."
    normal = (
        "nova-compute.log 2017-05-14 21:08:19.735 2931 INFO nova.virt.driver "
        "[-] [instance: bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb] Instance spawned successfully.\n"
    )
    (raw / "openstack_abnormal.log").write_text(abnormal, encoding="utf-8")
    (raw / "openstack_normal1.log").write_text(normal, encoding="utf-8")
    (raw / "openstack_normal2.log").write_text(normal, encoding="utf-8")
    store = OpenStackLogStore(tmp_path / "logs.db")
    store.build(raw)
    return store


@pytest.fixture()
def registry(indexed_store: OpenStackLogStore, tmp_path: Path) -> ToolRegistry:
    runbooks = tmp_path / "runbooks"
    runbooks.mkdir()
    (runbooks / "vm.md").write_text(
        "# VM stopped\nInvestigate VM stopped lifecycle", encoding="utf-8"
    )
    return ToolRegistry(indexed_store, RunbookStore(runbooks), tmp_path / "tickets")
