"""
Caso de uso: subir un test case aprobado a Xray (spec, sección 6, paso 9).

Orquesta dos colaboradores: `JiraCloudAdapter` (para resolver el proyecto
destino a partir del Test Plan) y `TestManagementSystem` (Xray, para crear el
Test). Importante: estos dos NO comparten una interfaz común -- son
colaboradores con responsabilidades distintas, no implementaciones
intercambiables (ver `ports/issue_tracker.py` para el porqué).

"Guardar resultado sin perder el trabajo ya hecho si algo falla" (spec,
sección 6, paso 9): si la subida a Xray falla, el TestCase se queda en estado
APROBADO (no se pierde, no cambia a RECHAZADO ni desaparece) y el error se
informa para que el usuario pueda reintentar.
"""

from __future__ import annotations

from domain.models import EstadoTestCase, TestCase
from infrastructure.config import obtener_logger
from ports.issue_tracker import IssueTracker
from ports.test_management import TestManagementSystem

_log = obtener_logger(__name__)


class SubirTestCaseAXray:
    def __init__(self, issue_tracker: IssueTracker, test_management: TestManagementSystem):
        self._issue_tracker = issue_tracker
        self._test_management = test_management

    def ejecutar(
        self,
        test_case: TestCase,
        key_test_plan: str | None,
        project_key_destino: str | None = None,
    ) -> TestCase:
        """
        Sube un test case aprobado a Xray. Requiere que `test_case.estado`
        sea APROBADO (no sube tests pendientes o rechazados -- eso sería
        saltarse la revisión humana que es el punto central de la Fase 2).

        Args:
            test_case: el test case aprobado.
            key_test_plan: key del Test Plan detectado para la HU (puede ser
                None si no se encontró y el usuario decidió continuar igual).
            project_key_destino: si se indica explícitamente, se usa este
                proyecto en vez del proyecto del Test Plan (opción avanzada,
                spec sección 5). Si es None, se resuelve automáticamente del
                Test Plan.

        Returns:
            El mismo `test_case`, mutado in-place con `xray_test_key` y
            estado `SUBIDO_A_XRAY`.

        Raises:
            ValueError: si el test case no está en estado APROBADO, o si no
                hay forma de determinar el proyecto destino (sin Test Plan y
                sin `project_key_destino` explícito).
            Cualquier excepción que levanten los adapters subyacentes (ej.
            errores de red o de Xray) se propaga sin envolver, para que el
            test case se quede en APROBADO y el usuario pueda reintentar sin
            perder el trabajo de revisión ya hecho.
        """
        if test_case.estado != EstadoTestCase.APROBADO:
            raise ValueError(
                f"Solo se pueden subir a Xray test cases en estado APROBADO "
                f"(estado actual: {test_case.estado.value})."
            )

        if not project_key_destino:
            if not key_test_plan:
                raise ValueError(
                    "No se puede determinar el proyecto destino: no hay Test "
                    "Plan detectado y no se indicó project_key_destino "
                    "explícitamente."
                )
            project_key_destino = self._issue_tracker.project_key_de(key_test_plan)

        _log.info(
            "Subiendo test case %s (%s) a Xray, proyecto %s, test plan %s",
            test_case.id, test_case.titulo, project_key_destino, key_test_plan,
        )

        xray_test_key = self._test_management.crear_test(
            test_case=test_case,
            key_test_plan=key_test_plan,
            project_key_destino=project_key_destino,
        )

        test_case.xray_test_key = xray_test_key
        test_case.estado = EstadoTestCase.SUBIDO_A_XRAY

        _log.info("Test case %s subido a Xray como %s", test_case.id, xray_test_key)
        return test_case
