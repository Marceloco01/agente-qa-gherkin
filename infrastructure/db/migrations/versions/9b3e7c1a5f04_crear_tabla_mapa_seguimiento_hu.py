"""crear tabla mapa seguimiento hu

Revision ID: 9b3e7c1a5f04
Revises: d4f28a91e6c3
Create Date: 2026-08-28 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9b3e7c1a5f04'
down_revision: Union[str, Sequence[str], None] = 'd4f28a91e6c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mapa_seguimiento_hu",
        sa.Column("hu_key", sa.String(length=50), primary_key=True),
        sa.Column("grupo", sa.String(length=20), nullable=False),
        sa.Column("tiempo_proceso_horas", sa.Float(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column(
            "fecha_agregado",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_mapa_seguimiento_hu_grupo", "mapa_seguimiento_hu", ["grupo"]
    )


def downgrade() -> None:
    op.drop_index("ix_mapa_seguimiento_hu_grupo", table_name="mapa_seguimiento_hu")
    op.drop_table("mapa_seguimiento_hu")
