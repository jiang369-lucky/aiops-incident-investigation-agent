from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .harness import AgentHarness, HarnessConfig
from .logstore import OpenStackLogStore
from .mcp_client import MCPToolClient
from .policies import HeuristicInvestigatorPolicy, OpenAICompatiblePolicy
from .runbooks import RunbookStore
from .skills import SkillCatalog
from .tools import ToolRegistry


@dataclass(slots=True)
class Application:
    settings: Settings
    store: OpenStackLogStore
    tools: ToolRegistry

    def harness(self, mode: str | None = None) -> AgentHarness:
        mode = mode or self.settings.model_mode
        skills = SkillCatalog(self.settings.skills_path).load(
            ["log-triage", "evidence-verification", "incident-reporting"]
        )
        if mode == "heuristic":
            policy = HeuristicInvestigatorPolicy(skills)
        elif mode == "llm":
            policy = OpenAICompatiblePolicy(
                base_url=self.settings.model_base_url,
                api_key=self.settings.model_api_key,
                model=self.settings.model_name,
                skills=skills,
            )
        else:
            raise ValueError("mode must be 'heuristic' or 'llm'")
        if self.settings.tool_transport == "mcp":
            tool_client = MCPToolClient(self.settings)
        elif self.settings.tool_transport == "local":
            tool_client = self.tools
        else:
            raise ValueError("AGENT_TOOL_TRANSPORT must be 'mcp' or 'local'")
        return AgentHarness(
            policy=policy,
            tools=tool_client,
            trace_path=self.settings.artifacts_path / "traces",
            config=HarnessConfig(),
        )


def create_application(settings: Settings | None = None) -> Application:
    settings = settings or Settings()
    store = OpenStackLogStore(settings.database_url)
    tools = ToolRegistry(
        store=store,
        runbooks=RunbookStore(settings.runbooks_path),
    )
    return Application(settings=settings, store=store, tools=tools)
