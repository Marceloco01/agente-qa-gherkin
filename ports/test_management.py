"""
Port (contrato) para el sistema de gestión de Tests (Xray).

Se separó de `IssueTracker` en Fase 2 porque crear un Test es responsabilidad
de Xray, no de Jira, y usa una autenticación completamente distinta (Client
ID + Client Secret vs. email + API token). Ver `ports/issue_tracker.py` para
la explicación completa de por qué no conviene forzar un solo contrato con
ambas responsabilidades (viola el Principio de Sustitución de Liskov).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import TestCase


class TestManagementSystem(ABC):
    @abstractmethod
    def crear_test(
        self,
        test_case: TestCase,
        key_test_plan: str | None,
        project_key_destino: str | None = None,
    ) -> str:
        """
        Crea un Test (tipo Cucumber/Gherkin) a partir de un TestCase aprobado,
        y lo vincula al Test Plan indicado (si hay uno).

        Args:
            test_case: el caso de prueba aprobado, con su Gherkin completo.
            key_test_plan: key del Test Plan al que vincular el Test recién
                creado (ej. "PROJ-45"). Si es None, el Test se crea sin
                vincular a ningún Test Plan (caso: no se encontró Test Plan
                vía "Será atendido por" y el usuario decidió continuar igual,
                ver spec sección 6 paso 4).
            project_key_destino: proyecto Jira donde crear el Test. Si es
                None (default), se usa el mismo proyecto donde vive el Test
                Plan (comportamiento por defecto, spec sección 5). Pasar un
                valor explícito es la opción avanzada, pensada para quedar
                oculta/colapsada en la UI por defecto.

        Returns:
            La key del Test creado en Jira (ej. "PROJ-456").
        """
        raise NotImplementedError

    @abstractmethod
    def crear_test_plan(self, summary: str, project_key: str) -> str:
        """
        Crea un Test Plan nuevo, sin tests asociados todavía. Se usa cuando
        no se encontró ningún Test Plan vinculado a la HU y el usuario
        decide crear uno en vez de continuar sin vínculo.

        Args:
            summary: título del Test Plan.
            project_key: proyecto Jira donde crearlo.

        Returns:
            La key de Jira del Test Plan creado (ej. "PROJ-50").
        """
        raise NotImplementedError
