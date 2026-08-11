"""FastAPI application factory.

Wiring here is intentionally thin: construct Axiomra components in a
dependency container (apps/api/app/dependencies.py) and pass them in.
"""

from __future__ import annotations

from fastapi import FastAPI

from apps.api.app.routes.research import router as research_router

app = FastAPI(
    title="Axiomra API",
    version="0.1.0",
    description="Evidence-driven AI quant intelligence",
)

app.include_router(research_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
