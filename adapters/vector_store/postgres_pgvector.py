"""
Adapter concreto del port `VectorStore`, usando PostgreSQL + pgvector.

Fase 3. Implementa `guardar_embedding()` y `buscar_similares()` contra la
tabla `embeddings_historicos` (ver `infrastructure/db/models_orm.py`).

Decisión de diseño:

- Métrica de similitud: distancia coseno (`cosine_distance` de
  pgvector-python), no euclidiana ni producto interno. Es la métrica
  estándar para embeddings de texto y la que mejor se alinea con cómo
  `nomic-embed-text` fue evaluado. La distancia coseno va de 0 (idénticos)
  a 2 (opuestos); se expone como `similitud = 1 - distancia` en
  `buscar_similares()` para que un score más alto signifique "más
  similar" (más intuitivo para quien consuma el resultado).

- Validación explícita de `metadata` en `guardar_embedding()` (opción B,
  adoptada para este diseño): el dict debe traer exactamente las claves
  `key_te`, `key_tp`, `hu_key`, `resumen` -- si falta alguna, se lanza un
  `ValueError` con el nombre de la clave faltante y el `referencia_id`
  afectado, ANTES de tocar la base de datos. Esto importa especialmente
  para el ETL del Excel histórico (Fase 3, sección 7 de la spec): con
  4147 filas a cargar de una fuente real que ya se sabe tiene encoding
  roto y columnas vacías, un error específico por fila ahorra tener que
  adivinar cuál de las miles de filas rompió la carga.

Misma decisión de sesión que `SqlAlchemyRepository`: sesión inyectada en
el constructor, no administrada por este adapter (ver
`infrastructure/db/conexion.py` para el patrón de "sesión por bloque").
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db.models_orm import EmbeddingHistoricoORM
from ports.vector_store import VectorStore


_CLAVES_METADATA_REQUERIDAS = ("key_te", "key_tp", "hu_key", "resumen")


class PostgresPgvectorAdapter(VectorStore):
    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    @staticmethod
    def _validar_metadata(referencia_id: str, metadata: dict) -> None:
        """
        Confirma que `metadata` trae todas las claves requeridas antes de
        construir el objeto ORM. Lanza `ValueError` con el nombre exacto
        de la clave faltante y el `referencia_id` afectado -- decisión
        adoptada para este diseño (opción B), pensada para el volumen real
        del ETL (miles de filas del Excel histórico).
        """
        faltantes = [
            clave for clave in _CLAVES_METADATA_REQUERIDAS if clave not in metadata
        ]
        if faltantes:
            raise ValueError(
                f"metadata incompleta para referencia_id={referencia_id!r}: "
                f"faltan las claves {faltantes}. Se requieren todas estas: "
                f"{list(_CLAVES_METADATA_REQUERIDAS)}."
            )

    def guardar_embedding(
        self,
        referencia_id: str,
        vector: list[float],
        metadata: dict,
    ) -> None:
        """
        Guarda o actualiza el embedding de un caso histórico (upsert).

        `referencia_id` mapea a la columna `key_test` (unique). Se hace un
        upsert explícito (buscar primero, actualizar si existe, insertar si
        no) en vez de `merge()`: SQLAlchemy's `merge()` no detecta
        correctamente la fila existente cuando la PK lógica es una columna
        `unique` pero no la PK real de la tabla (que en este caso es `id`,
        autoincrement), y cae en INSERT causando un `UniqueViolation` que
        invalida toda la sesión y afecta en cascada a todos los inserts
        siguientes del mismo lote -- bug real detectado durante el ETL.

        El upsert explícito es determinista: siempre hay exactamente una
        operación (UPDATE o INSERT), sin ambigüedad sobre qué columna usa
        SQLAlchemy como clave de identidad.
        """
        self._validar_metadata(referencia_id, metadata)


        existente = self._sesion.execute(
            select(EmbeddingHistoricoORM).where(
                EmbeddingHistoricoORM.key_test == referencia_id
            )
        ).scalar_one_or_none()

        if existente is not None:

            existente.key_te = metadata["key_te"]
            existente.key_tp = metadata["key_tp"]
            existente.hu_key = metadata["hu_key"]
            existente.resumen = metadata["resumen"]
            existente.embedding = vector
        else:

            nuevo = EmbeddingHistoricoORM(
                key_test=referencia_id,
                key_te=metadata["key_te"],
                key_tp=metadata["key_tp"],
                hu_key=metadata["hu_key"],
                resumen=metadata["resumen"],
                embedding=vector,
            )
            self._sesion.add(nuevo)

    def buscar_similares(self, vector: list[float], top_k: int) -> list[dict]:
        """
        Busca los `top_k` casos históricos más similares a `vector`,
        usando distancia coseno (Decisión de diseño).

        Cada dict devuelto trae las mismas claves que `guardar_embedding()`
        espera en `metadata`, más `referencia_id` y `similitud` -- así el
        caller (en Fase 3+, `application/generar_test_cases.py`) puede
        usar el resultado directo como contexto del prompt sin tener que
        traducir nombres de campos.

        `similitud` se expone como `1 - distancia_coseno` (rango
        aproximado 0 a 1 para vectores típicos de texto, donde más alto =
        más similar) en vez de la distancia cruda, porque es más intuitivo
        para cualquier código o persona que consuma este resultado sin
        tener que recordar que en la distancia "menor es mejor".
        """
        distancia = EmbeddingHistoricoORM.embedding.cosine_distance(vector)

        resultados = self._sesion.execute(
            select(EmbeddingHistoricoORM, distancia.label("distancia"))
            .order_by(distancia)
            .limit(top_k)
        ).all()

        return [
            {
                "referencia_id": fila.EmbeddingHistoricoORM.key_test,
                "key_te": fila.EmbeddingHistoricoORM.key_te,
                "key_tp": fila.EmbeddingHistoricoORM.key_tp,
                "hu_key": fila.EmbeddingHistoricoORM.hu_key,
                "resumen": fila.EmbeddingHistoricoORM.resumen,
                "similitud": 1 - fila.distancia,
            }
            for fila in resultados
        ]
