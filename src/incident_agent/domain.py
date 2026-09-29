from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

Verdict = Literal["anomalous", "normal", "uncertain"]


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


@dataclass(slots=True)
class IncidentReport:
    instance_id: str
    dataset: str
    verdict: Verdict
    confidence: float
    summary: str
    hypothesis: str
    evidence: list[str]
    counterevidence: list[str]
    recommended_actions: list[str]
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
