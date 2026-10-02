from collections.abc import Iterator
from typing import Self

from incident_agent.logstore import OpenStackLogStore

INSTANCE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
REQUEST = "req-11111111-1111-1111-1111-111111111111"


class FakeConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, object]] = []
        self.rows: list[dict[str, object]] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, parameters: object) -> Self:
        self.queries.append((query, parameters))
        self.rows = [
            {
                "id": index,
                "dataset": dataset,
                "line_no": 1,
                "timestamp": f"2017-05-14T21:08:1{index}.000",
                "source": "nova-compute.log",
                "level": "INFO",
                "logger": "nova.compute.manager",
                "request_id": REQUEST,
                "instance_id": INSTANCE,
                "message": "Instance spawned successfully",
                "raw": "Instance spawned successfully",
            }
            for index, dataset in enumerate(("normal1", "normal2"), start=1)
        ]
        return self

    def __iter__(self) -> Iterator[dict[str, object]]:
        return iter(self.rows)

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


def test_store_global_search_and_summary_do_not_filter_dataset(monkeypatch) -> None:
    store = OpenStackLogStore("unused")
    connection = FakeConnection()
    monkeypatch.setattr(store, "_connect", lambda: connection)
    store._duration_baseline = {"sample_count": 0, "p95_seconds": 0.0}

    records = store.search(dataset="all", instance_id=INSTANCE, request_id=REQUEST)
    summary = store.instance_summary(dataset="all", instance_id=INSTANCE, request_id=REQUEST)

    assert {record.citation() for record in records} == {"normal1:1", "normal2:1"}
    assert summary["total_records"] == 2
    assert summary["matched_datasets"] == ["normal1", "normal2"]
    assert all("dataset = %s" not in query for query, _ in connection.queries)
    assert all("request_id = %s" in query for query, _ in connection.queries)
    assert connection.queries[0][1] == [INSTANCE, REQUEST, 30]
    assert connection.queries[1][1] == (INSTANCE, REQUEST)
