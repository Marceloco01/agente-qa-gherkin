"""
Caso de uso: revisión 1×1 de un test case (spec, sección 6, paso 8).

Fase 3: se agrega persistencia de estado y feedback en el Repository.
El historial de feedback ya no vive solo en memoria de sesión -- ahora
se persiste en la BD en tiempo real, mensaje a mensaje.

Esta capa NO sabe nada de Streamlit ni de cómo se conecta a la BD --
solo recibe el Repository ya construido desde el punto de entrada.
"""

from __future__ import annotations

from domain.exceptions import AprobacionBloqueadaError
from domain.models import (
    EstadoTestCase,
    MensajeFeedback,
    TestCase,
    marcar_verificacion_no_disponible,
)
from infrastructure.config import obtener_logger
from ports.llm_provider import LLMProvider
from ports.repository import Repository

_log = obtener_logger(__name__)


class RevisarTestCase:
    """
    Cambios de estado simples: aprobar, editar+aprobar, rechazar, descartar.

    Fase 3: recibe `repository` para persistir cada cambio de estado.
    """

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def aprobar(self, test_case: TestCase) -> None:
        """
        v1.0.2: el bloqueo por alucinación (o por verificación no disponible)
        se aplica también aquí y no solo en la interfaz. Un caso marcado solo
        puede salir de ese estado editándolo (`editar_y_aprobar`) o
        regenerándolo (`RegenerarTestCase`).
        """
        if test_case.alucinacion_detectada:
            raise AprobacionBloqueadaError(
                f"El test case {test_case.id} tiene una posible alucinación o no "
                "pudo verificarse; edítalo o regenéralo antes de aprobar."
            )
        test_case.estado = EstadoTestCase.APROBADO
        self._repository.actualizar_estado(
            test_case.id, EstadoTestCase.APROBADO.value, "usuario"
        )
        _log.info("Test case %s (%s) aprobado", test_case.id, test_case.titulo)

    def editar_y_aprobar(
        self, test_case: TestCase, nuevo_gherkin: str, nuevo_titulo: str | None = None
    ) -> None:
        """
        Permite corregir el Gherkin (o el título) antes de aprobar, sin pasar
        por una nueva generación del LLM -- es una edición manual directa.

        Fix (2026-09-02): antes solo se llamaba a actualizar_estado(), que
        únicamente persiste la columna `estado` -- el Gherkin editado a mano
        quedaba mutado en el objeto de dominio en memoria pero NUNCA se
        escribía en la base de datos (bug real encontrado al diseñar la
        métrica de alucinaciones del análisis retrospectivo de NEXUS, que necesita poder
        confiar en que el Gherkin persistido es el que el QA realmente
        aprobó). Ahora se usa actualizar_test_case_completo(), que sincroniza
        gherkin/titulo/estado/version_contenido en un solo update -- mismo
        método que ya usa RegenerarTestCase. `version_contenido` también se
        incrementa acá (antes solo se incrementaba al regenerar vía chat),
        para que sea una señal confiable y uniforme de "este test case
        cambió de contenido", sin importar por qué camino de la UI pasó.
        """
        test_case.gherkin = nuevo_gherkin.strip()
        if nuevo_titulo is not None:
            test_case.titulo = nuevo_titulo.strip()
        test_case.estado = EstadoTestCase.APROBADO
        test_case.version_contenido += 1
        self._repository.actualizar_test_case_completo(test_case)
        _log.info(
            "Test case %s (%s) editado y aprobado", test_case.id, test_case.titulo
        )

    def rechazar(self, test_case: TestCase, motivo: str | None = None) -> None:
        test_case.estado = EstadoTestCase.RECHAZADO
        self._repository.actualizar_estado(
            test_case.id, EstadoTestCase.RECHAZADO.value, "usuario"
        )
        if motivo:
            test_case.historial_feedback.append(
                MensajeFeedback(autor="usuario", texto=motivo)
            )
            self._repository.guardar_feedback(test_case.id, "usuario", motivo)
        _log.info("Test case %s (%s) rechazado", test_case.id, test_case.titulo)

    def descartar(self, test_case: TestCase, motivo: str) -> None:
        """
        Registra el descarte definitivo de un test case. No muta el estado
        del test case ni lo quita de ninguna lista -- eso es responsabilidad
        del frontend. Solo persiste el motivo en el log para trazabilidad.
        """
        if not motivo.strip():
            raise ValueError("El motivo de descarte no puede estar vacío.")

        _log.info(
            "Test case %s (%s) descartado. Motivo: %s",
            test_case.id, test_case.titulo, motivo.strip(),
        )


class RegenerarTestCase:
    """
    Toma el feedback del chat libre QA↔Agente y le pide al LLM una nueva
    versión del test case, manteniendo el historial completo como contexto.

    Fase 3: persiste cada mensaje (usuario + agente) en el Repository.
    """

    def __init__(self, llm_provider: LLMProvider, repository: Repository) -> None:
        self._llm_provider = llm_provider
        self._repository = repository

    def regenerar(self, test_case: TestCase, mensaje_usuario: str, descripcion_hu: str = "") -> TestCase:
        """
        Agrega el mensaje del usuario al historial, pide al LLM una nueva
        versión del Gherkin, persiste ambos mensajes, y vuelve el test case
        a estado PENDIENTE para revisión.

        Fase 4: si el test case tiene alucinacion_detectada=True, el
        comentario es obligatorio -- no tiene sentido permitir "regenerar
        en blanco" un test case marcado como sospechoso. Tras regenerar, se
        vuelve a verificar SOLO este test case; si el LLM ya no encuentra
        nada raro, el flag se limpia y el QA puede aprobar; si lo sigue
        encontrando, el flag se mantiene y el ciclo continúa.

        Returns:
            El mismo objeto `test_case`, mutado in-place.
        """
        if test_case.alucinacion_detectada and not mensaje_usuario.strip():
            raise ValueError(
                "Este test case fue marcado con una posible alucinación "
                f"({test_case.alucinacion_detalle}). Es obligatorio indicar "
                "qué corregir antes de poder regenerarlo."
            )


        test_case.historial_feedback.append(
            MensajeFeedback(autor="usuario", texto=mensaje_usuario)
        )
        self._repository.guardar_feedback(test_case.id, "usuario", mensaje_usuario)

        _log.info(
            "Regenerando test case %s a partir de feedback del usuario", test_case.id
        )
        nuevo_gherkin, nuevo_titulo = self._llm_provider.regenerar_test_case(
            gherkin_actual=test_case.gherkin,
            titulo_actual=test_case.titulo,
            historial_feedback=test_case.historial_feedback,
        )

        gherkin_anterior = test_case.gherkin

        test_case.gherkin = nuevo_gherkin
        test_case.titulo = nuevo_titulo
        test_case.estado = EstadoTestCase.PENDIENTE
        test_case.version_contenido += 1


        mensaje_agente = (
            f"He regenerado el test case.\n\n"
            f"**Antes:**\n```gherkin\n{gherkin_anterior}\n```\n\n"
            f"**Después:**\n```gherkin\n{nuevo_gherkin}\n```"
        )
        test_case.historial_feedback.append(
            MensajeFeedback(autor="agente", texto=mensaje_agente)
        )
        self._repository.guardar_feedback(test_case.id, "agente", mensaje_agente)
        self._repository.actualizar_test_case_completo(test_case)


        self._reverificar_alucinacion(test_case, descripcion_hu)

        return test_case

    def _reverificar_alucinacion(self, test_case: TestCase, descripcion_hu: str = "") -> None:
        """
        Vuelve a correr verificar_alucinacion() sobre un único test case ya
        regenerado, y persiste el resultado con actualizar_alucinacion().

        Degradación elegante: si la verificación falla, se loggea y NO se
        toca el flag -- se prefiere dejar el flag tal como estaba antes que
        asumir silenciosamente que ya está todo bien.
        """
        contexto = [{"resumen": f"Historia de Usuario: {descripcion_hu}"}] if descripcion_hu else []
        try:
            resultados = self._llm_provider.verificar_alucinacion(
                [test_case], contexto=contexto
            )
        except Exception as exc:


            _log.warning(
                "No se pudo re-verificar alucinación de %s tras regenerar; "
                "queda marcado para revisión obligatoria: %s", test_case.id, exc,
            )
            resultados = None


        resultado = resultados[0] if resultados else None
        if resultado is None:
            marcar_verificacion_no_disponible(test_case)
            self._repository.actualizar_alucinacion(
                test_case.id, True, test_case.alucinacion_detalle
            )
            return

        test_case.alucinacion_detectada = bool(resultado.get("alucinado", False))
        test_case.alucinacion_detalle = (
            resultado.get("razon") or None if test_case.alucinacion_detectada else None
        )

        self._repository.actualizar_alucinacion(
            test_case.id, test_case.alucinacion_detectada, test_case.alucinacion_detalle
        )

        if test_case.alucinacion_detectada:
            _log.warning(
                "Test case %s sigue marcado con posible alucinación tras "
                "regenerar: %s", test_case.id, test_case.alucinacion_detalle,
            )
        else:
            _log.info(
                "Test case %s ya no presenta alucinación tras regenerar", test_case.id
            )
