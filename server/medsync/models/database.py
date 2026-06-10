"""SQLAlchemy ORM models.

Phase 1 / Increment 1 scope: pipeline_runs, patients, conditions. Additional
core resource types + raw_resources land in Increment 2; patient_links (dedup)
in Increment 4.

Invariants (CLAUDE.md §9.4): idempotent upserts on fhir_id, soft deletes only
(deleted_at), every pipeline stage updates pipeline_runs.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, String, func
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
