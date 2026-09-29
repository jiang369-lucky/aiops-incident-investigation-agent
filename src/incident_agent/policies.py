from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import Any

from .domain import FinishAction, IncidentReport, Observation, ToolAction
from .skills import Skill, SkillCatalog

UUID_RE = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.IGNORECASE)
DATASET_RE = re.compile(r"dataset\s*[=:]\s*(abnormal|normal1|normal2)", re.IGNORECASE)
SUSPICIOUS_RE = re.compile(
    r"error|fail|exception|traceback|timeout|no valid host|connection refused|"
    r"unavailable|vm stopped|vm paused",
    re.IGNORECASE,
)


def parse_task(task: str) -> tuple[str, str]:
    instance_match = UUID_RE.search(task)
    dataset_match = DATASET_RE.search(task)
    if not instance_match or not dataset_match:
        raise ValueError("Task must contain an instance UUID and dataset=<name>")
    return dataset_match.group(1).lower(), instance_match.group(0).lower()


class HeuristicInvestigatorPolicy:
    """Reproducible offline policy used as a baseline and no-key demo."""

    def __init__(self, skills: list[Skill]):
        self.skills = skills

    async def next_action(
        self, task: str, observations: list[Observation], step: int
    ) -> ToolAction | FinishAction:
        dataset, instance_id = parse_task(task)
        tools_seen = {item.tool for item in observations}
        if "get_instance_summary" not in tools_seen:
            return ToolAction(
                tool="get_instance_summary",
                arguments={"dataset": dataset, "instance_id": instance_id},
                reason="Establish bounded counts and suspicious signals before forming a hypothesis.",
            )
        if "get_timeline" not in tools_seen:
            return ToolAction(
                tool="get_timeline",
                arguments={"dataset": dataset, "instance_id": instance_id, "limit": 80},
                reason="Reconstruct the instance timeline and retain citeable evidence.",
            )
        if "search_runbooks" not in tools_seen:
            query = self._runbook_query(observations)
            return ToolAction(
                tool="search_runbooks",
                arguments={"query": query, "limit": 3},
                reason="Compare observed symptoms with operating guidance without treating it as evidence.",
            )
        citations = self._evidence(observations)
        if "validate_evidence" not in tools_seen and citations:
            return ToolAction(
                tool="validate_evidence",
                arguments={
                    "dataset": dataset,
                    "instance_id": instance_id,
                    "citations": citations,
                },
                reason="Check that every cited log exists and belongs to this incident.",
            )
        return FinishAction(self._report(dataset, instance_id, observations))

    @staticmethod
    def _observation(observations: list[Observation], tool: str) -> dict[str, Any]:
        for item in observations:
            if item.tool == tool:
                return item.result
        return {}

    def _evidence(self, observations: list[Observation]) -> list[str]:
        summary = self._observation(observations, "get_instance_summary")
        summary_examples = (
            summary.get("suspicious_examples", []) if isinstance(summary, dict) else []
        )
        timeline = self._observation(observations, "get_timeline")
        events = timeline.get("events", []) if isinstance(timeline, dict) else []
        timeline_suspicious = [
            event for event in events if SUSPICIOUS_RE.search(str(event.get("message", "")))
        ]
        selected = [*summary_examples, *timeline_suspicious][:8]
        if not selected and events:
            selected = [events[0], events[-1]] if len(events) > 1 else [events[0]]
        return list(
            dict.fromkeys(str(event["citation"]) for event in selected if event.get("citation"))
        )

    def _runbook_query(self, observations: list[Observation]) -> str:
        summary = self._observation(observations, "get_instance_summary")
        examples = summary.get("suspicious_examples", []) if isinstance(summary, dict) else []
        messages = " ".join(str(item.get("message", "")) for item in examples[:5])
        return messages or "OpenStack VM lifecycle instance investigation"

    def _report(
        self, dataset: str, instance_id: str, observations: list[Observation]
    ) -> IncidentReport:
        summary = self._observation(observations, "get_instance_summary")
        total = int(summary.get("total_records", 0))
        suspicious = int(summary.get("suspicious_count", 0))
        levels = summary.get("level_counts", {})
        errors = int(levels.get("ERROR", 0)) + int(levels.get("CRITICAL", 0))
        warnings = int(levels.get("WARNING", 0))
        build_duration = summary.get("build_duration_seconds")
        latency_outlier = bool(summary.get("latency_outlier", False))
        citations = self._evidence(observations)
        validation = self._observation(observations, "validate_evidence")
        valid_citations = {
            item["citation"] for item in validation.get("details", []) if item.get("valid")
        }
        evidence = [citation for citation in citations if citation in valid_citations]

        if not total:
            verdict = "uncertain"
            confidence = 0.2
            hypothesis = (
                "No instance-scoped records were found; the query scope or identifier may be wrong."
            )
        elif latency_outlier or errors > 0 or suspicious >= 3:
            verdict = "anomalous"
            confidence = min(0.92, 0.68 + errors * 0.08 + suspicious * 0.025)
            hypothesis = (
                "The instance shows an abnormal build-latency or failure signal compared with the "
                "normal reference distribution. "
                "The public labels do not identify a root cause, so this remains a candidate diagnosis."
            )
        elif warnings == 0 and suspicious <= 2:
            verdict = "normal"
            confidence = 0.78
            hypothesis = (
                "Build latency is within the normal reference range and no instance-scoped "
                "warning or error was found. Routine pause/stop lifecycle events were not "
                "treated as faults by themselves."
            )
        else:
            verdict = "uncertain"
            confidence = 0.5
            hypothesis = (
                "Some suspicious signals exist, but the available evidence is not decisive."
            )

        return IncidentReport(
            instance_id=instance_id,
            dataset=dataset,
            verdict=verdict,
            confidence=round(confidence, 3),
            summary=(
                f"Reviewed {total} instance-scoped records: {errors} errors, "
                f"{warnings} warnings, {suspicious} suspicious matches; "
                f"build duration={build_duration} seconds."
            ),
            hypothesis=hypothesis,
            evidence=evidence,
            counterevidence=self._counterevidence(observations),
            recommended_actions=[
                "Have an operator review the cited timeline before taking remediation action.",
                "Correlate the instance with host, network, and storage telemetry not present in Loghub.",
                "Create a ticket only after human approval.",
            ],
            requires_human_review=True,
            limitations=[
                "Loghub identifies anomalous instances but does not provide line-level root-cause labels.",
                "The result is an investigation aid, not an autonomous remediation decision.",
            ],
            skills_used=[skill.name for skill in self.skills],
        )

    @staticmethod
    def _counterevidence(observations: list[Observation]) -> list[str]:
        timeline = HeuristicInvestigatorPolicy._observation(observations, "get_timeline")
        events = timeline.get("events", []) if isinstance(timeline, dict) else []
        healthy = [
            item["citation"]
            for item in events
            if re.search(
                r"spawned successfully|claim successful|status:\s*200",
                str(item.get("message", "")),
                re.IGNORECASE,
            )
            and item.get("citation")
        ]
        return list(dict.fromkeys(healthy))[:5]


class OpenAICompatiblePolicy:
    """LLM policy using the common Chat Completions wire format without an SDK."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        tools: list[dict[str, Any]],
        skills: list[Skill],
        request_timeout: float = 30.0,
    ):
        if not api_key:
            raise ValueError("AGENT_API_KEY is required for LLM mode")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.tools = tools
        self.skills = skills
        self.request_timeout = request_timeout

    async def next_action(
        self, task: str, observations: list[Observation], step: int
    ) -> ToolAction | FinishAction:
        prompt = self._prompt(task, observations, step)
        content = await asyncio.to_thread(self._request, prompt)
        payload = self._json(content)
        if payload.get("type") == "tool":
            return ToolAction(
                tool=str(payload["tool"]),
                arguments=dict(payload.get("arguments", {})),
                reason=str(payload.get("reason", "")),
            )
        if payload.get("type") == "finish":
            return FinishAction(IncidentReport(**payload["report"]))
        raise ValueError("Model response must have type=tool or type=finish")

    def _prompt(self, task: str, observations: list[Observation], step: int) -> str:
        return f"""You are an evidence-grounded OpenStack incident investigator.
Never claim a root cause that the logs do not support. Never invent citations.
Use tools iteratively, check counterevidence, call validate_evidence before finish,
and always require human review. Dataset labels are unavailable to you.

TASK:
{task}

SKILLS:
{SkillCatalog.prompt_text(self.skills)}

TOOLS:
{json.dumps(self.tools, ensure_ascii=False)}

OBSERVATIONS:
{json.dumps([asdict(item) for item in observations], ensure_ascii=False, default=str)}

STEP: {step}

Return JSON only. To call a tool:
{{"type":"tool","tool":"name","arguments":{{}},"reason":"why"}}
To finish:
{{"type":"finish","report":{{"instance_id":"...","dataset":"...",
"verdict":"anomalous|normal|uncertain","confidence":0.0,"summary":"...",
"hypothesis":"...","evidence":["dataset:line"],"counterevidence":[],
"recommended_actions":[],"requires_human_review":true,"limitations":[],
"skills_used":[]}}}}
"""

    def _request(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Model endpoint returned HTTP {exc.code}: {detail[:500]}") from exc
        return str(result["choices"][0]["message"]["content"])

    @staticmethod
    def _json(content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("Model response must be a JSON object")  # noqa: TRY004
        return value
