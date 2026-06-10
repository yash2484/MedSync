"""Celery pipeline tasks.

Increment 1 wires only the ``parse`` stage end-to-end. normalize / deduplicate
/ enrich are appended to the chain in later increments (CLAUDE.md §9.5):

    parse.s(run_id) | normalize.s() | deduplicate.s() | enrich.s()

Each task updates the pipeline_runs row and publishes a status event. DB access
uses the async session driven via asyncio.run() — one event loop per task run,
which is safe under Celery's prefork pool.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert

from medsync.celery_app import celery
from medsync.db.session import async_session_factory
from medsync.models.database import Condition, Patient, PipelineRun
from medsync.pipeline.parser import ParseResult, parse_bundle
from medsync.pipeline.status import publish_status


async def _upsert_patients(session, patients) -> None:
    for p in patients:
        values = {
            "fhir_id": p.fhir_id,
            "family_name": p.family_name,
            "given_name": p.given_name,
            "gender": p.gender,
            "birth_date": p.birth_date,
            "address_line": p.address_line,
            "city": p.city,
            "state": p.state,
            "postal_code": p.postal_code,
            "has_incomplete_data": p.has_incomplete_data,
        }
        stmt = pg_insert(Patient).values(**values)
        update_cols = {k: stmt.excluded[k] for k in values if k != "fhir_id"}
        stmt = stmt.on_conflict_do_update(index_elements=["fhir_id"], set_=update_cols)
        await session.execute(stmt)


async def _upsert_conditions(session, conditions) -> None:
    for c in conditions:
        values = {
            "fhir_id": c.fhir_id,
            "patient_fhir_id": c.patient_fhir_id,
            "code": c.code,
            "system": c.system,
            "display": c.display,
            "clinical_status": c.clinical_status,
            "onset_date": c.onset_date,
            "has_incomplete_data": c.has_incomplete_data,
        }
        stmt = pg_insert(Condition).values(**values)
        update_cols = {k: stmt.excluded[k] for k in values if k != "fhir_id"}
        stmt = stmt.on_conflict_do_update(index_elements=["fhir_id"], set_=update_cols)
        await session.execute(stmt)


async def _run_parse(run_id: int) -> int:
    async with async_session_factory() as session:
        run = await session.get(PipelineRun, run_id)
        if run is None:
            raise ValueError(f"pipeline_run {run_id} not found")

        run.status = "running"
        run.current_stage = "parse"
        await session.commit()
        publish_status(run_id, "parse", "running")

        try:
            result: ParseResult = parse_bundle(run.raw_bundle or {})
            await _upsert_patients(session, result.patients)
            await _upsert_conditions(session, result.conditions)

            run.record_count = result.record_count
            run.error_count = result.error_count
            run.error_detail = {"parse_errors": result.errors, "skipped": result.skipped}
            run.status = "completed"  # spine: chain ends after parse for now
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


@celery.task(name="pipeline.parse")
def parse_stage(run_id: int) -> int:
    return asyncio.run(_run_parse(run_id))
