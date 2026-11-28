"""
env.py de Alembic — Fase 3.

Dos decisiones de este archivo, respecto a la plantilla por defecto que
genera `alembic init`:

1. La URL de conexión NO se lee de `alembic.ini` (que se dejó vacía a
   propósito). Se construye en runtime llamando a
   `infrastructure.config.cargar_configuracion_db()`, el mismo patrón ya
   usado para Jira/Xray/Ollama: un solo lugar que sabe leer `.env`, y que
   valida con un mensaje claro si falta alguna variable. Esto evita tener
   la contraseña de la base de datos en texto plano en un archivo que se
   versiona en git.

2. `target_metadata` apunta a `Base.metadata` de
   `infrastructure/db/models_orm.py`, no queda en `None`. Esto es lo que
   habilita `alembic revision --autogenerate`: Alembic compara el estado
   real de la base contra estas clases ORM y genera el script de migración
   automáticamente, en vez de tener que escribir cada `CREATE TABLE` a
   mano.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context


_RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
if str(_RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_PROYECTO))

from infrastructure.config import cargar_configuracion_db
from infrastructure.db.models_orm import Base


config = context.config


if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata


def _url_conexion() -> str:
    """
    Construye la URL de conexión real desde las variables DB_* de .env,
    reutilizando ConfiguracionDB (mismo patrón que Jira/Xray/Ollama). Se
    llama tanto en modo offline como online para no duplicar esta lógica.
    """
    return cargar_configuracion_db().url_sqlalchemy


def run_migrations_offline() -> None:
    """
    Modo offline: genera el SQL de la migración sin conectarse realmente
    a la base de datos (solo emite el string SQL a la salida). No es el
    modo que se usa en el flujo normal del proyecto, pero se mantiene por
    si en algún momento se necesita revisar el SQL exacto antes de
    aplicarlo contra producción.
    """
    context.configure(
        url=_url_conexion(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Modo online: se conecta de verdad a PostgreSQL (instalación nativa en
    Windows, ver spec sección 2) y aplica la migración. Este es el modo
    real que se usa en este proyecto.
    """
    configuracion_seccion = config.get_section(config.config_ini_section, {})
    configuracion_seccion["sqlalchemy.url"] = _url_conexion()

    connectable = engine_from_config(
        configuracion_seccion,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
