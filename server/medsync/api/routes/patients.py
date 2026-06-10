"""Patient registry endpoints (FHIR-native search expands in Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from medsync.db.session import get_session
from medsync.models.database import Patient
from medsync.models.schemas import PatientDetail, PatientOut

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


@router.get("", response_model=list[PatientOut])
async def list_patients(
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[Patient]:
    stmt = (
        select(Patient)
        .where(Patient.deleted_at.is_(None))
        .order_by(Patient.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{patient_id}", response_model=PatientDetail)
async def get_patient(
    patient_id: int, session: AsyncSession = Depends(get_session)
) -> Patient:
    stmt = (
        select(Patient)
        .where(Patient.id == patient_id, Patient.deleted_at.is_(None))
        .options(selectinload(Patient.conditions))
    )
    patient = (await session.execute(stmt)).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=404, detail="patient not found")
    return patient
