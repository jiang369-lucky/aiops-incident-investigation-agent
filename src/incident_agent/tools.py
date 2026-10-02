from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from .domain import REQUEST_PATTERN, UUID_PATTERN, InvestigationScope
from .logstore import DATASET_FILES, OpenStackLogStore
from .memory import ApprovedCaseMemory
from .runbooks import RunbookStore

ToolFunction = Callable[..., dict[str, Any]]
SAFE_ID_RE = re.compile(rf"^{UUID_PATTERN}$", re.IGNORECASE)


class ToolError(RuntimeError):
    pass


class ToolRegistry:
    """Shared tools for the default local transport and optional MCP server."""

    def __init__(
        self,
        store: OpenStackLogStore,
        runbooks: RunbookStore,
    ):
        self.store = store
        self.runbooks = runbooks
        self.memory = ApprovedCaseMemory(store.database_url)
        self._tools: dict[str, ToolFunction] = {
            "get_instance_summary": self.get_instance_summary,
            "search_logs": self.search_logs,
            "get_timeline": self.get_timeline,
            "search_runbooks": self.search_runbooks,
            "get_case_memory": self.get_case_memory,
            "validate_evidence": self.validate_evidence,
            "save_ticket_draft": self.save_ticket_draft,
        }

    @property
    def names(self) -> set[str]:
        return set(self._tools)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise ToolError(f"Unknown tool: {name}")
        if name in {"get_instance_summary", "search_logs", "get_timeline", "validate_evidence"}:
            if arguments.get("dataset", "all") != "all":
                raise ToolError("Agent tools search all log partitions; omit dataset")
            arguments = {"dataset": "all", **arguments}
        try:
            return self._tools[name](**arguments)
        except TypeError as exc:
            raise ToolError(f"Invalid arguments for {name}: {exc}") from exc

    def describe(self) -> list[dict[str, Any]]:
        definitions = [
            {
                "name": "get_instance_summary",
                "description": "Count signals only for the specified instance and operation request.",
                "arguments": {"instance_id": "uuid", "request_id": "req-uuid"},
            },
            {
                "name": "search_logs",
                "description": "Read a bounded set of matching log records.",
                "arguments": {
                    "instance_id": "uuid",
                    "request_id": "req-uuid",
                    "query": "optional text",
                    "levels": "optional list",
                    "limit": "1..100",
                },
            },
            {
                "name": "get_timeline",
                "description": "Return bounded opening and terminal events of this instance/request.",
                "arguments": {"instance_id": "uuid", "request_id": "req-uuid", "limit": "1..100"},
            },
            {
                "name": "search_runbooks",
                "description": "Retrieve ranked, citeable Runbook chunks as guidance, not incident evidence.",
                "arguments": {"query": "text", "limit": "1..5"},
            },
            {
                "name": "get_case_memory",
                "description": "Read approved drafts for the same instance/request as background only.",
                "arguments": {"instance_id": "uuid", "request_id": "req-uuid", "limit": "1..3"},
            },
            {
                "name": "validate_evidence",
                "description": "Verify citations belong to both the investigated instance and request.",
                "arguments": {
                    "instance_id": "uuid",
                    "request_id": "req-uuid",
                    "citations": "list like abnormal:11960",
                },
            },
            {
                "name": "save_ticket_draft",
                "description": "Persist a draft only after explicit human approval.",
                "arguments": {"ticket": "object", "approved": "boolean"},
            },
        ]
        schemas: dict[str, dict[str, Any]] = {
            "get_instance_summary": {
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string", "pattern": rf"^{UUID_PATTERN}$"},
                    "request_id": {"type": "string", "pattern": rf"^{REQUEST_PATTERN}$"},
                },
                "required": ["instance_id", "request_id"],
            },
            "search_logs": {
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string"},
                    "request_id": {"type": "string"},
                    "query": {"type": "string"},
                    "levels": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["instance_id", "request_id"],
            },
            "get_timeline": {
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string"},
                    "request_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["instance_id", "request_id"],
            },
            "search_runbooks": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["query"],
            },
            "get_case_memory": {
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string"},
                    "request_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["instance_id", "request_id"],
            },
            "validate_evidence": {
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string"},
                    "request_id": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["instance_id", "request_id", "citations"],
            },
            "save_ticket_draft": {
                "type": "object",
                "properties": {
                    "ticket": {"type": "object"},
                    "approved": {"type": "boolean"},
                },
                "required": ["ticket"],
            },
        }
        return [{**item, "input_schema": schemas[item["name"]]} for item in definitions]

    @staticmethod
    def _dataset(value: str) -> str:
        if value != "all" and value not in DATASET_FILES:
            raise ToolError(f"Invalid dataset: {value}")
        return value

    @staticmethod
    def _instance(value: str) -> str:
        value = value.lower()
        if not SAFE_ID_RE.fullmatch(value):
            raise ToolError("instance_id must be a UUID")
        return value

    @staticmethod
    def _scope(instance_id: str, request_id: str) -> InvestigationScope:
        try:
            return InvestigationScope(instance_id, request_id)
        except (ValueError, TypeError) as exc:
            raise ToolError(str(exc)) from exc

    def get_instance_summary(self, dataset: str, instance_id: str, request_id: str) -> dict[str, Any]:
        scope = self._scope(instance_id, request_id)
        return self.store.instance_summary(
            dataset=self._dataset(dataset), instance_id=scope.instance_id, request_id=scope.request_id
        )

    def search_logs(
        self,
        dataset: str,
        instance_id: str,
        request_id: str,
        query: str | None = None,
        levels: list[str] | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        scope = self._scope(instance_id, request_id)
        records = self.store.search(
            dataset=self._dataset(dataset),
            instance_id=scope.instance_id,
            request_id=scope.request_id,
            query=query,
            levels=levels,
            limit=limit,
        )
        return {
            "instance_id": scope.instance_id,
            "request_id": scope.request_id,
            "count": len(records),
            "records": [self._record(record) for record in records],
            "truncated": len(records) == min(max(int(limit), 1), 100),
        }

    def get_timeline(
        self, dataset: str, instance_id: str, request_id: str, limit: int = 80
    ) -> dict[str, Any]:
        scope = self._scope(instance_id, request_id)
        records = self.store.timeline(
            dataset=self._dataset(dataset),
            instance_id=scope.instance_id,
            request_id=scope.request_id,
            limit=min(max(int(limit), 1), 100),
        )
        return {
            "instance_id": scope.instance_id, "request_id": scope.request_id,
            "count": len(records), "selection": "head_and_tail",
            "possibly_truncated": len(records) == min(max(int(limit), 1), 100),
            "events": [self._record(record) for record in records],
        }

    def search_runbooks(self, query: str, limit: int = 3) -> dict[str, Any]:
        if not query.strip():
            raise ToolError("query must not be empty")
        matches = self.runbooks.search(query, limit=min(max(int(limit), 1), 5))
        return {"count": len(matches), "matches": matches}

    def get_case_memory(self, instance_id: str, request_id: str, limit: int = 2) -> dict[str, Any]:
        scope = self._scope(instance_id, request_id)
        cases = self.memory.recent(scope.instance_id, scope.request_id, limit)
        return {
            "instance_id": scope.instance_id,
            "request_id": scope.request_id,
            "count": len(cases),
            "cases": cases,
            "warning": "Past approved drafts are background, not evidence about the current run.",
        }

    def validate_evidence(
        self, dataset: str, instance_id: str, request_id: str, citations: list[str]
    ) -> dict[str, Any]:
        dataset = self._dataset(dataset)
        scope = self._scope(instance_id, request_id)
        if len(citations) > 30:
            raise ToolError("At most 30 citations can be validated per call")
        details: list[dict[str, Any]] = []
        for citation in citations:
            record = self.store.record_by_citation(citation)
            valid = bool(
                record
                and (dataset == "all" or record.dataset == dataset)
                and record.instance_id == scope.instance_id
                and record.request_id == scope.request_id
            )
            details.append(
                {
                    "citation": citation,
                    "valid": valid,
                    "reason": "matched instance and request" if valid else "missing or wrong instance/request",
                }
            )
        return {
            "instance_id": scope.instance_id,
            "request_id": scope.request_id,
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
        scope = self._scope(str(ticket.get("instance_id", "")), str(ticket.get("request_id", "")))
        saved = self.memory.save_approved(scope.instance_id, scope.request_id, ticket)
        return {"saved": True, **saved, "requires_approval": False}

    @staticmethod
    def _record(record: Any) -> dict[str, Any]:
        value = asdict(record)
        value["citation"] = record.citation()
        value.pop("raw", None)
        return value
