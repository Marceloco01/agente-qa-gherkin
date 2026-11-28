"""
Tests para CrearTestPlanParaHU: orquestación entre TestManagementSystem
(crear el Test Plan en Xray) e IssueTracker (vincularlo a la HU en Jira).
"""

import pytest

from ports.issue_tracker import IssueTracker
from ports.test_management import TestManagementSystem
from application.crear_test_plan import CrearTestPlanParaHU


class IssueTrackerFake(IssueTracker):
    def __init__(self, excepcion: Exception | None = None):
        self._excepcion = excepcion
        self.ultima_vinculacion: dict | None = None

    def obtener_hu(self, key):
        raise NotImplementedError

    def detectar_test_plan(self, key_hu):
        raise NotImplementedError

    def vincular_test_plan_a_hu(self, key_hu: str, key_test_plan: str) -> None:
        self.ultima_vinculacion = {"key_hu": key_hu, "key_test_plan": key_test_plan}
        if self._excepcion:
            raise self._excepcion

    def project_key_de(self, key_issue: str) -> str:
        raise NotImplementedError

    def obtener_fecha_entrada_qa(self, key_hu):


        raise NotImplementedError


class TestManagementSystemFake(TestManagementSystem):
    __test__ = False

    def __init__(self, key_devuelta: str = "PROJ-50"):
        self._key_devuelta = key_devuelta
        self.ultima_llamada: dict | None = None

    def crear_test(self, test_case, key_test_plan, project_key_destino=None):
        raise NotImplementedError

    def crear_test_plan(self, summary: str, project_key: str) -> str:
        self.ultima_llamada = {"summary": summary, "project_key": project_key}
        return self._key_devuelta


class TestCrearTestPlanParaHU:
    def test_crea_el_test_plan_con_el_summary_indicado(self):
        test_management = TestManagementSystemFake()
        caso_de_uso = CrearTestPlanParaHU(IssueTrackerFake(), test_management)

        caso_de_uso.ejecutar(key_hu="PROJ-1", summary="Test Plan - Login de usuario", project_key="PROJ")

        assert test_management.ultima_llamada["summary"] == "Test Plan - Login de usuario"
        assert test_management.ultima_llamada["project_key"] == "PROJ"

    def test_no_le_agrega_ningun_prefijo_al_summary_recibido(self):


        test_management = TestManagementSystemFake()
        caso_de_uso = CrearTestPlanParaHU(IssueTrackerFake(), test_management)

        caso_de_uso.ejecutar(key_hu="PROJ-1", summary="Cualquier título custom", project_key="PROJ")

        assert test_management.ultima_llamada["summary"] == "Cualquier título custom"

    def test_vincula_el_test_plan_creado_a_la_hu(self):
        issue_tracker = IssueTrackerFake()
        test_management = TestManagementSystemFake(key_devuelta="PROJ-77")
        caso_de_uso = CrearTestPlanParaHU(issue_tracker, test_management)

        caso_de_uso.ejecutar(key_hu="PROJ-1", summary="Test Plan - Login", project_key="PROJ")

        assert issue_tracker.ultima_vinculacion == {"key_hu": "PROJ-1", "key_test_plan": "PROJ-77"}

    def test_devuelve_la_key_del_test_plan_creado(self):
        test_management = TestManagementSystemFake(key_devuelta="PROJ-99")
        caso_de_uso = CrearTestPlanParaHU(IssueTrackerFake(), test_management)

        resultado = caso_de_uso.ejecutar(key_hu="PROJ-1", summary="Test Plan - Login", project_key="PROJ")

        assert resultado == "PROJ-99"

    def test_si_la_vinculacion_falla_el_error_incluye_la_key_del_test_plan_ya_creado(self):


        issue_tracker = IssueTrackerFake(excepcion=ConnectionError("Jira no responde"))
        test_management = TestManagementSystemFake(key_devuelta="PROJ-77")
        caso_de_uso = CrearTestPlanParaHU(issue_tracker, test_management)

        with pytest.raises(ValueError, match="PROJ-77"):
            caso_de_uso.ejecutar(key_hu="PROJ-1", summary="Test Plan - Login", project_key="PROJ")

    def test_el_error_de_vinculacion_menciona_que_no_hace_falta_crear_otro(self):
        issue_tracker = IssueTrackerFake(excepcion=ConnectionError("Jira no responde"))
        caso_de_uso = CrearTestPlanParaHU(issue_tracker, TestManagementSystemFake())

        with pytest.raises(ValueError, match="no es necesario crear otro"):
            caso_de_uso.ejecutar(key_hu="PROJ-1", summary="Test Plan - Login", project_key="PROJ")
