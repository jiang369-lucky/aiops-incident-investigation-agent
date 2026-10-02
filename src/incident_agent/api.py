from __future__ import annotations

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install API dependencies with `pip install -e .[api]`") from exc

from .application import create_application
from .domain import REQUEST_PATTERN, UUID_PATTERN, ScopeResolutionError


class InvestigationRequest(BaseModel):
    instance_id: str = Field(pattern=rf"^{UUID_PATTERN}$")
    request_id: str | None = Field(default=None, pattern=rf"^{REQUEST_PATTERN}$")
    mode: str = Field(default="heuristic", pattern=r"^(heuristic|llm)$")


application = create_application()
app = FastAPI(
    title="AIOps Incident Investigation Agent",
    version="0.1.0",
    description="Read-only evidence investigation; no autonomous remediation.",
)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok" if application.store.is_ready() else "index_missing_or_unavailable",
        "database": "PostgreSQL",
    }


@app.post("/v1/investigations")
async def investigate(request: InvestigationRequest) -> dict[str, object]:
    try:
        result = await application.investigate(request.instance_id, request.request_id, request.mode)
    except ScopeResolutionError as exc:
        raise HTTPException(status_code=422, detail={"code": "scope_unresolved", "error": str(exc)}) from exc
    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.to_dict())
    if result.status in {"blocked", "timed_out"}:
        raise HTTPException(status_code=422, detail=result.to_dict())
    return result.to_dict()
