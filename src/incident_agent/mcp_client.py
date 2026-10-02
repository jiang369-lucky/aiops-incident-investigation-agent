from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from .config import Settings, project_root


class MCPToolClient:
    """Use one stdio MCP session for all tool calls in an investigation."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._session: Any = None
        self._catalog: list[dict[str, Any]] = []

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[None]:
        try:
            from mcp import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ImportError as exc:
            raise RuntimeError("MCP transport requires the `mcp` package") from exc

        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "incident_agent.mcp_server"],
            cwd=str(project_root()),
            env={
                "AGENT_DATABASE_URL": self.settings.database_url,
                "AGENT_RUNBOOKS_PATH": str(self.settings.runbooks_path),
                "AGENT_ARTIFACTS_PATH": str(self.settings.artifacts_path),
            },
        )
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                discovered = (await session.list_tools()).tools
                available = {item.name for item in discovered}
                required = {
                    "get_case_memory", "get_instance_summary", "search_logs",
                    "get_timeline", "search_runbooks", "validate_evidence",
                }
                if missing := required - available:
                    raise RuntimeError(f"MCP server is missing tools: {sorted(missing)}")
                self._catalog = [
                    {
                        "name": item.name,
                        "description": item.description or "",
                        "input_schema": item.inputSchema,
                    }
                    for item in discovered
                ]
                self._session = session
                try:
                    yield
                finally:
                    self._session = None
                    self._catalog = []

    def describe(self) -> list[dict[str, Any]]:
        if self._session is None:
            raise RuntimeError("MCP tool session is not connected")
        return list(self._catalog)

    async def call_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("MCP tool session is not connected")
        result = await self._session.call_tool(name, arguments=arguments)
        text_blocks = [block.text for block in result.content if hasattr(block, "text")]
        if result.isError:
            raise RuntimeError(f"MCP tool {name} failed: {' '.join(text_blocks)[:500]}")
        value = result.structuredContent
        if value is None and text_blocks:
            value = json.loads(text_blocks[0])
        if isinstance(value, dict) and set(value) == {"result"} and isinstance(value["result"], dict):
            value = value["result"]
        if not isinstance(value, dict):
            raise RuntimeError(f"MCP tool {name} returned no structured object")
        return value
