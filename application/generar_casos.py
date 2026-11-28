"""
Caso de uso: RAG + Gio, sobre una HU que ya pasó (o que se decidió saltear)
el Quality Gate.

Fase 2 §2.2: es la segunda mitad de lo que antes era
`GenerarTestCases.ejecutar()`. La primera mitad --Jira + Vera-- vive ahora en
`application/evaluar_hu.py`; acá empieza recién cuando alguien decidió
generar.

`forzada=True` es el caso en que Vera bloqueó y el usuario generó igual. NO
cambia nada del comportamiento de la generación: cambia lo que queda
registrado. Sin esa marca, después no hay forma de separar "casos de HU
aprobadas" de "casos de HU forzadas" en ningún indicador -- que es
exactamente lo que pasó con el lote de septiembre, donde el forzado se hizo
bajando el umbral en el .env y no dejó rastro en la base.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.models import (
    EvaluacionHU,
    HistoriaUsuario,
    TestCase,
    marcar_verificacion_no_disponible,
)
from infrastructure.config import obtener_logger
from ports.llm_provider import LLMProvider
from ports.repository import Repository
from ports.vector_store import VectorStore

_log = obtener_logger(__name__)


@dataclass
class ResultadoGeneracion:
    """
    Resultado del caso de uso, con la información que el frontend necesita
    para decidir qué advertencias mostrar (descripción pobre, etc.) sin tener
    que recalcular nada por su cuenta.

    `evaluacion_hu`: resultado de Vera. Si `evaluacion_hu.aprobada` es False
    y `test_cases` viene vacío, Gio nunca llegó a correr. Si es False y hay
    test cases, la generación se forzó -- y `forzada` lo dice explícitamente
    en vez de dejarlo a deducción.

    Vive en este módulo y no en `generar_test_cases.py` para evitar un import
    circular: aquel importa a este, no al revés. Se sigue re-exportando desde
    allá para no romper a quien ya lo importaba.
    """

    hu: HistoriaUsuario
    test_cases: list[TestCase]
    descripcion_es_pobre: bool
    casos_similares_usados: int
    evaluacion_hu: EvaluacionHU | None = None
    forzada: bool = False


class GenerarCasos:
    """RAG -> Gio -> verificación de alucinación -> persistir."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        repository: Repository,
        vector_store: VectorStore,
        top_k: int = 3,
    ):
        self._llm_provider = llm_provider
        self._repository = repository
        self._vector_store = vector_store
        self._top_k = top_k
        self.verificaciones_no_disponibles = 0

    def ejecutar(
        self,
        hu: HistoriaUsuario,
        evaluacion: EvaluacionHU | None = None,
        forzada: bool = False,
        descripcion_usada: str | None = None,
        descripcion_original: str | None = None,
    ) -> ResultadoGeneracion:
        casos_similares = self._buscar_similares(hu)


        test_cases = self._llm_provider.generar_test_cases(
            hu, casos_similares=casos_similares if casos_similares else None
        )


        self._verificar_alucinacion(hu, test_cases, casos_similares)


        hu.generacion_forzada = forzada
        if descripcion_usada is not None:
            hu.descripcion_usada = descripcion_usada


            if descripcion_original is not None:
                hu.descripcion = descripcion_original
        self._persistir(hu, test_cases)
        self._repository.registrar_generacion(hu.key, forzada, descripcion_usada)
        if forzada:
            _log.warning(
                "Generación FORZADA para %s: Vera la había bloqueado (score %s)",
                hu.key, evaluacion.score if evaluacion else "s/d",
            )

        return ResultadoGeneracion(
            hu=hu,
            test_cases=test_cases,
            descripcion_es_pobre=hu.descripcion_es_pobre,
            casos_similares_usados=len(casos_similares) if casos_similares else 0,
            evaluacion_hu=evaluacion,
            forzada=forzada,
        )

    def _buscar_similares(self, hu: HistoriaUsuario) -> list[dict] | None:
        """
        Genera un embedding del texto de la HU y busca los casos históricos
        más similares. Si falla (VectorStore no disponible, Ollama caído,
        etc.), loggea el error y devuelve None para que la generación
        continúe sin contexto RAG -- degradación elegante, no fallo total.
        """
        try:
            texto_consulta = f"HU: {hu.key} | {hu.descripcion}"
            vector = self._llm_provider.generar_embedding(texto_consulta)
            similares = self._vector_store.buscar_similares(vector, top_k=self._top_k)
            _log.info(
                "RAG: %d casos similares encontrados para %s", len(similares), hu.key
            )
            return similares
        except Exception as exc:
            _log.warning(
                "RAG no disponible para %s, se genera sin contexto histórico: %s",
                hu.key, exc,
            )
            return None

    def _verificar_alucinacion(
        self, hu: HistoriaUsuario, test_cases: list[TestCase], casos_similares: list[dict] | None
    ) -> None:
        """
        Llama a LLMProvider.verificar_alucinacion() en batch (una sola llamada
        para todos los test_cases generados de esta HU) y aplica el resultado
        a cada objeto TestCase en memoria, mutándolos in-place.

        Falla segura (v1.0.2): si la verificación falla por completo, o si
        el modelo no devuelve resultado para algún test case (por ejemplo,
        JSON no parseable), ese test case queda MARCADO con
        `DETALLE_VERIFICACION_NO_DISPONIBLE`. Así no puede aprobarse sin que
        el analista lo edite o lo regenere, igual que un caso con alucinación
        detectada. Hasta la v1.0.1 la falla era abierta: el caso pasaba sin
        marca. `verificaciones_no_disponibles` cuenta cuántos casos quedaron
        en esa situación en la última ejecución.
        """
        contexto_completo = [
            {"resumen": f"Historia de Usuario {hu.key} - {hu.titulo}: {hu.descripcion}"}
        ] + (casos_similares or [])
        try:
            resultados = self._llm_provider.verificar_alucinacion(
                test_cases, contexto=contexto_completo
            )
        except Exception as exc:
            _log.warning(
                "Verificación de alucinación no disponible; se marcan los %d "
                "test case(s) para revisión obligatoria: %s", len(test_cases), exc,
            )
            for tc in test_cases:
                marcar_verificacion_no_disponible(tc)
            self.verificaciones_no_disponibles = len(test_cases)
            return

        resultados_por_id = {r.get("test_case_id"): r for r in (resultados or [])}
        self.verificaciones_no_disponibles = 0
        for tc in test_cases:
            resultado = resultados_por_id.get(tc.id)
            if resultado is None:
                _log.warning(
                    "Sin resultado de verificación para %s (%s); queda marcado "
                    "para revisión obligatoria.", tc.id, tc.titulo,
                )
                marcar_verificacion_no_disponible(tc)
                self.verificaciones_no_disponibles += 1
                continue
            tc.alucinacion_detectada = bool(resultado.get("alucinado", False))
            tc.alucinacion_detalle = (
                resultado.get("razon") or None if tc.alucinacion_detectada else None
            )
            if tc.alucinacion_detectada:
                _log.warning(
                    "Posible alucinación detectada en test case %s (%s): %s",
                    tc.id, tc.titulo, tc.alucinacion_detalle,
                )

    def _persistir(self, hu: HistoriaUsuario, test_cases: list[TestCase]) -> None:
        self._repository.guardar_hu(hu)
        self._repository.guardar_test_cases(test_cases)
        _log.info("Persistidos: HU %s + %d test cases", hu.key, len(test_cases))
