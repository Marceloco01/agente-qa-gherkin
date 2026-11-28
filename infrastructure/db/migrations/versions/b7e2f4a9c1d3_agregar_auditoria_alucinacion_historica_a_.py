"""agregar auditoria de alucinacion historica a test_cases

Revision ID: b7e2f4a9c1d3
Revises: 4a726066a1e4
Create Date: 2026-09-02 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e2f4a9c1d3'
down_revision: Union[str, Sequence[str], None] = '4a726066a1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "test_cases",
        sa.Column(
            "alucinacion_detectada_alguna_vez",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "test_cases",
        sa.Column("version_contenido_al_detectar_alucinacion", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("test_cases", "version_contenido_al_detectar_alucinacion")
    op.drop_column("test_cases", "alucinacion_detectada_alguna_vez")
