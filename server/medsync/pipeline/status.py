"""Pipeline status publishing over Redis pub/sub.

A Celery stage publishes a JSON status message to channel ``pipeline:{run_id}``;
a FastAPI WebSocket subscribes and relays it to the frontend (CLAUDE.md §9.5).
"""

from __future__ import annotations

import json

import redis

from medsync.config import settings


def publish_status(run_id: int, stage: str, status: str, **extra) -> None:
    """Publish a stage-transition event. Best-effort: never break the pipeline."""
    payload = {"run_id": run_id, "stage": stage, "status": status, **extra}
    try:
        client = redis.Redis.from_url(settings.redis_url)
        client.publish(f"pipeline:{run_id}", json.dumps(payload))
        client.close()
    except Exception:  # status is observability, not correctness
        pass
