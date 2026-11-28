"""
Port (contrato) para el issue tracker de Historias de Usuario (Jira).

Fase 1: solo se implementa `obtener_hu()`.
Fase 2: se implementa `detectar_test_plan()`.

Decisión de Fase 2: `crear_test()` SALIÓ de este port. Vivía aquí en Fase 1
como contrato "completo" preventivo, pero al llegar a Fase 2 quedó claro que
crear un Test es responsabilidad de Xray, no de Jira, y usa una autenticación
completamente distinta (ver `adapters/issue_tracker/xray_cloud_adapter.py`).
Forzar que `JiraCloudAdapter` implementara un método que en realidad no le
compete violaría el Principio de Sustitución de Liskov. Ese método ahora vive
en el port `ports/test_management.py` (`TestManagementSystem`), implementado
por `XrayCloudAdapter`.

Decisión de Fase 2 (confirmado por el usuario): un Test NO se vincula
directamente a la HU. Solo se vincula al Test Plan (vía la mutación
`addTestsToTestPlan` de Xray). La trazabilidad Test→HU queda indirecta, a
través del Test Plan, que sí está vinculado a la HU vía "Será atendido por".

Si no se encuentra ningún Test Plan, el usuario puede pedir crear uno nuevo
-- en ese caso, sí hace falta vincular ESE Test Plan nuevo a la HU (ver
`vincular_test_plan_a_hu()` más abajo), para que la próxima vez la detección
ya lo encuentre solo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.models import HistoriaUsuario, InfoTestPlan


class IssueTracker(ABC):
    @abstractmethod
    def obtener_hu(self, key: str) -> HistoriaUsuario:
        """
        Trae una Historia de Usuario desde Jira a partir de su key (ej. "PROJ-123").

        Debe devolver título y descripción ya como texto plano: la extracción
        del formato ADF (Atlassian Document Format) de la descripción de Jira
        es responsabilidad del adapter, no de quien llama a este método.

        Raises:
            Lo que el adapter concreto considere apropiado si la HU no existe
            o no es accesible (ej. HTTPError, ValueError). Fase 1 no define
            todavía una excepción de dominio específica para esto.
        """
        raise NotImplementedError

    @abstractmethod
    def detectar_test_plan(self, key_hu: str) -> list[InfoTestPlan]:
        """
        Busca TODOS los Test Plans vinculados a la HU vía el issue link
        "Será atendido por", filtrando explícitamente por issuetype = "Test
        Plan" (ese link puede traer vinculados otros tipos de issue además
        de un Test Plan).

        Decisión confirmada por el usuario: si hay más de un Test Plan
        vinculado, no se elige uno automáticamente (sería arriesgado --
        podría subirse el Test al Test Plan incorrecto sin que el usuario
        se entere). Se devuelven todos los encontrados para que el usuario
        elija cuál usar.

        Devuelve título y estado además de la key (no solo `str`) porque
        cuando hay más de uno, la key sola no alcanza para distinguirlos a
        simple vista en la UI.

        Returns:
            Lista de InfoTestPlan. Lista vacía si no se encontró ninguno.
            Puede tener más de un elemento.
        """
        raise NotImplementedError

    @abstractmethod
    def vincular_test_plan_a_hu(self, key_hu: str, key_test_plan: str) -> None:
        """
        Crea el issue link "Será atendido por" entre una HU y un Test Plan.
        Se usa cuando se crea un Test Plan nuevo porque la detección
        automática no encontró ninguno existente.
        """
        raise NotImplementedError

    @abstractmethod
    def project_key_de(self, key_issue: str) -> str:
        """
        Devuelve la key del proyecto Jira al que pertenece un issue (ej. dado
        "PROJ-45" devuelve "PROJ"). Se usa para crear el Test en el mismo
        proyecto donde vive el Test Plan, comportamiento por defecto pedido
        en la spec (sección 5).
        """
        raise NotImplementedError

    @abstractmethod
    def obtener_fecha_entrada_qa(self, key_hu: str) -> datetime | None:
        """
        Busca en el changelog de la HU el timestamp de la primera transición
        de estado hacia alguno de los estados configurados como "entrada a
        QA" (ver infrastructure.config.cargar_configuracion_tiempo_proceso).

        Necesario para el Dashboard (fórmulas de tiempo de proceso, spec del
        libro [29]): el punto de partida es "cuándo entró la HU a QA", tomado
        directamente del historial real de Jira en vez de pedirle al usuario
        que lo cargue a mano.

        Returns:
            El timestamp (con timezone) de esa transición, o None si la HU
            nunca pasó por ninguno de los estados configurados -- puede
            significar que todavía no llegó a QA, o que pertenece a un
            workflow con un nombre de estado que todavía no está en la
            configuración (ver ESTADOS_ENTRADA_QA en .env).
        """
        raise NotImplementedError
