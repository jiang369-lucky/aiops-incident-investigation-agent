from __future__ import annotations

import json
import re
from typing import Any

from .domain import Observation, validated_log_citations

SIGNAL_RE = re.compile(
    r"error|fail|exception|timeout|stopped|paused|spawned successfully|claim successful",
    re.IGNORECASE,
)


class ContextManager:
    """Keep citeable current evidence and a small amount of approved history in the LLM prompt."""

    def __init__(self, max_chars: int = 12_000):
        self.max_chars = max_chars

    def build(self, observations: list[Observation]) -> dict[str, Any]:
        latest = {item.tool: item.result for item in observations}
        summary = latest.get("get_instance_summary", {})
        timeline = latest.get("get_timeline", {})
        guidance = latest.get("search_runbooks", {})
        history = latest.get("get_case_memory", {})
        searches = [item for item in observations if item.tool == "search_logs"][-2:]

        valid_citations = validated_log_citations(observations)
        events = timeline.get("events", [])
        priority = [
            event for event in events
            if event.get("citation") in valid_citations
            or SIGNAL_RE.search(str(event.get("message", "")))
        ]
        priority.extend(events[:2])
        priority.extend(events[-2:])
        selected_events: list[dict[str, Any]] = []
        seen: set[str] = set()
        for event in priority:
            citation = str(event.get("citation", ""))
            if not citation or citation in seen:
                continue
            seen.add(citation)
            selected_events.append(
                {
                    "citation": citation,
                    "timestamp": event.get("timestamp"),
                    "instance_id": event.get("instance_id"),
                    "request_id": event.get("request_id"),
                    "level": event.get("level"),
                    "message": str(event.get("message", ""))[:300],
                }
            )
            if len(selected_events) == 16:
                break

        context: dict[str, Any] = {
            "instance_summary": {
                key: summary.get(key)
                for key in (
                    "instance_id", "request_id", "matched_datasets", "total_records", "level_counts",
                    "suspicious_count", "build_duration_seconds", "latency_outlier",
                    "latency_outlier_threshold_seconds",
                    "first_timestamp", "last_timestamp",
                )
            },
            "suspicious_examples": [
                {
                    "citation": item.get("citation"),
                    "message": str(item.get("message", ""))[:300],
                }
                for item in summary.get("suspicious_examples", [])[:6]
            ],
            "timeline_events": selected_events,
            "timeline_selection": timeline.get("selection"),
            "timeline_possibly_truncated": timeline.get("possibly_truncated", False),
            "searched_logs": [
                {
                    "query": item.arguments,
                    "records": [
                        {
                            "citation": record.get("citation"),
                            "timestamp": record.get("timestamp"),
                            "instance_id": record.get("instance_id"),
                            "request_id": record.get("request_id"),
                            "level": record.get("level"),
                            "message": str(record.get("message", ""))[:300],
                        }
                        for record in item.result.get("records", [])[:6]
                    ],
                }
                for item in searches
            ],
            "runbook_chunks": [
                {
                    "citation": item.get("citation"),
                    "title": item.get("title"),
                    "excerpt": str(item.get("excerpt", ""))[:850],
                }
                for item in guidance.get("matches", [])[:3]
            ],
            "validated_log_citations": valid_citations,
            "approved_history": history.get("cases", [])[:2],
            "truncated_tool_results": [
                item.tool for item in observations if item.result.get("truncated")
            ],
            "recent_tools": [item.tool for item in observations[-6:]],
        }
        while len(json.dumps(context, ensure_ascii=False, default=str)) > self.max_chars:
            if context["timeline_events"]:
                context["timeline_events"].pop()
            elif context["approved_history"]:
                context["approved_history"].pop()
            elif context["suspicious_examples"]:
                context["suspicious_examples"].pop()
            elif context["searched_logs"]:
                context["searched_logs"].pop(0)
            elif len(context["runbook_chunks"]) > 1:
                context["runbook_chunks"].pop()
            else:
                raise ValueError("Essential investigation context exceeds the prompt budget")
        return context
