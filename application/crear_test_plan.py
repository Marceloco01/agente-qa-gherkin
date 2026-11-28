"""
Caso de uso: crear un Test Plan nuevo y vincularlo a la HU, cuando
`detectar_test_plan()` no encontró ninguno existente (spec, sección 6, paso 4).

Orquesta dos colaboradores: `TestManagementSystem` (Xray, crea el Test Plan)
y `IssueTracker` (Jira, vincula el Test Plan nuevo a la HU vía "Será atendido
por") -- el mismo patrón de `subir_a_xray.py`.
"""

from __future__ import annotations

from infrastructure.config import obtener_logger
from ports.issue_tracker import IssueTracker
from ports.test_management import TestManagementSystem

_log = obtener_logger(__name__)


class CrearTestPlanParaHU:
    def __init__(self, issue_tracker: IssueTracker, test_management: TestManagementSystem):
        self._issue_tracker = issue_tracker
        self._test_management = test_management

    def ejecutar(self, key_hu: str, summary: str, project_key: str) -> str:
        """
        Crea un Test Plan nuevo con el summary indicado, en el proyecto
        dado, y lo vincula a la HU con "Será atendido por".

        Args:
            key_hu: key de la HU a la que se va a vincular el Test Plan nuevo.
            summary: título completo del Test Plan (ya armado por quien
                llama -- ej. "Test Plan - <título de la HU>", o cualquier
                otro título que el usuario haya elegido editar).
            project_key: proyecto Jira donde crear el Test Plan.

        Returns:
            La key del Test Plan creado (ej. "PROJ-50").

        Si la vinculación falla después de crear el Test Plan, el Test Plan
        ya existe en Jira (no se pierde) pero queda sin vincular -- el error
        se propaga para que el usuario sepa que debe vincularlo manualmente
        o reintentar.
        """
        _log.info("Creando Test Plan nuevo para %s: '%s'", key_hu, summary)
        key_test_plan = self._test_management.crear_test_plan(summary=summary, project_key=project_key)

        _log.info("Vinculando Test Plan %s a HU %s", key_test_plan, key_hu)
        try:
            self._issue_tracker.vincular_test_plan_a_hu(key_hu=key_hu, key_test_plan=key_test_plan)
        except Exception as exc:
            _log.error(
                "El Test Plan %s se creó correctamente pero falló la "
                "vinculación a %s: %s. El Test Plan queda sin vincular -- "
                "vincularlo manualmente en Jira o reintentar sin crear uno "
                "nuevo.",
                key_test_plan, key_hu, exc,
            )
            raise ValueError(
                f"El Test Plan {key_test_plan} se creó correctamente, pero no "
                f"se pudo vincular a la HU: {exc}. Puedes vincularlo "
                f"manualmente en Jira (no es necesario crear otro)."
            ) from exc

        return key_test_plan
