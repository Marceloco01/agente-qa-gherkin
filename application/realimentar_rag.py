"""
Caso de uso: re-alimentar el histórico del RAG cuando un test case llega a
SUBIDO_A_XRAY.

Motivación (ver arquitectura-qa-test-agent.md, sección "Sobre el RAG: no
es un agente"): el histórico de `embeddings_historicos` se cargó una sola
vez desde el Excel (4.147 casos, ETL de Fase 3) y nunca se actualiza con
el uso real del sistema -- un test case nuevo, generado por Gio, revisado
por el QA y subido a Xray, nunca se convertía en un embedding nuevo. Esta
clase cierra ese círculo: es lo que le da "memoria que crece" al RAG.

Deliberadamente NO es un agente (ver gobernanza de agentes en el doc del
proyecto): no hay juicio de LLM propio involucrado -- `generar_embedding()`
ya es una llamada existente y determinista dada la misma entrada, sin vara
de calidad propia que evaluar. Es un paso de código más, aunque use un LLM
por debajo.

Deliberadamente NO conectado todavía a `application/subir_a_xray.py`: el
punto de integración natural es "después de que SubirTestCaseAXray.ejecutar()
devuelva éxito", pero ese wiring vive en el frontend (Streamlit, que
mantiene la sesión y el `test_plan_key` de la HU en memoria) y tocar el
frontend sigue fuera de alcance por ahora (ver "mantener la visual
actual"). Esta clase queda lista y probada de forma aislada para cuando se
habilite ese cambio -- es, literalmente, una llamada de una línea después
de `subir.ejecutar(...)`.
"""

from __future__ import annotations

from domain.models import EstadoTestCase, TestCase
from infrastructure.config import obtener_logger
from ports.llm_provider import LLMProvider
from ports.vector_store import VectorStore

_log = obtener_logger(__name__)


class RealimentarRAG:
    def __init__(self, llm_provider: LLMProvider, vector_store: VectorStore) -> None:
        self._llm_provider = llm_provider
        self._vector_store = vector_store

    def ejecutar(self, test_case: TestCase, test_plan_key: str | None) -> None:
        """
        Genera el embedding del test case ya subido a Xray y lo guarda (o
        actualiza, si ya existía -- `guardar_embedding()` hace upsert por
        `key_test`, ver `adapters/vector_store/postgres_pgvector.py`) en
        `embeddings_historicos`, para que futuras búsquedas de casos
        similares (`application/generar_test_cases.py::_buscar_similares()`)
        puedan encontrarlo como referencia.

        Args:
            test_case: debe estar en estado SUBIDO_A_XRAY y tener
                `xray_test_key` -- se usa como `referencia_id`/`key_test`,
                el mismo identificador natural que ya usa el histórico del
                ETL.
            test_plan_key: key del Test Plan de la HU, si se conoce (mapea
                a `key_tp`). None si la HU se procesó sin Test Plan
                detectado -- la columna es nullable exactamente por este
                caso.

        No propaga excepciones: si algo falla acá (LLM caído, red, lo que
        sea), se loguea como warning y se sigue. Cuando esto se conecte al
        flujo real después de `SubirTestCaseAXray`, una falla acá NUNCA
        debe poner en duda que el test SÍ se subió correctamente a Xray
        (eso ya es un hecho consumado en ese punto) -- misma filosofía de
        "degradación elegante" que ya usa `verificar_alucinacion()` ante
        una respuesta no parseable del LLM.

        `key_te` (Test Execution) queda siempre en `None`: a diferencia del
        histórico del Excel (que ya trae ejecuciones corridas), un test
        recién subido a Xray todavía no tiene ninguna ejecución propia --
        inventar un valor acá sería peor que dejarlo vacío (la columna es
        nullable justamente por esto).
        """
        if test_case.estado != EstadoTestCase.SUBIDO_A_XRAY:
            raise ValueError(
                f"Solo se re-alimentan test cases en estado SUBIDO_A_XRAY "
                f"(estado actual: {test_case.estado.value})."
            )
        if not test_case.xray_test_key:
            raise ValueError(
                "El test case no tiene xray_test_key -- no se puede usar "
                "como referencia_id del embedding."
            )

        texto = f"{test_case.titulo}\n{test_case.gherkin}"

        try:
            vector = self._llm_provider.generar_embedding(texto)
            self._vector_store.guardar_embedding(
                referencia_id=test_case.xray_test_key,
                vector=vector,
                metadata={
                    "key_te": None,
                    "key_tp": test_plan_key,
                    "hu_key": test_case.hu_key,
                    "resumen": texto,
                },
            )
        except Exception:
            _log.warning(
                "No se pudo re-alimentar el RAG con el test case %s (%s) -- "
                "el test SÍ quedó subido a Xray, esto solo afecta al "
                "histórico de referencia para futuras generaciones.",
                test_case.id, test_case.xray_test_key, exc_info=True,
            )
            return

        _log.info(
            "Test case %s (%s) re-alimentado al histórico del RAG",
            test_case.id, test_case.xray_test_key,
        )
