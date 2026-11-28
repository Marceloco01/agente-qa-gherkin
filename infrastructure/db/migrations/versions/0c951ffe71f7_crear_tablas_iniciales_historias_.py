"""crear tablas iniciales: historias_usuario, test_cases, mensajes_feedback, embeddings_historicos

Revision ID: 0c951ffe71f7
Revises: 
Create Date: 2026-06-29 16:52:56.564704

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = '0c951ffe71f7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _asegurar_extension_vector() -> None:
    """
    La tabla `embeddings_historicos` usa el tipo `vector` de pgvector, que
    solo existe si la extensión está activa en esta base. Si ya la activó un
    administrador, no se hace nada. Si no, se intenta activarla (requiere
    superusuario); si el usuario no tiene permiso, se corta con un mensaje
    que dice exactamente qué ejecutar.
    """
    if context.is_offline_mode():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        return
    conexion = op.get_bind()
    activa = conexion.execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    if activa:
        return
    try:
        conexion.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:
        raise RuntimeError(
            "La extensión pgvector no está activa en esta base y el usuario "
            "de la aplicación no tiene permiso para activarla. Ejecute una vez, "
            "como superusuario (por ejemplo, postgres):\n\n"
            "    psql -U postgres -d agente_qa -c \"CREATE EXTENSION IF NOT EXISTS vector;\"\n\n"
            "y vuelva a correr `alembic upgrade head`. Si el comando dice que la "
            "extensión no está disponible, falta instalar pgvector en el servidor "
            "PostgreSQL (ver README, sección Base de datos)."
        ) from exc


def upgrade() -> None:
    """Upgrade schema."""

    _asegurar_extension_vector()

    op.create_table('embeddings_historicos',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key_test', sa.String(length=50), nullable=False),
    sa.Column('key_te', sa.String(length=50), nullable=True),
    sa.Column('key_tp', sa.String(length=50), nullable=True),
    sa.Column('hu_key', sa.String(length=50), nullable=True),
    sa.Column('resumen', sa.Text(), nullable=False),
    sa.Column('embedding', Vector(768), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_embeddings_historicos_key_test'), 'embeddings_historicos', ['key_test'], unique=True)
    op.create_table('historias_usuario',
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('titulo', sa.String(length=500), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('test_plan_key', sa.String(length=50), nullable=True),
    sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('test_cases',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('hu_key', sa.String(length=50), nullable=False),
    sa.Column('titulo', sa.String(length=500), nullable=False),
    sa.Column('gherkin', sa.Text(), nullable=False),
    sa.Column('estado', sa.String(length=30), nullable=False),
    sa.Column('xray_test_key', sa.String(length=50), nullable=True),
    sa.Column('version_contenido', sa.Integer(), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['hu_key'], ['historias_usuario.key'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_test_cases_estado'), 'test_cases', ['estado'], unique=False)
    op.create_index(op.f('ix_test_cases_hu_key'), 'test_cases', ['hu_key'], unique=False)
    op.create_table('mensajes_feedback',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('test_case_id', sa.Uuid(), nullable=False),
    sa.Column('autor', sa.String(length=20), nullable=False),
    sa.Column('texto', sa.Text(), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['test_case_id'], ['test_cases.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mensajes_feedback_test_case_id'), 'mensajes_feedback', ['test_case_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f('ix_mensajes_feedback_test_case_id'), table_name='mensajes_feedback')
    op.drop_table('mensajes_feedback')
    op.drop_index(op.f('ix_test_cases_hu_key'), table_name='test_cases')
    op.drop_index(op.f('ix_test_cases_estado'), table_name='test_cases')
    op.drop_table('test_cases')
    op.drop_table('historias_usuario')
    op.drop_index(op.f('ix_embeddings_historicos_key_test'), table_name='embeddings_historicos')
    op.drop_table('embeddings_historicos')
