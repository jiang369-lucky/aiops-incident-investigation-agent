from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .logstore import DATASET_FILES, OpenStackLogStore
from .runbooks import RunbookStore

ToolFunction = Callable[..., dict[str, Any]]
SAFE_ID_RE = re.compile(r"^[0-9a-f-]{36}$", re.IGNORECASE)


class ToolError(RuntimeError):
    pass


class ToolRegistry:
    """Single seam shared by the agent harness, FastAPI adapter, and MCP adapter."""

    def __init__(
        self,
        store: OpenStackLogStore,
        runbooks: RunbookStore,
        tickets_path: Path,
    ):
        self.store = store
        self.runbooks = runbooks
        self.tickets_path = Path(tickets_path)
        self._tools: dict[str, ToolFunction] = {
            "get_instance_summary": self.get_instance_summary,
            "search_logs": self.search_logs,
            "get_timeline": self.get_timeline,
            "search_runbooks": self.search_runbooks,
            "validate_evidence": self.validate_evidence,
            "save_ticket_draft": self.save_ticket_draft,
        }

    @property
    def names(self) -> set[str]:
        return set(self._tools)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise ToolError(f"Unknown tool: {name}")
        try:
            return self._tools[name](**arguments)
        except TypeError as exc:
            raise ToolError(f"Invalid arguments for {name}: {exc}") from exc

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "get_instance_summary",
                "description": "Count levels and suspicious signals for one VM instance.",
                "arguments": {"dataset": "abnormal|normal1|normal2", "instance_id": "uuid"},
            },
            {
                "name": "search_logs",
                "description": "Read a bounded set of matching log records.",
                "arguments": {
                    "dataset": "abnormal|normal1|normal2",
                    "instance_id": "optional uuid",
                    "request_id": "optional req-uuid",
                    "query": "optional text",
                    "levels": "optional list",
                    "limit": "1..100",
                },
            },
            {
                "name": "get_timeline",
                "description": "Return chronological events for one VM instance.",
                "arguments": {"dataset": "dataset", "instance_id": "uuid", "limit": "1..100"},
            },
            {
                "name": "search_runbooks",
                "description": "Retrieve operating guidance. Runbooks are advice, not evidence.",
                "arguments": {"query": "text", "limit": "1..5"},
            },
            {
                "name": "validate_evidence",
                "description": "Verify that citations exist and refer to the investigated instance.",
                "arguments": {
                    "dataset": "dataset",
                    "instance_id": "uuid",
                    "citations": "list like abnormal:11960",
                },
            },
            {
                "name": "save_ticket_draft",
                "description": "Persist a draft only after explicit human approval.",
                "arguments": {"ticket": "object", "approved": "boolean"},
            },
        ]

    @staticmethod
    def _dataset(value: str) -> str:
        if value not in DATASET_FILES:
            raise ToolError(f"Invalid dataset: {value}")
        return value

    @staticmethod
    def _instance(value: str) -> str:
        value = value.lower()
        if not SAFE_ID_RE.fullmatch(value):
            raise ToolError("instance_id must be a UUID")
        return value

    def get_instance_summary(self, dataset: str, instance_id: str) -> dict[str, Any]:
        return self.store.instance_summary(
            dataset=self._dataset(dataset), instance_id=self._instance(instance_id)
        )

    def search_logs(
        self,
        dataset: str,
        instance_id: str | None = None,
        request_id: str | None = None,
        query: str | None = None,
        levels: list[str] | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        if instance_id:
            instance_id = self._instance(instance_id)
        records = self.store.search(
            dataset=self._dataset(dataset),
            instance_id=instance_id,
            request_id=request_id,
            query=query,
            levels=levels,
            limit=limit,
        )
        return {
            "count": len(records),
            "records": [self._record(record) for record in records],
            "truncated": len(records) == min(max(int(limit), 1), 100),
        }

    def get_timeline(self, dataset: str, instance_id: str, limit: int = 80) -> dict[str, Any]:
        records = self.store.timeline(
            dataset=self._dataset(dataset),
            instance_id=self._instance(instance_id),
            limit=min(max(int(limit), 1), 100),
        )
        return {"count": len(records), "events": [self._record(record) for record in records]}

    def search_runbooks(self, query: str, limit: int = 3) -> dict[str, Any]:
        if not query.strip():
            raise ToolError("query must not be empty")
        matches = self.runbooks.search(query, limit=min(max(int(limit), 1), 5))
        return {"count": len(matches), "matches": matches}

    def validate_evidence(
        self, dataset: str, instance_id: str, citations: list[str]
    ) -> dict[str, Any]:
        dataset = self._dataset(dataset)
        instance_id = self._instance(instance_id)
        if len(citations) > 30:
            raise ToolError("At most 30 citations can be validated per call")
        details: list[dict[str, Any]] = []
        for citation in citations:
            record = self.store.record_by_citation(citation)
            valid = bool(
                record
                and record.dataset == dataset
                and (record.instance_id == instance_id or instance_id in record.raw.lower())
            )
            details.append(
                {
                    "citation": citation,
                    "valid": valid,
                    "reason": "matched instance" if valid else "missing or wrong instance",
                }
            )
        return {
            "all_valid": bool(details) and all(item["valid"] for item in details),
            "valid_count": sum(bool(item["valid"]) for item in details),
            "details": details,
        }

    def save_ticket_draft(self, ticket: dict[str, Any], approved: bool = False) -> dict[str, Any]:
        if not approved:
            return {
                "saved": False,
                "requires_approval": True,
                "message": "Human approval is required before writing a ticket draft.",
            }
        instance_id = self._instance(str(ticket.get("instance_id", "")))
        self.tickets_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output = self.tickets_path / f"{timestamp}-{instance_id}.json"
        output.write_text(json.dumps(ticket, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"saved": True, "path": str(output), "requires_approval": False}

    @staticmethod
    def _record(record: Any) -> dict[str, Any]:
        value = asdict(record)
        value["citation"] = record.citation()
        value.pop("raw", None)
        return value
