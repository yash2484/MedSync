"""normalization columns on conditions + observations

Revision ID: 0003_normalization
Revises: 0002_full_resources
Create Date: 2026-06-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_normalization"
down_revision: Union[str, None] = "0002_full_resources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conditions", sa.Column("snomed_code", sa.String(64), nullable=True))
    op.add_column("conditions", sa.Column("icd10_code", sa.String(64), nullable=True))
    op.add_column("conditions", sa.Column("mapping_confidence", sa.Float(), nullable=True))
    op.add_column("conditions", sa.Column("mapping_source", sa.String(64), nullable=True))
    op.add_column("conditions", sa.Column("normalized", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("conditions", sa.Column("normalization_failed", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.add_column("observations", sa.Column("loinc_code", sa.String(32), nullable=True))
    op.add_column("observations", sa.Column("canonical_display", sa.String(512), nullable=True))
    op.add_column("observations", sa.Column("value_canonical", sa.Float(), nullable=True))
    op.add_column("observations", sa.Column("value_canonical_unit", sa.String(64), nullable=True))
    op.add_column("observations", sa.Column("normalized", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("observations", sa.Column("normalization_failed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_index("ix_observations_loinc_code", "observations", ["loinc_code"])


def downgrade() -> None:
    op.drop_index("ix_observations_loinc_code", table_name="observations")
    for col in ("normalization_failed", "normalized", "value_canonical_unit", "value_canonical", "canonical_display", "loinc_code"):
        op.drop_column("observations", col)
    for col in ("normalization_failed", "normalized", "mapping_source", "mapping_confidence", "icd10_code", "snomed_code"):
        op.drop_column("conditions", col)
