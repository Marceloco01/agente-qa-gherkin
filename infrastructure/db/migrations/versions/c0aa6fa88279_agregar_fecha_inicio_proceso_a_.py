"""agregar fecha inicio proceso a historias usuario

Revision ID: c0aa6fa88279
Revises: 0a0210e50b09
Create Date: 2026-07-14 02:02:52.960384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c0aa6fa88279'
down_revision: Union[str, Sequence[str], None] = '0a0210e50b09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "historias_usuario",
        sa.Column(
            "fecha_inicio_proceso",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("historias_usuario", "fecha_inicio_proceso")
