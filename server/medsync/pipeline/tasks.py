"""Celery pipeline tasks.

Increment 2 wires the ``parse`` stage for all 13 resource types. normalize /
deduplicate / enrich are appended to the chain in later increments
(CLAUDE.md §9.5):

    parse.s(run_id) | normalize.s() | deduplicate.s() | enrich.s()

DB access uses the async session driven via asyncio.run() — one event loop per
task run, which is safe under Celery's prefork pool.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict

from sqlalchemy import pool
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from medsync.celery_app import celery
from medsync.config import settings
from medsync.models.database import (
    AllergyIntolerance,
    Condition,
    DiagnosticReport,
    Encounter,
    MedicationRequest,
    Observation,
    Patient,
    PipelineRun,
    Procedure,
    RawResource,
)
from medsync.pipeline.normalizer import normalize_records
from medsync.pipeline.parser import ParseResult, parse_bundle
from medsync.pipeline.status import publish_status


@asynccontextmanager
async def _task_session():
    """A DB session whose engine lives and dies inside the current event loop.

    Celery runs each task via a fresh asyncio.run() loop. A module-level pooled
    engine binds connections to the first loop, so later tasks hit
    "Future attached to a different loop". A per-task NullPool engine, disposed
    before the loop closes, avoids any cross-loop connection reuse.
    """
    engine = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def _upsert(session, model, records, conflict: str = "fhir_id") -> None:
    """Idempotent bulk upsert. Record dataclass fields map 1:1 to model columns."""
    for record in records:
        values = asdict(record)
        stmt = pg_insert(model).values(**values)
        update_cols = {k: stmt.excluded[k] for k in values if k != conflict}
        stmt = stmt.on_conflict_do_update(index_elements=[conflict], set_=update_cols)
        await session.execute(stmt)


async def _persist(session, result: ParseResult) -> None:
    # Patients first (others FK to patients.fhir_id). encounter_fhir_id is a soft
    # reference, so ordering among the rest is irrelevant.
    await _upsert(session, Patient, result.patients)
    await _upsert(session, Encounter, result.encounters)
    await _upsert(session, Condition, result.conditions)
    await _upsert(session, Observation, result.observations)
    await _upsert(session, MedicationRequest, result.medication_requests)
    await _upsert(session, Procedure, result.procedures)
    await _upsert(session, DiagnosticReport, result.diagnostic_reports)
    await _upsert(session, AllergyIntolerance, result.allergies)
    await _upsert(session, RawResource, result.raw_resources)


async def _run_parse(run_id: int) -> int:
    async with _task_session() as session:
        run = await session.get(PipelineRun, run_id)
        if run is None:
            raise ValueError(f"pipeline_run {run_id} not found")

        run.status = "running"
        run.current_stage = "parse"
        await session.commit()
        publish_status(run_id, "parse", "running")

        try:
            result = parse_bundle(run.raw_bundle or {})
            await _persist(session, result)

            run.record_count = result.record_count
            run.error_count = result.error_count
            run.error_detail = {"parse_errors": result.errors, "skipped": result.skipped}
            run.status = "running"  # normalize stage follows in the chain
            run.current_stage = "parse"
            await session.commit()
            publish_status(
                run_id, "parse", "completed",
                record_count=result.record_count, error_count=result.error_count,
            )
        except Exception as exc:
            await session.rollback()
            run = await session.get(PipelineRun, run_id)
            run.status = "failed"
            run.error_detail = {"stage": "parse", "error": str(exc)}
            await session.commit()
            publish_status(run_id, "parse", "failed", error=str(exc))
            raise

    return run_id


async def _run_normalize(run_id: int) -> int:
    async with _task_session() as session:
        run = await session.get(PipelineRun, run_id)
        if run is None:
            raise ValueError(f"pipeline_run {run_id} not found")

        run.current_stage = "normalize"
        await session.commit()
        publish_status(run_id, "normalize", "running")

        try:
            stats = await normalize_records(session)
            detail = dict(run.error_detail or {})
            detail["normalize"] = stats
            run.error_detail = detail
            run.status = "completed"  # final stage until dedup/enrich (Inc 4)
            run.current_stage = "normalize"
            await session.commit()
            publish_status(run_id, "normalize", "completed", **stats)
        except Exception as exc:
            await session.rollback()
            run = await session.get(PipelineRun, run_id)
            run.status = "failed"
            run.error_detail = {"stage": "normalize", "error": str(exc)}
            await session.commit()
            publish_status(run_id, "normalize", "failed", error=str(exc))
            raise

    return run_id


@celery.task(name="pipeline.parse")
def parse_stage(run_id: int) -> int:
    return asyncio.run(_run_parse(run_id))


@celery.task(name="pipeline.normalize")
def normalize_stage(run_id: int) -> int:
    return asyncio.run(_run_normalize(run_id))
