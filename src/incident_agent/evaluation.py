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
    for case in cases:
        task = (
            f"Investigate OpenStack instance {case.instance_id}. "
            "Produce an evidence-grounded report."
        )
        result = await application.harness(mode).run(task)
        predicted = bool(result.report and result.report.verdict == "anomalous")
        evidence_count = len(result.report.evidence) if result.report else 0
        valid = 0
        if result.report and result.report.evidence:
            check = application.tools.validate_evidence(
                dataset="all",
                instance_id=case.instance_id,
                citations=result.report.evidence,
            )
            valid = int(check["valid_count"])
        rows.append(
            {
                **asdict(case),
                "predicted_anomalous": predicted,
                "verdict": result.report.verdict if result.report else None,
                "status": result.status,
                "evidence_count": evidence_count,
                "valid_evidence_count": valid,
                "steps": len(result.observations),
                "elapsed_ms": round(result.elapsed_ms, 2),
                "run_id": result.run_id,
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
            "positive_count": sum(row["expected_anomalous"] for row in rows),
            "negative_count": sum(not row["expected_anomalous"] for row in rows),
            "warning": (
                "This small smoke evaluation measures instance anomaly detection only; "
                "it does not establish root-cause accuracy."
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
                sum(row["status"] == "completed" for row in rows) / len(rows), 4
            ),
            "mean_steps": round(statistics.mean(row["steps"] for row in rows), 2),
            "mean_latency_ms": round(statistics.mean(row["elapsed_ms"] for row in rows), 2),
        },
        "cases": rows,
    }
    output_dir = application.settings.artifacts_path / "evaluations"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"evaluation-{mode}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["output_path"] = str(output)
    return report


def evaluate_sync(application: Application, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(evaluate(application, **kwargs))
