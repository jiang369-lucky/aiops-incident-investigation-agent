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
def get_instance_summary(dataset: str, instance_id: str) -> dict[str, Any]:
    """Return bounded counts and suspicious signals for a VM instance."""
    return application.tools.get_instance_summary(dataset, instance_id)


@mcp.tool()
def search_logs(
    dataset: str,
    instance_id: str = "",
    request_id: str = "",
    query: str = "",
    levels: list[str] | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Read at most 100 matching logs. This tool never exposes evaluation labels."""
    return application.tools.search_logs(
        dataset=dataset,
        instance_id=instance_id or None,
        request_id=request_id or None,
        query=query or None,
        levels=levels,
        limit=limit,
    )


@mcp.tool()
def get_timeline(dataset: str, instance_id: str, limit: int = 80) -> dict[str, Any]:
    """Return chronological, citeable events for one VM instance."""
    return application.tools.get_timeline(dataset, instance_id, limit)


@mcp.tool()
def search_runbooks(query: str, limit: int = 3) -> dict[str, Any]:
    """Find operational guidance; runbooks are guidance rather than incident evidence."""
    return application.tools.search_runbooks(query, limit)


@mcp.tool()
def validate_evidence(dataset: str, instance_id: str, citations: list[str]) -> dict[str, Any]:
    """Verify that citations exist and match the investigated instance."""
    return application.tools.validate_evidence(dataset, instance_id, citations)


@mcp.tool()
def save_ticket_draft(ticket: dict[str, Any], approved: bool = False) -> dict[str, Any]:
    """Save a local ticket draft only when a human explicitly passes approved=true."""
    return application.tools.save_ticket_draft(ticket, approved)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
