"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="MedSync",
    description="FHIR-native clinical data pipeline with AI triage",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by Docker Compose and load balancers."""
    return {"status": "ok"}
