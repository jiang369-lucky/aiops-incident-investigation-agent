from __future__ import annotations

import asyncio
import json
import re
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .application import Application
from .domain import InvestigationScope

UUID_RE = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class EvalCase:
    dataset: str
    instance_id: str
    expected_anomalous: bool


def load_anomaly_labels(path: Path) -> set[str]:
    text = Path(path).read_text(encoding="utf-8")
    return {match.group(0).lower() for match in UUID_RE.finditer(text)}


def build_cases(application: Application, negative_count: int = 50) -> list[EvalCase]:
    labels = load_anomaly_labels(application.settings.raw_data_path / "anomaly_labels.txt")
    cases = [EvalCase("abnormal", instance_id, True) for instance_id in sorted(labels)]
    # normal1 calibrates the latency baseline; normal2 is held out for negative evaluation.
    candidates = application.store.instance_ids(dataset="normal2")
    for instance_id in candidates[:negative_count]:
        cases.append(EvalCase("normal2", instance_id, False))
    return cases


async def evaluate(
    application: Application,
    *,
    mode: str = "heuristic",
    negative_count: int = 50,
) -> dict[str, Any]:
    cases = build_cases(application, negative_count)
    rows: list[dict[str, Any]] = []
    request_rows: list[dict[str, Any]] = []
    for case in cases:
        operations: list[dict[str, Any]] = []
        for request_id in application.store.request_ids(instance_id=case.instance_id):
            scope = InvestigationScope(case.instance_id, request_id)
            result = await application.harness(mode).run(scope.task())
            citations = list(dict.fromkeys([
                *result.report.evidence, *result.report.counterevidence
            ])) if result.report else []
            valid = 0
            # Chunk validation to honor the tool's 30-citation budget.
            for offset in range(0, len(citations), 30):
                check = application.tools.validate_evidence(
                    dataset="all", instance_id=case.instance_id, request_id=request_id,
                    citations=citations[offset:offset + 30],
                )
                valid += int(check["valid_count"])
            operation = {
                "instance_id": case.instance_id,
                "request_id": request_id,
                "verdict": result.report.verdict if result.report else None,
                "status": result.status,
                "evidence_count": len(citations),
                "valid_evidence_count": valid,
                "steps": len(result.observations),
                "elapsed_ms": round(result.elapsed_ms, 2),
                "run_id": result.run_id,
            }
            operations.append(operation)
            request_rows.append(operation)
        predicted = any(operation["verdict"] == "anomalous" for operation in operations)
        complete = bool(operations) and all(
            operation["status"] == "completed" for operation in operations
        )
        verdict = (
            "anomalous" if predicted else "normal" if operations and all(
                operation["verdict"] == "normal" for operation in operations
            ) else "uncertain"
        )
        rows.append(
            {
                **asdict(case),
                "predicted_anomalous": predicted,
                "verdict": verdict,
                "status": "completed" if complete else "incomplete",
                "request_count": len(operations),
                "evidence_count": sum(operation["evidence_count"] for operation in operations),
                "valid_evidence_count": sum(operation["valid_evidence_count"] for operation in operations),
                "steps": sum(operation["steps"] for operation in operations),
                "elapsed_ms": round(sum(operation["elapsed_ms"] for operation in operations), 2),
                "requests": operations,
                "warning": None if operations else "No request-tagged instance logs; not classified as normal",
            }
        )

    tp = sum(row["expected_anomalous"] and row["predicted_anomalous"] for row in rows)
    fp = sum(not row["expected_anomalous"] and row["predicted_anomalous"] for row in rows)
    fn = sum(row["expected_anomalous"] and not row["predicted_anomalous"] for row in rows)
    tn = sum(not row["expected_anomalous"] and not row["predicted_anomalous"] for row in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    total_evidence = sum(row["evidence_count"] for row in rows)
    valid_evidence = sum(row["valid_evidence_count"] for row in rows)
    report = {
        "metadata": {
            "created_at": datetime.now(UTC).isoformat(),
            "mode": mode,
            "case_count": len(rows),
            "request_count": len(request_rows),
            "scope": "instance_id + request_id",
            "aggregation": "instance is flagged if any of its request investigations flags an anomaly",
            "tool_metrics_unit": "request investigations",
            "positive_count": sum(row["expected_anomalous"] for row in rows),
            "negative_count": sum(not row["expected_anomalous"] for row in rows),
            "warning": (
                "Labels are instance-level only: request results are aggregated before scoring. "
                "No request-level ground truth or root-cause accuracy is established. "
                "Missing request IDs or incomplete investigations reduce coverage; old metrics are not reusable."
            ),
        },
        "metrics": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "evidence_validity": round(valid_evidence / total_evidence, 4)
            if total_evidence
            else 0.0,
            "completion_rate": round(
                sum(row["status"] == "completed" for row in request_rows) / len(request_rows), 4
            ) if request_rows else 0.0,
            "instance_completion_rate": round(
                sum(row["status"] == "completed" for row in rows) / len(rows), 4
            ) if rows else 0.0,
            "instance_request_coverage": round(
                sum(bool(row["request_count"]) for row in rows) / len(rows), 4
            ) if rows else 0.0,
            "mean_steps": round(statistics.mean(row["steps"] for row in request_rows), 2)
            if request_rows else 0.0,
            "mean_latency_ms": round(statistics.mean(row["elapsed_ms"] for row in request_rows), 2)
            if request_rows else 0.0,
        },
        "cases": rows,
    }
    output_dir = application.settings.artifacts_path / "evaluations"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"evaluation-request-scoped-{mode}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["output_path"] = str(output)
    return report


def evaluate_sync(application: Application, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(evaluate(application, **kwargs))
