"""FastAPI application entry point."""

from fastapi import FastAPI

from medsync.api.routes import bundles, patients

app = FastAPI(
    title="MedSync",
    description="FHIR-native clinical data pipeline with AI triage",
    version="0.1.0",
)

app.include_router(bundles.router)
app.include_router(patients.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by Docker Compose and load balancers."""
    return {"status": "ok"}
