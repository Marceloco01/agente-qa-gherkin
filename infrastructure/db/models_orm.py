"""
Modelos ORM (SQLAlchemy) — Fase 3.

Mapea las entidades de `domain/models.py` a tablas relacionales reales en
PostgreSQL. Esta capa vive en `infrastructure/`, NO en `domain/`, porque
acopla intencionalmente a SQLAlchemy — algo que `domain/models.py` (puras
dataclasses) tiene prohibido hacer (ver regla de dependencia, spec sección
3.2: las flechas de importación solo apuntan hacia adentro).

`adapters/repository/sqlalchemy_repository.py` (siguiente paso) es quien
traduce entre estas clases ORM y las dataclasses de dominio — ningún otro
módulo del proyecto debe importar de aquí salvo ese adapter y las
migraciones de Alembic.

Decisión de diseño para este esquema:
- `estado` en TestCase: VARCHAR, no ENUM nativo de Postgres. Motivo: el set
  de estados puede crecer en Fase 4/5 (ej. un estado intermedio de
  verificación de alucinación) y un VARCHAR evita tener que migrar el tipo
  ENUM de la base de datos cada vez que el dominio agregue un valor nuevo.
  La validación de qué valores son válidos sigue viviendo en el `Enum` de
  Python (`EstadoTestCase`), que ya es robusto.
- `historial_feedback`: tabla relacionada (`mensajes_feedback`), no columna
  JSON. Motivo: permite auditar/ordenar mensajes individualmente y es más
  nativo de SQLAlchemy: el costo de un JOIN extra es trivial en este
  volumen de datos.
- Timestamps de auditoría (`fecha_creacion`, `fecha_actualizacion`) en todas
  las tablas principales, aunque la spec original no los pida
  explícitamente — útil para Fase 5 (Dashboard).
- Embeddings históricos del ETL del Excel viven en tabla separada
  (`embeddings_historicos`), no junto a `test_cases`. Motivo: el corpus
  histórico (4147 casos validados) tiene un ciclo de vida distinto al de
  los TestCase que el agente genera y que pasan por pendiente → aprobado →
  rechazado → subido_a_xray. Mezclarlos obligaría a filtrar constantemente
  por origen y complicaría qué pasa con el embedding de un TestCase
  descartado.
- Dimensión del vector: 768, confirmado contra una llamada real a
  `nomic-embed-text` en la instancia de Ollama del usuario (no asumido
  desde documentación).

Punto pendiente de definición antes de conectar esto al flujo
real (ver spec sección 14): en qué momento exacto se llama a
`Repository.guardar_hu()` / `guardar_test_cases()`. Ya confirmado: al
generar (apenas el LLM produce los test cases), no al aprobar ni al subir
a Xray.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


DIMENSION_EMBEDDING = 768


def _ahora_utc() -> datetime:
    """
    Devuelve la hora actual en UTC.

    Se usa como `default`/`onupdate` de los timestamps de auditoría.
    Centralizado en una función (en vez de `datetime.utcnow` directo en
    cada columna) para que las firmas de columna sean más legibles y para
    tener un solo lugar que tocar si en el futuro se decide registrar en
    otra zona horaria.
    """
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Clase base declarativa de SQLAlchemy para todos los modelos ORM."""

    pass


class HistoriaUsuarioORM(Base):
    """
    Tabla `historias_usuario`.

    Mapea `domain.models.HistoriaUsuario`. La PK es la `key` de Jira
    (ej. "PRJ-14") y no un id autogenerado: la key de Jira ya es el
    identificador natural y único de la HU en el sistema de origen, así
    que inventar un id propio sería redundante y complicaría las
    consultas (siempre se busca por key, nunca por un id interno).
    """

    __tablename__ = "historias_usuario"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)


    test_plan_key: Mapped[str | None] = mapped_column(String(50), nullable=True)


    fecha_inicio_proceso: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


    fecha_fin_proceso: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


    vera_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vera_aprobada: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    vera_motivo_bloqueo: Mapped[str | None] = mapped_column(Text, nullable=True)

    vera_umbral_aplicado: Mapped[int | None] = mapped_column(Integer, nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora_utc, nullable=False
    )


    generacion_forzada: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False,
    )
    descripcion_usada: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_ahora_utc,
        onupdate=_ahora_utc,
        nullable=False,
    )

    test_cases: Mapped[list["TestCaseORM"]] = relationship(
        back_populates="historia_usuario", cascade="all, delete-orphan"
    )


class TestCaseORM(Base):
    """
    Tabla `test_cases`.

    Mapea `domain.models.TestCase`. La PK es el mismo `id` (UUID) que ya
    existe en el dominio — no se inventa un id distinto a nivel de
    persistencia, así el adapter de Repository no tiene que hacer
    traducción de identidad entre dominio y base de datos.
    """

    __tablename__ = "test_cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    hu_key: Mapped[str] = mapped_column(
        String(50), ForeignKey("historias_usuario.key"), nullable=False, index=True
    )

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    gherkin: Mapped[str] = mapped_column(Text, nullable=False)


    estado: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    xray_test_key: Mapped[str | None] = mapped_column(String(50), nullable=True)


    version_contenido: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


    alucinacion_detectada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alucinacion_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)


    alucinacion_detectada_alguna_vez: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


    version_contenido_al_detectar_alucinacion: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )


    tipo_cobertura: Mapped[str | None] = mapped_column(String(20), nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora_utc, nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_ahora_utc,
        onupdate=_ahora_utc,
        nullable=False,
    )

    historia_usuario: Mapped["HistoriaUsuarioORM"] = relationship(
        back_populates="test_cases"
    )
    historial_feedback: Mapped[list["MensajeFeedbackORM"]] = relationship(
        back_populates="test_case",
        cascade="all, delete-orphan",
        order_by="MensajeFeedbackORM.fecha_creacion",
    )


class MensajeFeedbackORM(Base):
    """
    Tabla `mensajes_feedback`.

    Mapea `domain.models.MensajeFeedback`, uno por fila. El orden del chat
    se reconstruye con `ORDER BY fecha_creacion` (ver `order_by` en la
    relación de `TestCaseORM.historial_feedback`) — no se usa un campo de
    "orden" manual separado porque la fecha de creación ya es
    estrictamente creciente y suficiente para este volumen de mensajes por
    test case.
    """

    __tablename__ = "mensajes_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    test_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_cases.id"), nullable=False, index=True
    )


    autor: Mapped[str] = mapped_column(String(20), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora_utc, nullable=False
    )

    test_case: Mapped["TestCaseORM"] = relationship(back_populates="historial_feedback")


class EmbeddingHistoricoORM(Base):
    """
    Tabla `embeddings_historicos`.

    Carga del Excel histórico (Fase 3, ETL — spec sección 7). Separada de
    `test_cases` a propósito (ver decisión en el docstring del módulo):
    este corpus no pasa por el ciclo de vida pendiente/aprobado/rechazado,
    es el material de referencia contra el que se busca similitud antes de
    generar test cases nuevos.

    No hereda ninguna estructura de `domain.models.TestCase` porque no es
    la misma entidad de dominio — es un registro histórico de
    `CasosPrueba` del Excel, con su propio campo `resumen` (no `gherkin`,
    el histórico no necesariamente está en formato Gherkin completo) y
    metadata propia de trazabilidad (`key_test`, `key_te`, `key_tp`).

    Campos de metadata como Módulo/Funcionalidad/Criticidad de Negocio NO
    se modelan aquí: están 100% vacíos en el archivo real (confirmado
    contra el Excel real, spec sección 7) y agregarlos sería ruido sin
    ningún valor — disciplina de alcance ya acordada.
    """

    __tablename__ = "embeddings_historicos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


    key_test: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)


    key_te: Mapped[str | None] = mapped_column(String(50), nullable=True)
    key_tp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hu_key: Mapped[str | None] = mapped_column(String(50), nullable=True)


    resumen: Mapped[str] = mapped_column(Text, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(
        Vector(DIMENSION_EMBEDDING), nullable=False
    )

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora_utc, nullable=False
    )


class MapaSeguimientoHUORM(Base):
    """
    Tabla `mapa_seguimiento_hu`.

    Curación MANUAL de qué HUs se usan para la comparación "antes vs. con
    IA" del Dashboard (Decisión de diseño). No se llena
    sola: el QA agrega acá cualquier HU que quiera trackear para la
    comparación, la haya procesado el agente o no -- por eso es una tabla
    separada de `historias_usuario` (esa se llena sola cuando el agente
    corre; esta es la lista curada de qué SE QUIERE medir, y en qué grupo
    de comparación entra).

    Ver `infrastructure/db/mapa_seguimiento.py` para las funciones que
    escriben y leen esta tabla -- se mantuvo fuera del port `Repository` a
    propósito: es una utilidad de curación para el Dashboard, no una
    operación del flujo central del agente (generar/revisar/subir).
    """

    __tablename__ = "mapa_seguimiento_hu"

    hu_key: Mapped[str] = mapped_column(String(50), primary_key=True)


    grupo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)


    tiempo_proceso_horas: Mapped[float | None] = mapped_column(Float, nullable=True)

    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    fecha_agregado: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora_utc, nullable=False
    )


class SeguimientoHUMetricasORM(Base):
    """
    Tabla `seguimiento_hu_metricas`.

    Snapshots APPEND-ONLY de los índices de `frontend/pages/5_🎯_Seguimiento.py`
    (vía `application/seguimiento/motor.py::ejecutar_seguimiento()`), para
    trackear la evolución CRONOLÓGICA del proceso de certificación -- no
    confundir con la curación manual "antes vs. con IA" de
    `mapa_seguimiento_hu` de arriba, que es otra cosa.

    Decisión de diseño (2026-09-02): "cronológico". Las HU
    se anclan por `fecha_certificacion_terminada` (customfield_10428, "Fin
    En certificación" -- mismo campo que ya usa
    `scripts/obtener_duracion_certificacion_82hu.py` para la duración de la
    certificación, reusado acá para otro fin: ubicar la HU en el tiempo,
    no medir cuánto duró), NO por la fecha de paso a "En Producción" (el
    usuario señaló que la práctica de registro del equipo todavía no es
    100% consistente ahí). Se probó primero con `customfield_10429`
    ("Inicio Certificación Terminada"), pero esa búsqueda libre devolvió
    2000 candidatas -- muy por encima de los corpus ya conocidos del
    proyecto y con una tasa altísima de HU "sin criterios detectables",
    señal de que ese campo no está acotado a HU. Ver el comentario sobre
    `CAMPO_FECHA_CERTIFICACION_TERMINADA` en
    `application/seguimiento/motor.py` para el detalle, incluida la
    advertencia de que el cambio de campo por sí solo no garantiza que el
    alcance quede acotado a HU -- todavía falta confirmar issuetype/
    proyecto con datos reales si el volumen vuelve a dispararse.
    `scripts/procesar_seguimiento_historico.py` recorre las HU con ese
    campo cargado, de más antigua a más nueva, en cohortes configurables
    (default 10), y guarda una fila por HU procesada. La vista de
    "evolución" (todavía no construida) agruparía estas filas en cohortes
    cronológicas y promediaría cada índice por cohorte -- SQL `AVG(...)
    GROUP BY` sobre esta tabla, sin necesidad de columnas de agregado
    separadas.

    Restringida a HU con al menos un criterio de aceptación detectable
    (`num_criterios_identificados > 0`, decisión de diseño): una
    HU sin criterios detectables no aporta nada a la cobertura y ensuciaría
    el promedio -- ni siquiera se guarda una fila para ella (a diferencia
    de "sin Test Plan", que si se guarda, con las columnas de índice en
    None -- ver el script batch).

    APPEND-ONLY a propósito, nunca UPDATE (ver
    `infrastructure/db/seguimiento_metricas.py::guardar_snapshot_hu()`): el
    único de estos índices que legítimamente puede cambiar después de
    medido es el estado de defectos (un defecto se puede corregir semanas
    más tarde) -- si algún día se agrega un refresh de eso, tiene que
    quedar como una fila NUEVA, no pisando el snapshot original, mismo
    criterio de auditoría que el resto del esquema. La cobertura real (IA)
    en particular NUNCA se recalcula sola para no introducir una variación
    de no-determinismo entre dos lecturas de la misma HU (ver
    `HU-394`, ya documentado en `ports/llm_provider.py`).

    Sin ForeignKey a `historias_usuario`: estas HU vienen de una búsqueda
    JQL libre por `customfield_10428`, no necesariamente pasaron por el
    flujo del agente (mismo criterio que `EmbeddingHistoricoORM.hu_key`
    arriba).
    """

    __tablename__ = "seguimiento_hu_metricas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    hu_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)


    fecha_certificacion_terminada: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    num_criterios_identificados: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_tests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indice_cobertura_densidad_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    indice_cobertura_real_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    criterios_no_cubiertos: Mapped[str | None] = mapped_column(Text, nullable=True)

    indice_ejecucion_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    test_pass_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    num_defectos_detectados: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_defectos_resueltos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    defectos_por_severidad: Mapped[str | None] = mapped_column(String(200), nullable=True)

    test_plan_keys: Mapped[str | None] = mapped_column(String(300), nullable=True)
    aviso: Mapped[str | None] = mapped_column(Text, nullable=True)


    fecha_medicion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora_utc, nullable=False
    )
