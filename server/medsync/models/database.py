"""SQLAlchemy ORM models.

Phase 1 / Increment 1 scope: pipeline_runs, patients, conditions. Additional
core resource types + raw_resources land in Increment 2; patient_links (dedup)
in Increment 4.

Invariants (CLAUDE.md §9.4): idempotent upserts on fhir_id, soft deletes only
(deleted_at), every pipeline stage updates pipeline_runs.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from medsync.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PipelineRun(TimestampMixin, Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_filename: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(32))
    record_count: Mapped[int] = mapped_column(default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(default=0, nullable=False)
    error_detail: Mapped[dict | None] = mapped_column(JSONB)
    # Raw uploaded bundle, read by the worker. Avoids a shared filesystem.
    raw_bundle: Mapped[dict | None] = mapped_column(JSONB)


class Patient(TimestampMixin, Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    fhir_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    family_name: Mapped[str | None] = mapped_column(String(256))
    given_name: Mapped[str | None] = mapped_column(String(256))
    gender: Mapped[str | None] = mapped_column(String(32))
    birth_date: Mapped[date | None] = mapped_column()
    address_line: Mapped[str | None] = mapped_column(String(512))
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(64))
    postal_code: Mapped[str | None] = mapped_column(String(32))

    has_incomplete_data: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Deduplication (Increment 4)
    cluster_id: Mapped[str | None] = mapped_column(String(64), index=True)
    match_zone: Mapped[str | None] = mapped_column(String(32))

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conditions: Mapped[list[Condition]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )


class Condition(TimestampMixin, Base):
    __tablename__ = "conditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    fhir_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_fhir_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.fhir_id", ondelete="CASCADE"), index=True
    )

    code: Mapped[str | None] = mapped_column(String(64))
    system: Mapped[str | None] = mapped_column(String(256))
    display: Mapped[str | None] = mapped_column(String(512))
    clinical_status: Mapped[str | None] = mapped_column(String(64))
    onset_date: Mapped[date | None] = mapped_column()

    has_incomplete_data: Mapped[bool] = mapped_column(default=False, nullable=False)

    patient: Mapped[Patient | None] = relationship(back_populates="conditions")


# --------------------------------------------------------------------------- #
# Increment 2: remaining core resource types + raw_resources
# encounter_fhir_id is a SOFT reference (indexed string, no FK) so an
# Observation referencing an encounter absent from the bundle never fails to
# insert (CLAUDE.md flag-don't-reject policy).
# --------------------------------------------------------------------------- #
class Encounter(TimestampMixin, Base):
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(primary_key=True)
    fhir_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_fhir_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.fhir_id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str | None] = mapped_column(String(32))
    encounter_class: Mapped[str | None] = mapped_column(String(32))
    type_code: Mapped[str | None] = mapped_column(String(64))
    type_display: Mapped[str | None] = mapped_column(String(512))
    reason_code: Mapped[str | None] = mapped_column(String(64))
    reason_display: Mapped[str | None] = mapped_column(String(512))
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    has_incomplete_data: Mapped[bool] = mapped_column(default=False, nullable=False)


class Observation(TimestampMixin, Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    fhir_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_fhir_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.fhir_id", ondelete="CASCADE"), index=True
    )
    encounter_fhir_id: Mapped[str | None] = mapped_column(String(64), index=True)
    code: Mapped[str | None] = mapped_column(String(64))
    system: Mapped[str | None] = mapped_column(String(256))
    display: Mapped[str | None] = mapped_column(String(512))
    value_number: Mapped[float | None] = mapped_column(Float)
    value_unit: Mapped[str | None] = mapped_column(String(64))
    value_string: Mapped[str | None] = mapped_column(String(512))
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(32))
    has_incomplete_data: Mapped[bool] = mapped_column(default=False, nullable=False)


class MedicationRequest(TimestampMixin, Base):
    __tablename__ = "medication_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    fhir_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_fhir_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.fhir_id", ondelete="CASCADE"), index=True
    )
    encounter_fhir_id: Mapped[str | None] = mapped_column(String(64), index=True)
    code: Mapped[str | None] = mapped_column(String(64))
    system: Mapped[str | None] = mapped_column(String(256))
    display: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(32))
    authored_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    has_incomplete_data: Mapped[bool] = mapped_column(default=False, nullable=False)


class Procedure(TimestampMixin, Base):
    __tablename__ = "procedures"

    id: Mapped[int] = mapped_column(primary_key=True)
    fhir_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_fhir_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.fhir_id", ondelete="CASCADE"), index=True
    )
    encounter_fhir_id: Mapped[str | None] = mapped_column(String(64), index=True)
    code: Mapped[str | None] = mapped_column(String(64))
    system: Mapped[str | None] = mapped_column(String(256))
    display: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(32))
    performed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    has_incomplete_data: Mapped[bool] = mapped_column(default=False, nullable=False)


class DiagnosticReport(TimestampMixin, Base):
    __tablename__ = "diagnostic_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    fhir_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_fhir_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.fhir_id", ondelete="CASCADE"), index=True
    )
    encounter_fhir_id: Mapped[str | None] = mapped_column(String(64), index=True)
    code: Mapped[str | None] = mapped_column(String(64))
    system: Mapped[str | None] = mapped_column(String(256))
    display: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(32))
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    has_incomplete_data: Mapped[bool] = mapped_column(default=False, nullable=False)


class AllergyIntolerance(TimestampMixin, Base):
    __tablename__ = "allergy_intolerances"

    id: Mapped[int] = mapped_column(primary_key=True)
    fhir_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_fhir_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.fhir_id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str | None] = mapped_column(String(64))
    system: Mapped[str | None] = mapped_column(String(256))
    display: Mapped[str | None] = mapped_column(String(512))
    clinical_status: Mapped[str | None] = mapped_column(String(64))
    criticality: Mapped[str | None] = mapped_column(String(32))
    has_incomplete_data: Mapped[bool] = mapped_column(default=False, nullable=False)


class RawResource(TimestampMixin, Base):
    """Deferred FHIR resource types stored verbatim for Phase-4 promotion."""

    __tablename__ = "raw_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    fhir_id: Mapped[str | None] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    patient_fhir_id: Mapped[str | None] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
