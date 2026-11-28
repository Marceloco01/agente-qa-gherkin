"""
Caso de uso legado: HU desde Jira -> Vera -> (RAG) -> Gio -> persistir, todo
en una sola llamada.

**Fase 2 §2.2: este módulo dejó de tener lógica propia.** La tenía, y era el
problema: el Quality Gate quedaba encerrado adentro de `ejecutar()`, así que
ninguna pantalla podía frenar en él --para cuando el usuario veía el score de
Vera, Gio ya había corrido--. Se partió en dos casos de uso con una
responsabilidad cada uno:

  - `application/evaluar_hu.EvaluarHU`   -> Jira + persistir + Vera
  - `application/generar_casos.GenerarCasos` -> RAG + Gio + persistir

Esta clase queda como envoltura de las dos, con la MISMA firma y el MISMO
comportamiento de antes, porque `scripts/correr_agente_*.py` y las corridas
batch la usan tal cual y no tienen por qué enterarse del cambio. Para la
pantalla nueva no se usa: ahí se llaman los dos casos de uso por separado,
que es justamente el punto.

`ResultadoGeneracion` se re-exporta desde acá por la misma razón: vive en
`generar_casos.py` (si viviera acá habría import circular), pero quien ya lo
importaba de este módulo lo sigue encontrando.
"""

from __future__ import annotations

from application.evaluar_hu import EvaluarHU
from application.generar_casos import GenerarCasos, ResultadoGeneracion
from infrastructure.config import obtener_logger
from ports.issue_tracker import IssueTracker
from ports.llm_provider import LLMProvider
from ports.repository import Repository
from ports.vector_store import VectorStore

__all__ = ["GenerarTestCases", "ResultadoGeneracion"]

_log = obtener_logger(__name__)


class GenerarTestCases:
    """
    Caso de uso: HU desde Jira -> Vera valida -> (RAG) casos similares -> LLM
    genera Gherkin -> persistir en Repository.

    Los parámetros `repository` y `vector_store` son obligatorios -- si
    Postgres está caído, se lanza excepción inmediatamente en lugar de
    silenciar el fallo (Decisión de diseño).
    """

    def __init__(
        self,
        issue_tracker: IssueTracker,
        llm_provider: LLMProvider,
        repository: Repository,
        vector_store: VectorStore,
        top_k: int = 3,
    ):
        self._evaluar = EvaluarHU(
            llm_provider=llm_provider,
            repository=repository,
            issue_tracker=issue_tracker,
        )
        self._generar = GenerarCasos(
            llm_provider=llm_provider,
            repository=repository,
            vector_store=vector_store,
            top_k=top_k,
        )

    def ejecutar(self, key_hu: str) -> ResultadoGeneracion:
        evaluado = self._evaluar.ejecutar(key_hu)

        if not evaluado.evaluacion.aprobada:


            _log.warning(
                "Vera bloqueó %s, no se genera nada con Gio: %s",
                evaluado.hu.key, evaluado.evaluacion.detalle,
            )
            return ResultadoGeneracion(
                hu=evaluado.hu,
                test_cases=[],
                descripcion_es_pobre=evaluado.descripcion_es_pobre,
                casos_similares_usados=0,
                evaluacion_hu=evaluado.evaluacion,
                forzada=False,
            )

        return self._generar.ejecutar(evaluado.hu, evaluacion=evaluado.evaluacion)
