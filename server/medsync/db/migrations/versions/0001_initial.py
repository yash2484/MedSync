"""initial: pipeline_runs, patients, conditions

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bundle_filename", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("current_stage", sa.String(32), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_detail", postgresql.JSONB(), nullable=True),
        sa.Column("raw_bundle", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fhir_id", sa.String(64), nullable=False),
        sa.Column("family_name", sa.String(256), nullable=True),
        sa.Column("given_name", sa.String(256), nullable=True),
        sa.Column("gender", sa.String(32), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("address_line", sa.String(512), nullable=True),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("postal_code", sa.String(32), nullable=True),
        sa.Column("has_incomplete_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cluster_id", sa.String(64), nullable=True),
        sa.Column("match_zone", sa.String(32), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("fhir_id", name="uq_patients_fhir_id"),
    )
    op.create_index("ix_patients_fhir_id", "patients", ["fhir_id"])
    op.create_index("ix_patients_cluster_id", "patients", ["cluster_id"])

    op.create_table(
        "conditions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fhir_id", sa.String(64), nullable=False),
        sa.Column("patient_fhir_id", sa.String(64), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("system", sa.String(256), nullable=True),
        sa.Column("display", sa.String(512), nullable=True),
        sa.Column("clinical_status", sa.String(64), nullable=True),
        sa.Column("onset_date", sa.Date(), nullable=True),
        sa.Column("has_incomplete_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("fhir_id", name="uq_conditions_fhir_id"),
        sa.ForeignKeyConstraint(
            ["patient_fhir_id"], ["patients.fhir_id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_conditions_fhir_id", "conditions", ["fhir_id"])
    op.create_index("ix_conditions_patient_fhir_id", "conditions", ["patient_fhir_id"])


def downgrade() -> None:
    op.drop_table("conditions")
    op.drop_table("patients")
    op.drop_table("pipeline_runs")
