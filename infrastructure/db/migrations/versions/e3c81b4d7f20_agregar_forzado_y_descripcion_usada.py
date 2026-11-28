"""agregar generacion_forzada y descripcion_usada a historias_usuario

Revision ID: e3c81b4d7f20
Revises: b7e2f4a9c1d3
Create Date: 2026-09-16 00:00:00.000000

Los dos campos existen por el Quality Gate de la pantalla "Generar casos"
(Fase 2 §2.2), y los dos son de TRAZABILIDAD, no de funcionalidad:

- `generacion_forzada`: la HU no pasó el umbral de Vera y aun así se generó,
  por definición del alcance. Sin esta marca no hay forma de separar
  después "casos de HU aprobadas" de "casos de HU forzadas" en ningún
  indicador -- que es exactamente el problema que apareció con el lote de
  septiembre, donde el forzado se hizo bajando el umbral en el .env y no
  quedó registrado en ninguna parte.

- `descripcion_usada`: el texto con el que Vera evaluó y Gio generó, cuando
  se editó en pantalla. La HU en Jira NO se modifica (decisión
  confirmada), así que sin este campo quedaría un caso generado a partir de
  un texto que no existe en ningún lado. NULL significa "se usó la
  descripción tal como vino de Jira".

Ambos son aditivos y con default, así que las filas históricas quedan
válidas: `generacion_forzada=false` (ninguna generación anterior a esta
pantalla pudo forzarse) y `descripcion_usada=NULL` (se usó la de Jira).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3c81b4d7f20'
down_revision: Union[str, Sequence[str], None] = 'b7e2f4a9c1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "historias_usuario",
        sa.Column(
            "generacion_forzada",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "historias_usuario",
        sa.Column("descripcion_usada", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("historias_usuario", "descripcion_usada")
    op.drop_column("historias_usuario", "generacion_forzada")
