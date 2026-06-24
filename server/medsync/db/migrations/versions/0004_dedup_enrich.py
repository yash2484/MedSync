"""dedup + enrich: patient_links table, patients.summary

Revision ID: 0004_dedup_enrich
Revises: 0003_normalization
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_dedup_enrich"
down_revision: Union[str, None] = "0003_normalization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("summary", postgresql.JSONB(), nullable=True))
    op.create_table(
        "patient_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_a_fhir_id", sa.String(64), nullable=False),
        sa.Column("patient_b_fhir_id", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("match_zone", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_patient_links_a", "patient_links", ["patient_a_fhir_id"])
    op.create_index("ix_patient_links_b", "patient_links", ["patient_b_fhir_id"])


def downgrade() -> None:
    op.drop_table("patient_links")
    op.drop_column("patients", "summary")
