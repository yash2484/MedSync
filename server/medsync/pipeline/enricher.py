"""Stage 4 — patient enrichment.  [AI-ASSISTED]

Pure `compute_summary` builds a per-patient rollup; the DB sweep stores it as a
JSONB summary. Flag-and-continue on partial data (CLAUDE.md §9.1).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from medsync.models.database import Condition, Encounter, MedicationRequest, Patient


def compute_summary(conditions, medications, encounters) -> dict:
    active = [c for c in conditions if (c.clinical_status or "").lower() == "active"]
    starts = [e.period_start for e in encounters if getattr(e, "period_start", None)]
    last = max(starts) if starts else None
    return {
        "condition_count": len(conditions),
        "active_condition_count": len(active),
        "active_conditions": [c.display for c in active if c.display],
        "medication_count": len(medications),
        "encounter_count": len(encounters),
        "last_encounter_date": last.date().isoformat() if last else None,
    }


async def enrich_records(session: AsyncSession) -> dict:
    patients = (
        await session.execute(select(Patient).where(Patient.deleted_at.is_(None)))
    ).scalars().all()
    enriched = 0
    for p in patients:
        conditions = (
            await session.execute(select(Condition).where(Condition.patient_fhir_id == p.fhir_id))
        ).scalars().all()
        meds = (
            await session.execute(
                select(MedicationRequest).where(MedicationRequest.patient_fhir_id == p.fhir_id)
            )
        ).scalars().all()
        encs = (
            await session.execute(select(Encounter).where(Encounter.patient_fhir_id == p.fhir_id))
        ).scalars().all()
        p.summary = compute_summary(conditions, meds, encs)
        enriched += 1
    await session.commit()
    return {"patients_enriched": enriched}
