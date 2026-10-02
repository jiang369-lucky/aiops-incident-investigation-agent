from __future__ import annotations

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install API dependencies with `pip install -e .[api]`") from exc

from .application import create_application


class InvestigationRequest(BaseModel):
    instance_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
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
    task = (
        f"Investigate OpenStack instance {request.instance_id}. "
        "Produce an evidence-grounded report and do not take remediation action."
    )
    result = await application.harness(request.mode).run(task)
    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)
    if result.status in {"blocked", "timed_out"}:
        raise HTTPException(status_code=422, detail=result.to_dict())
    return result.to_dict()
