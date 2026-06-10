"""FHIR Bundle upload + pipeline status streaming."""

from __future__ import annotations

import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from medsync.config import settings
from medsync.db.session import get_session
from medsync.models.database import PipelineRun
from medsync.models.schemas import BundleUploadResponse, PipelineRunOut
from medsync.pipeline.tasks import parse_stage

router = APIRouter(prefix="/api/v1/bundles", tags=["bundles"])


@router.post("/upload", response_model=BundleUploadResponse)
async def upload_bundle(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> BundleUploadResponse:
    """Accept a FHIR Bundle JSON, create a pipeline run, enqueue async processing."""
    raw = await file.read()
    try:
        bundle = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(status_code=400, detail="Payload is not a FHIR Bundle")

    run = PipelineRun(bundle_filename=file.filename, status="pending", raw_bundle=bundle)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    parse_stage.delay(run.id)
    return BundleUploadResponse(pipeline_run_id=run.id, status=run.status)


@router.get("/{run_id}", response_model=PipelineRunOut)
async def get_run(run_id: int, session: AsyncSession = Depends(get_session)) -> PipelineRun:
    run = await session.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    return run


@router.websocket("/{run_id}/status")
async def stream_status(websocket: WebSocket, run_id: int) -> None:
    """Relay Redis pipeline:{run_id} status events to the client over WebSocket."""
    await websocket.accept()
    client = aioredis.from_url(settings.redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe(f"pipeline:{run_id}")
    try:
        async for message in pubsub.listen():
            if message.get("type") == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                await websocket.send_text(data)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"pipeline:{run_id}")
        await pubsub.close()
        await client.close()
