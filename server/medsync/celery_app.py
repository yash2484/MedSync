"""Celery application instance.

The FHIR pipeline runs as a Celery chain (parse | normalize | deduplicate |
enrich) — see medsync.pipeline.tasks (added in Increment 1+).
"""

from celery import Celery

from medsync.config import settings

celery = Celery(
    "medsync",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["medsync.pipeline.tasks"],
)

celery.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
)
