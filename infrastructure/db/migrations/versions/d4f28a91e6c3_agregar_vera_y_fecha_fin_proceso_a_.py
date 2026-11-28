"""agregar vera y fecha fin proceso a historias usuario

Revision ID: d4f28a91e6c3
Revises: c0aa6fa88279
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f28a91e6c3'
down_revision: Union[str, Sequence[str], None] = 'c0aa6fa88279'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "historias_usuario",
        sa.Column("fecha_fin_proceso", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "historias_usuario",
        sa.Column("vera_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "historias_usuario",
        sa.Column("vera_aprobada", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "historias_usuario",
        sa.Column("vera_motivo_bloqueo", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("historias_usuario", "vera_motivo_bloqueo")
    op.drop_column("historias_usuario", "vera_aprobada")
    op.drop_column("historias_usuario", "vera_score")
    op.drop_column("historias_usuario", "fecha_fin_proceso")
