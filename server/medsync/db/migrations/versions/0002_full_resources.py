"""full resource set: encounters, observations, meds, procedures, reports, allergies, raw

Revision ID: 0002_full_resources
Revises: 0001_initial
Create Date: 2026-06-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_full_resources"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _patient_fk() -> sa.Column:
    return sa.Column("patient_fhir_id", sa.String(64), nullable=True)


def upgrade() -> None:
    op.create_table(
        "encounters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fhir_id", sa.String(64), nullable=False),
        _patient_fk(),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("encounter_class", sa.String(32), nullable=True),
        sa.Column("type_code", sa.String(64), nullable=True),
        sa.Column("type_display", sa.String(512), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("reason_display", sa.String(512), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_incomplete_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.UniqueConstraint("fhir_id", name="uq_encounters_fhir_id"),
        sa.ForeignKeyConstraint(["patient_fhir_id"], ["patients.fhir_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_encounters_fhir_id", "encounters", ["fhir_id"])
    op.create_index("ix_encounters_patient_fhir_id", "encounters", ["patient_fhir_id"])

    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fhir_id", sa.String(64), nullable=False),
        _patient_fk(),
        sa.Column("encounter_fhir_id", sa.String(64), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("system", sa.String(256), nullable=True),
        sa.Column("display", sa.String(512), nullable=True),
        sa.Column("value_number", sa.Float(), nullable=True),
        sa.Column("value_unit", sa.String(64), nullable=True),
        sa.Column("value_string", sa.String(512), nullable=True),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("has_incomplete_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.UniqueConstraint("fhir_id", name="uq_observations_fhir_id"),
        sa.ForeignKeyConstraint(["patient_fhir_id"], ["patients.fhir_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_observations_fhir_id", "observations", ["fhir_id"])
    op.create_index("ix_observations_patient_fhir_id", "observations", ["patient_fhir_id"])
    op.create_index("ix_observations_encounter_fhir_id", "observations", ["encounter_fhir_id"])

    op.create_table(
        "medication_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fhir_id", sa.String(64), nullable=False),
        _patient_fk(),
        sa.Column("encounter_fhir_id", sa.String(64), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("system", sa.String(256), nullable=True),
        sa.Column("display", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("authored_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_incomplete_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.UniqueConstraint("fhir_id", name="uq_medication_requests_fhir_id"),
        sa.ForeignKeyConstraint(["patient_fhir_id"], ["patients.fhir_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_medication_requests_fhir_id", "medication_requests", ["fhir_id"])
    op.create_index("ix_medication_requests_patient_fhir_id", "medication_requests", ["patient_fhir_id"])

    op.create_table(
        "procedures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fhir_id", sa.String(64), nullable=False),
        _patient_fk(),
        sa.Column("encounter_fhir_id", sa.String(64), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("system", sa.String(256), nullable=True),
        sa.Column("display", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("performed_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_incomplete_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.UniqueConstraint("fhir_id", name="uq_procedures_fhir_id"),
        sa.ForeignKeyConstraint(["patient_fhir_id"], ["patients.fhir_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_procedures_fhir_id", "procedures", ["fhir_id"])
    op.create_index("ix_procedures_patient_fhir_id", "procedures", ["patient_fhir_id"])

    op.create_table(
        "diagnostic_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fhir_id", sa.String(64), nullable=False),
        _patient_fk(),
        sa.Column("encounter_fhir_id", sa.String(64), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("system", sa.String(256), nullable=True),
        sa.Column("display", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_incomplete_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.UniqueConstraint("fhir_id", name="uq_diagnostic_reports_fhir_id"),
        sa.ForeignKeyConstraint(["patient_fhir_id"], ["patients.fhir_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_diagnostic_reports_fhir_id", "diagnostic_reports", ["fhir_id"])
    op.create_index("ix_diagnostic_reports_patient_fhir_id", "diagnostic_reports", ["patient_fhir_id"])

    op.create_table(
        "allergy_intolerances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fhir_id", sa.String(64), nullable=False),
        _patient_fk(),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("system", sa.String(256), nullable=True),
        sa.Column("display", sa.String(512), nullable=True),
        sa.Column("clinical_status", sa.String(64), nullable=True),
        sa.Column("criticality", sa.String(32), nullable=True),
        sa.Column("has_incomplete_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.UniqueConstraint("fhir_id", name="uq_allergy_intolerances_fhir_id"),
        sa.ForeignKeyConstraint(["patient_fhir_id"], ["patients.fhir_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_allergy_intolerances_fhir_id", "allergy_intolerances", ["fhir_id"])
    op.create_index("ix_allergy_intolerances_patient_fhir_id", "allergy_intolerances", ["patient_fhir_id"])

    op.create_table(
        "raw_resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fhir_id", sa.String(64), nullable=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("patient_fhir_id", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("fhir_id", name="uq_raw_resources_fhir_id"),
    )
    op.create_index("ix_raw_resources_fhir_id", "raw_resources", ["fhir_id"])
    op.create_index("ix_raw_resources_resource_type", "raw_resources", ["resource_type"])
    op.create_index("ix_raw_resources_patient_fhir_id", "raw_resources", ["patient_fhir_id"])


def downgrade() -> None:
    op.drop_table("raw_resources")
    op.drop_table("allergy_intolerances")
    op.drop_table("diagnostic_reports")
    op.drop_table("procedures")
    op.drop_table("medication_requests")
    op.drop_table("observations")
    op.drop_table("encounters")
