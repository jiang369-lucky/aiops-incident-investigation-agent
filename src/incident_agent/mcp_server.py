from __future__ import annotations

from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install MCP dependencies with `pip install -e .[mcp]`") from exc

from .application import create_application

application = create_application()
mcp = FastMCP("openstack-incident-tools")


@mcp.tool()
def get_instance_summary(instance_id: str, request_id: str) -> dict[str, Any]:
    """Return signals only for the specified instance/request pair."""
    return application.tools.get_instance_summary("all", instance_id, request_id)


@mcp.tool()
def search_logs(
    instance_id: str,
    request_id: str,
    query: str = "",
    levels: list[str] | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Read at most 100 matching logs. This tool never exposes evaluation labels."""
    return application.tools.search_logs(
        dataset="all",
        instance_id=instance_id,
        request_id=request_id,
        query=query or None,
        levels=levels,
        limit=limit,
    )


@mcp.tool()
def get_timeline(instance_id: str, request_id: str, limit: int = 80) -> dict[str, Any]:
    """Return bounded opening and terminal events of the specified operation."""
    return application.tools.get_timeline("all", instance_id, request_id, limit)


@mcp.tool()
def search_runbooks(query: str, limit: int = 3) -> dict[str, Any]:
    """Find citeable Runbook chunks; guidance is not incident evidence."""
    return application.tools.search_runbooks(query, limit)


@mcp.tool()
def get_case_memory(instance_id: str, request_id: str, limit: int = 2) -> dict[str, Any]:
    """Read approved drafts for this instance/request pair as historical context."""
    return application.tools.get_case_memory(instance_id, request_id, limit)


@mcp.tool()
def validate_evidence(instance_id: str, request_id: str, citations: list[str]) -> dict[str, Any]:
    """Verify citations match both the investigated instance and request."""
    return application.tools.validate_evidence("all", instance_id, request_id, citations)


@mcp.tool()
def save_ticket_draft(ticket: dict[str, Any], approved: bool = False) -> dict[str, Any]:
    """Persist a draft in PostgreSQL only when the caller explicitly passes approved=true."""
    return application.tools.save_ticket_draft(ticket, approved)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
