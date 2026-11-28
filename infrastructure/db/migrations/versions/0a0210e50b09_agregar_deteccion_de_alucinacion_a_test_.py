"""agregar deteccion de alucinacion a test_cases

Revision ID: 0a0210e50b09
Revises: 0c951ffe71f7
Create Date: 2026-06-30 01:44:06.411540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0a0210e50b09'
down_revision: Union[str, Sequence[str], None] = '0c951ffe71f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "test_cases",
        sa.Column("alucinacion_detectada", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "test_cases",
        sa.Column("alucinacion_detalle", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("test_cases", "alucinacion_detalle")
    op.drop_column("test_cases", "alucinacion_detectada")
