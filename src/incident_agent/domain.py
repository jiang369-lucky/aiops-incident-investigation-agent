from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

Verdict = Literal["anomalous", "normal", "uncertain"]
UUID_PATTERN = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
REQUEST_PATTERN = rf"req-{UUID_PATTERN}"


class ScopeResolutionError(ValueError):
    """A request cannot be resolved safely from the supplied identifiers."""


def normalize_instance_id(value: str) -> str:
    if not re.fullmatch(UUID_PATTERN, value):
        raise ScopeResolutionError("instance_id must be a UUID")
    return value.lower()


def normalize_request_id(value: str) -> str:
    if not re.fullmatch(REQUEST_PATTERN, value, re.IGNORECASE):
        raise ScopeResolutionError("request_id must have the form req-<UUID>")
    return value.lower()


@dataclass(frozen=True, slots=True)
class InvestigationScope:
    """An immutable instance/request boundary shared by entrypoints and the harness."""

    instance_id: str
    request_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", normalize_instance_id(self.instance_id))
        object.__setattr__(self, "request_id", normalize_request_id(self.request_id))

    @classmethod
    def from_task(cls, task: str) -> InvestigationScope:
        instance = re.search(rf"\binstance(?:_id)?\s*[=:]?\s*({UUID_PATTERN})\b", task, re.IGNORECASE)
        request = re.search(rf"\brequest(?:_id)?\s*[=:]?\s*({REQUEST_PATTERN})\b", task, re.IGNORECASE)
        if not instance or not request:
            raise ValueError("Task must explicitly name an instance UUID and request ID")
        return cls(instance.group(1), request.group(1))

    def task(self) -> str:
        return (
            f"Investigate OpenStack instance {self.instance_id} for request {self.request_id}. "
            "Produce an evidence-grounded report for this request only and do not take remediation action."
        )


@dataclass(frozen=True, slots=True)
class LogRecord:
    id: int
    dataset: str
    line_no: int
    timestamp: str | None
    source: str
    level: str
    logger: str
    request_id: str | None
    instance_id: str | None
    message: str
    raw: str

    def citation(self) -> str:
        return f"{self.dataset}:{self.line_no}"


@dataclass(frozen=True, slots=True)
class ToolAction:
    tool: str
    arguments: dict[str, Any]
    reason: str


@dataclass(frozen=True, slots=True)
class FinishAction:
    report: IncidentReport


AgentAction = ToolAction | FinishAction


@dataclass(slots=True)
class Observation:
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    latency_ms: float
    attempt: int


def validated_log_citations(observations: list[Observation]) -> list[str]:
    """Accumulate validation calls; the latest check wins for each citation."""
    checks: dict[str, bool] = {}
    for observation in observations:
        if observation.tool == "validate_evidence":
            for detail in observation.result.get("details", []):
                if detail.get("citation"):
                    checks[str(detail["citation"])] = bool(detail.get("valid"))
    return [citation for citation, valid in checks.items() if valid]


@dataclass(slots=True)
class IncidentReport:
    instance_id: str
    request_id: str
    dataset: str
    verdict: Verdict
    confidence: float
    summary: str
    hypothesis: str
    evidence: list[str]
    counterevidence: list[str]
    recommended_actions: list[str]
    runbook_sources: list[str] = field(default_factory=list)
    requires_human_review: bool = True
    limitations: list[str] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunResult:
    run_id: str
    status: Literal["completed", "failed", "timed_out", "blocked"]
    report: IncidentReport | None
    observations: list[Observation]
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["report"] = self.report.to_dict() if self.report else None
        return value
