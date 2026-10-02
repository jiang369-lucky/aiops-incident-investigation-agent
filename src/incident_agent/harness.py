from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .domain import AgentAction, FinishAction, Observation, RunResult, ToolAction
from .mcp_client import MCPToolClient
from .tools import ToolRegistry


class AgentPolicy(Protocol):
    async def next_action(
        self,
        task: str,
        observations: list[Observation],
        step: int,
    ) -> AgentAction: ...


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    max_steps: int = 8
    total_timeout_seconds: float = 45.0
    tool_timeout_seconds: float = 8.0
    tool_retries: int = 1
    max_repeated_call: int = 2
    max_observation_chars: int = 16_000
    allowed_tools: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "get_instance_summary",
                "search_logs",
                "get_timeline",
                "search_runbooks",
                "get_case_memory",
                "validate_evidence",
            }
        )
    )


class AgentHarness:
    """Runs any policy safely behind one small, testable interface."""

    def __init__(
        self,
        policy: AgentPolicy,
        tools: ToolRegistry | MCPToolClient,
        trace_path: Path,
        config: HarnessConfig | None = None,
    ):
        self.policy = policy
        self.tools = tools
        self.trace_path = Path(trace_path)
        self.config = config or HarnessConfig()

    async def run(self, task: str) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        observations: list[Observation] = []
        repeats: dict[str, int] = {}
        self._trace(run_id, "run_started", {"task": task, "config": asdict(self.config)})

        try:
            async with asyncio.timeout(self.config.total_timeout_seconds):
                async with AsyncExitStack() as stack:
                    if isinstance(self.tools, MCPToolClient):
                        await stack.enter_async_context(self.tools.connect())
                    catalog = [
                        item for item in self.tools.describe()
                        if item["name"] in self.config.allowed_tools
                    ]
                    if hasattr(self.policy, "set_tools"):
                        self.policy.set_tools(catalog)
                    self._trace(
                        run_id,
                        "tools_discovered",
                        {"transport": "mcp" if isinstance(self.tools, MCPToolClient) else "local",
                         "names": [item["name"] for item in catalog]},
                    )
                    for step in range(self.config.max_steps):
                        action = await self.policy.next_action(task, observations, step)
                        self._trace(run_id, "action", self._action_dict(action, step))
                        if isinstance(action, FinishAction):
                            elapsed = (time.perf_counter() - started) * 1_000
                            result = RunResult(
                                run_id=run_id,
                                status="completed",
                                report=action.report,
                                observations=observations,
                                elapsed_ms=elapsed,
                            )
                            self._trace(run_id, "run_finished", result.to_dict())
                            return result

                        blocked = self._guard(action, repeats)
                        if blocked:
                            elapsed = (time.perf_counter() - started) * 1_000
                            result = RunResult(
                                run_id=run_id,
                                status="blocked",
                                report=None,
                                observations=observations,
                                error=blocked,
                                elapsed_ms=elapsed,
                            )
                            self._trace(run_id, "run_blocked", result.to_dict())
                            return result

                        observation = await self._execute(action)
                        observations.append(observation)
                        self._trace(run_id, "observation", asdict(observation))
        except TimeoutError:
            elapsed = (time.perf_counter() - started) * 1_000
            result = RunResult(
                run_id=run_id,
                status="timed_out",
                report=None,
                observations=observations,
                error="Run exceeded total timeout",
                elapsed_ms=elapsed,
            )
            self._trace(run_id, "run_timed_out", result.to_dict())
            return result
        except (
            Exception  # noqa: BLE001
        ) as exc:  # harness converts policy/tool crashes into a stable result
            elapsed = (time.perf_counter() - started) * 1_000
            result = RunResult(
                run_id=run_id,
                status="failed",
                report=None,
                observations=observations,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed,
            )
            self._trace(run_id, "run_failed", result.to_dict())
            return result

        elapsed = (time.perf_counter() - started) * 1_000
        result = RunResult(
            run_id=run_id,
            status="failed",
            report=None,
            observations=observations,
            error=f"Agent did not finish within {self.config.max_steps} steps",
            elapsed_ms=elapsed,
        )
        self._trace(run_id, "run_failed", result.to_dict())
        return result

    def _guard(self, action: ToolAction, repeats: dict[str, int]) -> str | None:
        if action.tool not in self.config.allowed_tools:
            return f"Tool is not allowed by harness policy: {action.tool}"
        signature = hashlib.sha256(
            json.dumps(
                {"tool": action.tool, "arguments": action.arguments},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        repeats[signature] = repeats.get(signature, 0) + 1
        if repeats[signature] > self.config.max_repeated_call:
            return f"Repeated identical tool call detected: {action.tool}"
        return None

    async def _execute(self, action: ToolAction) -> Observation:
        last_error: Exception | None = None
        for attempt in range(1, self.config.tool_retries + 2):
            started = time.perf_counter()
            try:
                async with asyncio.timeout(self.config.tool_timeout_seconds):
                    if isinstance(self.tools, MCPToolClient):
                        result = await self.tools.call_async(action.tool, action.arguments)
                    else:
                        result = await asyncio.to_thread(self.tools.call, action.tool, action.arguments)
                result = self._bounded(result)
                return Observation(
                    tool=action.tool,
                    arguments=action.arguments,
                    result=result,
                    latency_ms=(time.perf_counter() - started) * 1_000,
                    attempt=attempt,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt <= self.config.tool_retries:
                    await asyncio.sleep(0.1 * 2 ** (attempt - 1))
        assert last_error is not None
        raise last_error

    def _bounded(self, result: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(result, ensure_ascii=False, default=str)
        if len(raw) <= self.config.max_observation_chars:
            return result
        return {
            "truncated": True,
            "original_chars": len(raw),
            "preview": raw[: self.config.max_observation_chars],
        }

    def _trace(self, run_id: str, event: str, payload: dict[str, Any]) -> None:
        self.trace_path.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {"run_id": run_id, "event": event, "payload": payload},
            ensure_ascii=False,
            default=str,
        )
        with (self.trace_path / f"{run_id}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    @staticmethod
    def _action_dict(action: AgentAction, step: int) -> dict[str, Any]:
        if isinstance(action, FinishAction):
            return {"step": step, "type": "finish", "report": action.report.to_dict()}
        return {"step": step, "type": "tool", **asdict(action)}
