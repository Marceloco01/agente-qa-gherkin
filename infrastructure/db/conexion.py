"""
Conexión y manejo de sesiones de SQLAlchemy — Fase 3.

Centraliza la creación del engine y de las sesiones para que
`SqlAlchemyRepository` y, más adelante, `PostgresPgvectorAdapter` no
dupliquen esta lógica cada uno por su lado.

Patrón de sesión elegido (Decisión de diseño): "sesión por
bloque", no "sesión por operación". Quien orquesta (un caso de uso en
`application/`, ej. `generar_test_cases.py`) abre el bloque `with` UNA sola
vez y, dentro de ese bloque, llama a los métodos del Repository que
necesite. Si cualquier operación dentro del bloque lanza una excepción,
TODO se revierte junto -- evita el escenario real que se buscaba
prevenir: guardar la HU pero solo 2 de 5 test cases si el tercero falla.

Uso típico desde un caso de uso:

    from infrastructure.db.conexion import obtener_sesion
    from adapters.repository.sqlalchemy_repository import SqlAlchemyRepository

    with obtener_sesion() as sesion:
        repository = SqlAlchemyRepository(sesion)
        repository.guardar_hu(hu)
        repository.guardar_test_cases(test_cases)
        # Si todo lo anterior no lanzó excepción, se hace commit acá abajo,
        # al salir del bloque `with` sin errores.

Si algo dentro del bloque lanza una excepción, `obtener_sesion()` hace
rollback automáticamente antes de relanzar la excepción -- el caller no
tiene que escribir su propio try/except solo para revertir.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from infrastructure.config import cargar_configuracion_db

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _obtener_engine() -> Engine:
    """
    Crea el engine una sola vez por proceso (patrón singleton simple).

    No se crea un engine nuevo en cada llamada: un Engine de SQLAlchemy ya
    administra internamente un pool de conexiones, así que crear varios
    engines sería desperdiciar ese pooling y abrir más conexiones de las
    necesarias contra Postgres.
    """
    global _engine
    if _engine is None:
        configuracion = cargar_configuracion_db()
        _engine = create_engine(configuracion.url_sqlalchemy)
    return _engine


def _obtener_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=_obtener_engine())
    return _SessionFactory


@contextmanager
def obtener_sesion() -> Iterator[Session]:
    """
    Context manager que entrega una sesión de SQLAlchemy y administra su
    ciclo de vida completo: commit automático si el bloque `with` termina
    sin errores, rollback automático si lanza una excepción, y cierre de
    la sesión en ambos casos.

    Esto es lo que habilita la atomicidad "todo o nada" que el usuario
    pidió explícitamente para `guardar_hu()` + `guardar_test_cases()`.
    """
    sesion = _obtener_session_factory()()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()
