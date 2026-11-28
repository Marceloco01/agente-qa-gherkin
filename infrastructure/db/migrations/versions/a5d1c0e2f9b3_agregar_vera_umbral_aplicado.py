"""agregar vera_umbral_aplicado a historias_usuario

Revision ID: a5d1c0e2f9b3
Revises: e3c81b4d7f20
Create Date: 2026-11-26 00:00:00.000000

Guarda el umbral de Vera vigente en cada evaluación. Hasta la v1.0.1 el
umbral solo vivía en el .env, así que la reducción temporal a 35 del lote de
septiembre no quedó registrada. Las filas anteriores quedan en NULL (sin
dato retroactivo).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5d1c0e2f9b3"
down_revision: Union[str, Sequence[str], None] = "e3c81b4d7f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "historias_usuario",
        sa.Column("vera_umbral_aplicado", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("historias_usuario", "vera_umbral_aplicado")
