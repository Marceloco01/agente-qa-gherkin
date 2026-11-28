"""
Port (contrato) para persistencia relacional (HU, test cases, estado, feedback).

Fase 1 y 2: este archivo NO se usaba todavía. No había base de datos: el
resultado de la generación solo se mostraba en Streamlit, y el chat de
feedback vivía en memoria de sesión (`st.session_state`). Se incluyó desde
el principio por consistencia con la estructura de carpetas definitiva
(spec, sección 3.2), pero ningún código de Fase 1/2 lo importaba.

Se implementa en Fase 3, con `SqlAlchemyRepository`
(`adapters/repository/sqlalchemy_repository.py`).

Nota sobre el parámetro `autor` (antes `usuario` en una versión anterior de
este contrato): se renombró para que sea explícito que el valor esperado es
"usuario" o "agente" -- el mismo vocabulario que ya usa
`domain.models.MensajeFeedback.autor` -- y no el nombre real de la persona
que está usando la app. El proyecto sigue siendo de un solo usuario (spec,
sección 1); si en el futuro se necesita trazabilidad por persona física
(útil para Fase 5, Dashboard, si el equipo crece a varios QA), eso requiere
un campo nuevo y separado, no reutilizar este.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import HistoriaUsuario, TestCase


class Repository(ABC):
    @abstractmethod
    def guardar_hu(self, hu: HistoriaUsuario) -> None:
        raise NotImplementedError

    @abstractmethod
    def guardar_test_cases(self, test_cases: list[TestCase]) -> None:
        raise NotImplementedError

    @abstractmethod
    def actualizar_estado(self, test_case_id: str, estado: str, autor: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def guardar_feedback(self, test_case_id: str, autor: str, mensaje: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def actualizar_test_case_completo(self, test_case: TestCase) -> None:
        """..."""
        raise NotImplementedError

    @abstractmethod
    def actualizar_alucinacion(
        self,
        test_case_id: str,
        alucinacion_detectada: bool,
        alucinacion_detalle: str | None,
    ) -> None:
        """
        Sincroniza el resultado de la verificación de alucinación
        (Fase 4) con la base de datos.

        Método separado de actualizar_test_case_completo() por el mismo
        motivo que ese método existe separado de actualizar_estado(): la
        verificación de alucinación cambia 2 campos que no tienen relación
        con gherkin/titulo/estado/version_contenido -- mezclarlos
        sobrecargaría la responsabilidad de un método existente en vez de
        que cada operación de dominio tenga su reflejo explícito en el
        Repository (ver bug real de version_contenido desincronizado,
        spec sección 12.8).
        """
        raise NotImplementedError

    @abstractmethod
    def actualizar_evaluacion_vera(
        self,
        hu_key: str,
        score: int | None,
        aprobada: bool,
        motivo_bloqueo: str | None,
        umbral_aplicado: int | None = None,
    ) -> None:
        """
        Sincroniza el resultado de Vera (application/validar_hu.py) con la
        HU ya persistida. `umbral_aplicado` (v1.0.2) guarda el umbral vigente
        en esa evaluación, para que un cambio del .env quede registrado. Separado de `guardar_hu()` a propósito: `guardar_hu`
        se llama al recibir la HU de Jira, ANTES de que Vera la evalúe, para
        que el indicador del Dashboard cuente también las HUs que Vera
        termina bloqueando (Decisión de diseño: el bloqueo
        "queda en nuestro indicador", no se pierde).
        """
        raise NotImplementedError

    @abstractmethod
    def registrar_generacion(
        self,
        hu_key: str,
        forzada: bool,
        descripcion_usada: str | None,
    ) -> None:
        """
        Deja constancia de CÓMO se generó: si fue forzando el bloqueo de Vera
        y con qué texto.

        Separado de `actualizar_evaluacion_vera()` porque responde otra
        pregunta y en otro momento. Vera puede evaluar una HU cinco veces
        mientras el usuario la edita, y cada evaluación pisa la anterior --
        eso está bien, el veredicto vigente es el último. Pero "se generó
        forzando" y "se generó con este texto" son hechos de la generación,
        ocurren una sola vez y no deben perderse si después alguien reevalúa.

        `descripcion_usada=None` significa que se usó la descripción tal como
        vino de Jira, sin editar.
        """
        raise NotImplementedError

    @abstractmethod
    def actualizar_fecha_fin_proceso(self, hu_key: str) -> None:
        """
        Marca el cierre del proceso para una HU (fecha_fin_proceso = ahora),
        llamado cuando el último test case de esa HU se sube a Xray (ver
        application/subir_a_xray.py). Junto con fecha_inicio_proceso, esto
        es lo que permite calcular cuánto tardó el proceso de punta a punta
        para el Dashboard.
        """
        raise NotImplementedError
