"""crear tabla seguimiento hu metricas

Revision ID: 4a726066a1e4
Revises: f1a6c92d4b17
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4a726066a1e4'
down_revision: Union[str, Sequence[str], None] = 'f1a6c92d4b17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seguimiento_hu_metricas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hu_key", sa.String(length=50), nullable=False),
        sa.Column("fecha_certificacion_terminada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("num_criterios_identificados", sa.Integer(), nullable=True),
        sa.Column("num_tests", sa.Integer(), nullable=True),
        sa.Column("indice_cobertura_densidad_pct", sa.Float(), nullable=True),
        sa.Column("indice_cobertura_real_pct", sa.Float(), nullable=True),
        sa.Column("criterios_no_cubiertos", sa.Text(), nullable=True),
        sa.Column("indice_ejecucion_pct", sa.Float(), nullable=True),
        sa.Column("test_pass_rate_pct", sa.Float(), nullable=True),
        sa.Column("num_defectos_detectados", sa.Integer(), nullable=True),
        sa.Column("num_defectos_resueltos", sa.Integer(), nullable=True),
        sa.Column("defectos_por_severidad", sa.String(length=200), nullable=True),
        sa.Column("test_plan_keys", sa.String(length=300), nullable=True),
        sa.Column("aviso", sa.Text(), nullable=True),
        sa.Column(
            "fecha_medicion",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_seguimiento_hu_metricas_hu_key", "seguimiento_hu_metricas", ["hu_key"]
    )
    op.create_index(
        "ix_seguimiento_hu_metricas_fecha_certificacion_terminada",
        "seguimiento_hu_metricas", ["fecha_certificacion_terminada"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_seguimiento_hu_metricas_fecha_certificacion_terminada",
        table_name="seguimiento_hu_metricas",
    )
    op.drop_index("ix_seguimiento_hu_metricas_hu_key", table_name="seguimiento_hu_metricas")
    op.drop_table("seguimiento_hu_metricas")
