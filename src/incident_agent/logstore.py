from __future__ import annotations

import json
import re
import sqlite3
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from .domain import LogRecord
from .parser import parse_openstack_line

DATASET_FILES = {
    "abnormal": "openstack_abnormal.log",
    "normal1": "openstack_normal1.log",
    "normal2": "openstack_normal2.log",
}

SUSPICIOUS_RE = re.compile(
    r"\b(error|failed|failure|exception|traceback|timed?\s*out|no valid host|"
    r"connection refused|not found|unavailable|killed|stopped|paused)\b",
    re.IGNORECASE,
)
BUILD_DURATION_RE = re.compile(r"Took\s+([0-9.]+)\s+seconds to build instance", re.IGNORECASE)


class OpenStackLogStore:
    """Deep module hiding parsing, indexing, query limits, and citation lookup."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self._duration_baseline: dict[str, float | int | str] | None = None

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.exists():
            raise FileNotFoundError(
                f"Log index not found: {self.database_path}. Run `incident-agent prepare`."
            )
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def build(self, raw_data_path: Path, *, force: bool = False) -> dict[str, int]:
        raw_data_path = Path(raw_data_path)
        missing = [name for name in DATASET_FILES.values() if not (raw_data_path / name).exists()]
        if missing:
            raise FileNotFoundError(f"Missing raw log files: {', '.join(missing)}")

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        if self.database_path.exists() and not force:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT dataset, COUNT(*) AS count FROM logs GROUP BY dataset"
                ).fetchall()
            return {row["dataset"]: row["count"] for row in rows}
        if self.database_path.exists():
            self.database_path.unlink()

        connection = sqlite3.connect(self.database_path)
        try:
            self._create_schema(connection)
            counts: dict[str, int] = {}
            for dataset, filename in DATASET_FILES.items():
                path = raw_data_path / filename
                count = self._load_file(connection, dataset, path)
                counts[dataset] = count
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES(?, ?)",
                ("dataset_counts", json.dumps(counts, ensure_ascii=False)),
            )
            connection.commit()
            return counts
        finally:
            connection.close()

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset TEXT NOT NULL,
                line_no INTEGER NOT NULL,
                timestamp TEXT,
                source TEXT NOT NULL,
                level TEXT NOT NULL,
                logger TEXT NOT NULL,
                request_id TEXT,
                instance_id TEXT,
                message TEXT NOT NULL,
                raw TEXT NOT NULL,
                UNIQUE(dataset, line_no)
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX idx_logs_instance ON logs(instance_id, dataset, timestamp);
            CREATE INDEX idx_logs_request ON logs(request_id, dataset, timestamp);
            CREATE INDEX idx_logs_level ON logs(level, dataset);
            CREATE INDEX idx_logs_timestamp ON logs(dataset, timestamp);
            """
        )

    @staticmethod
    def _load_file(connection: sqlite3.Connection, dataset: str, path: Path) -> int:
        batch: list[tuple[object, ...]] = []
        count = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                parsed = parse_openstack_line(line)
                batch.append(
                    (
                        dataset,
                        line_no,
                        parsed.timestamp,
                        parsed.source,
                        parsed.level,
                        parsed.logger,
                        parsed.request_id,
                        parsed.instance_id,
                        parsed.message,
                        parsed.raw,
                    )
                )
                if len(batch) >= 2_000:
                    connection.executemany(
                        """
                        INSERT INTO logs(
                            dataset, line_no, timestamp, source, level, logger,
                            request_id, instance_id, message, raw
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch,
                    )
                    count += len(batch)
                    batch.clear()
            if batch:
                connection.executemany(
                    """
                    INSERT INTO logs(
                        dataset, line_no, timestamp, source, level, logger,
                        request_id, instance_id, message, raw
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                count += len(batch)
        connection.commit()
        return count

    def search(
        self,
        *,
        dataset: str,
        instance_id: str | None = None,
        request_id: str | None = None,
        query: str | None = None,
        levels: Iterable[str] | None = None,
        limit: int = 30,
    ) -> list[LogRecord]:
        limit = max(1, min(int(limit), 100))
        clauses = ["dataset = ?"]
        parameters: list[object] = [dataset]
        if instance_id:
            clauses.append("instance_id = ?")
            parameters.append(instance_id.lower())
        if request_id:
            clauses.append("request_id = ?")
            parameters.append(request_id.lower())
        normalized_levels = [item.upper() for item in levels or []]
        if normalized_levels:
            placeholders = ",".join("?" for _ in normalized_levels)
            clauses.append(f"level IN ({placeholders})")
            parameters.extend(normalized_levels)
        if query:
            clauses.append("LOWER(raw) LIKE ?")
            parameters.append(f"%{query.lower()}%")
        parameters.append(limit)
        sql = (
            "SELECT * FROM logs WHERE "
            + " AND ".join(clauses)
            + " ORDER BY timestamp, line_no LIMIT ?"
        )
        with self._connect() as connection:
            return [self._row_to_record(row) for row in connection.execute(sql, parameters)]

    def timeline(self, *, dataset: str, instance_id: str, limit: int = 80) -> list[LogRecord]:
        return self.search(dataset=dataset, instance_id=instance_id, limit=limit)

    def instance_summary(self, *, dataset: str, instance_id: str) -> dict[str, object]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, dataset, line_no, timestamp, source, level, logger,
                       request_id, instance_id, message, raw
                FROM logs WHERE dataset = ? AND instance_id = ?
                ORDER BY timestamp, line_no
                """,
                (dataset, instance_id.lower()),
            ).fetchall()
        records = [self._row_to_record(row) for row in rows]
        levels = Counter(record.level for record in records)
        sources = Counter(record.logger.split(".")[0] for record in records)
        baseline = self.normal_build_duration_baseline()
        build_duration = None
        build_record = None
        for record in records:
            match = BUILD_DURATION_RE.search(record.message)
            if match:
                build_duration = float(match.group(1))
                build_record = record
                break
        outlier_threshold = float(baseline["p95_seconds"]) * 1.25
        latency_outlier = bool(build_duration and build_duration > outlier_threshold)
        suspicious = [record for record in records if SUSPICIOUS_RE.search(record.raw)]
        if latency_outlier and build_record and build_record not in suspicious:
            suspicious.append(build_record)
        return {
            "dataset": dataset,
            "instance_id": instance_id.lower(),
            "total_records": len(records),
            "level_counts": dict(levels),
            "source_counts": dict(sources.most_common(8)),
            "first_timestamp": records[0].timestamp if records else None,
            "last_timestamp": records[-1].timestamp if records else None,
            "suspicious_count": len(suspicious),
            "suspicious_examples": [self._public_record(item) for item in suspicious[:12]],
            "build_duration_seconds": build_duration,
            "normal_build_duration_p95_seconds": baseline["p95_seconds"],
            "latency_outlier_threshold_seconds": round(outlier_threshold, 3),
            "latency_outlier": latency_outlier,
        }

    def normal_build_duration_baseline(self) -> dict[str, float | int | str]:
        """Compute a reference distribution from normal partitions only, never from labels."""
        if self._duration_baseline is not None:
            return self._duration_baseline
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT message FROM logs
                WHERE dataset = 'normal1'
                  AND message LIKE '%%seconds to build instance%%'
                """
            ).fetchall()
        values = [
            float(match.group(1))
            for row in rows
            if (match := BUILD_DURATION_RE.search(row["message"]))
        ]
        if not values:
            self._duration_baseline = {"sample_count": 0, "median_seconds": 0.0, "p95_seconds": 0.0}
            return self._duration_baseline
        ordered = sorted(values)
        p95_index = int(0.95 * (len(ordered) - 1))
        self._duration_baseline = {
            "sample_count": len(values),
            "calibration_dataset": "normal1",
            "median_seconds": round(statistics.median(values), 3),
            "p95_seconds": round(ordered[p95_index], 3),
        }
        return self._duration_baseline

    def record_by_citation(self, citation: str) -> LogRecord | None:
        try:
            dataset, raw_line = citation.split(":", 1)
            line_no = int(raw_line)
        except (ValueError, TypeError):
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM logs WHERE dataset = ? AND line_no = ?",
                (dataset, line_no),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def instance_ids(self, *, dataset: str, limit: int = 10_000) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT instance_id, COUNT(*) AS count FROM logs
                WHERE dataset = ? AND instance_id IS NOT NULL
                GROUP BY instance_id ORDER BY count DESC LIMIT ?
                """,
                (dataset, limit),
            ).fetchall()
        return [row["instance_id"] for row in rows]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> LogRecord:
        return LogRecord(**{key: row[key] for key in LogRecord.__dataclass_fields__})

    @staticmethod
    def _public_record(record: LogRecord) -> dict[str, object]:
        value = asdict(record)
        value["citation"] = record.citation()
        value.pop("raw", None)
        return value
