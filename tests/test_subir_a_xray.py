"""
Tests para SubirTestCaseAXray: orquestación entre JiraCloudAdapter (resolver
proyecto destino) y TestManagementSystem (Xray, crear el Test).
"""

import pytest

from domain.models import EstadoTestCase, TestCase
from ports.issue_tracker import IssueTracker
from ports.test_management import TestManagementSystem
from application.subir_a_xray import SubirTestCaseAXray


class IssueTrackerFake(IssueTracker):
    def __init__(self, project_key_devuelto: str = "PROJ"):
        self._project_key_devuelto = project_key_devuelto
        self.ultima_key_consultada: str | None = None

    def obtener_hu(self, key):
        raise NotImplementedError

    def detectar_test_plan(self, key_hu):
        raise NotImplementedError

    def vincular_test_plan_a_hu(self, key_hu: str, key_test_plan: str) -> None:
        raise NotImplementedError

    def project_key_de(self, key_issue: str) -> str:
        self.ultima_key_consultada = key_issue
        return self._project_key_devuelto

    def obtener_fecha_entrada_qa(self, key_hu):


        raise NotImplementedError


class TestManagementSystemFake(TestManagementSystem):
    __test__ = False

    def __init__(self, key_devuelta: str = "PROJ-999", excepcion: Exception | None = None):
        self._key_devuelta = key_devuelta
        self._excepcion = excepcion
        self.ultima_llamada: dict | None = None

    def crear_test(self, test_case, key_test_plan, project_key_destino=None):
        self.ultima_llamada = {
            "test_case": test_case,
            "key_test_plan": key_test_plan,
            "project_key_destino": project_key_destino,
        }
        if self._excepcion:
            raise self._excepcion
        return self._key_devuelta

    def crear_test_plan(self, summary: str, project_key: str) -> str:
        raise NotImplementedError


def _crear_test_case_aprobado(**overrides) -> TestCase:
    base = dict(
        titulo="Login OK",
        gherkin="Scenario: Login OK\n  Given x\n  Then y",
        hu_key="PROJ-1",
        estado=EstadoTestCase.APROBADO,
    )
    base.update(overrides)
    return TestCase(**base)


class TestSubirTestCaseAXray:
    def test_solo_sube_test_cases_en_estado_aprobado(self):
        tc = _crear_test_case_aprobado(estado=EstadoTestCase.PENDIENTE)
        caso_de_uso = SubirTestCaseAXray(IssueTrackerFake(), TestManagementSystemFake())

        with pytest.raises(ValueError, match="APROBADO"):
            caso_de_uso.ejecutar(tc, key_test_plan="PROJ-45")

    def test_rechazado_tampoco_se_puede_subir(self):
        tc = _crear_test_case_aprobado(estado=EstadoTestCase.RECHAZADO)
        caso_de_uso = SubirTestCaseAXray(IssueTrackerFake(), TestManagementSystemFake())

        with pytest.raises(ValueError, match="APROBADO"):
            caso_de_uso.ejecutar(tc, key_test_plan="PROJ-45")

    def test_resuelve_project_key_automaticamente_desde_el_test_plan(self):
        tc = _crear_test_case_aprobado()
        issue_tracker = IssueTrackerFake(project_key_devuelto="PROJ")
        test_management = TestManagementSystemFake()

        SubirTestCaseAXray(issue_tracker, test_management).ejecutar(tc, key_test_plan="PROJ-45")

        assert issue_tracker.ultima_key_consultada == "PROJ-45"
        assert test_management.ultima_llamada["project_key_destino"] == "PROJ"

    def test_project_key_destino_explicito_evita_consultar_el_test_plan(self):
        tc = _crear_test_case_aprobado()
        issue_tracker = IssueTrackerFake()
        test_management = TestManagementSystemFake()

        SubirTestCaseAXray(issue_tracker, test_management).ejecutar(
            tc, key_test_plan="PROJ-45", project_key_destino="OTRO"
        )

        assert issue_tracker.ultima_key_consultada is None
        assert test_management.ultima_llamada["project_key_destino"] == "OTRO"

    def test_sin_test_plan_y_sin_project_key_destino_lanza_error_claro(self):
        tc = _crear_test_case_aprobado()
        caso_de_uso = SubirTestCaseAXray(IssueTrackerFake(), TestManagementSystemFake())

        with pytest.raises(ValueError, match="proyecto destino"):
            caso_de_uso.ejecutar(tc, key_test_plan=None)

    def test_actualiza_xray_test_key_y_estado_al_subir_exitosamente(self):
        tc = _crear_test_case_aprobado()
        caso_de_uso = SubirTestCaseAXray(IssueTrackerFake(), TestManagementSystemFake(key_devuelta="PROJ-777"))

        resultado = caso_de_uso.ejecutar(tc, key_test_plan="PROJ-45")

        assert resultado.xray_test_key == "PROJ-777"
        assert resultado.estado == EstadoTestCase.SUBIDO_A_XRAY

    def test_si_xray_falla_el_test_case_se_queda_en_aprobado_no_se_pierde(self):


        tc = _crear_test_case_aprobado()
        test_management = TestManagementSystemFake(excepcion=ConnectionError("Xray no responde"))
        caso_de_uso = SubirTestCaseAXray(IssueTrackerFake(), test_management)

        with pytest.raises(ConnectionError):
            caso_de_uso.ejecutar(tc, key_test_plan="PROJ-45")

        assert tc.estado == EstadoTestCase.APROBADO
        assert tc.xray_test_key is None

    def test_funciona_sin_test_plan_si_se_da_project_key_destino(self):
        tc = _crear_test_case_aprobado()
        test_management = TestManagementSystemFake()
        caso_de_uso = SubirTestCaseAXray(IssueTrackerFake(), test_management)

        caso_de_uso.ejecutar(tc, key_test_plan=None, project_key_destino="PROJ")

        assert test_management.ultima_llamada["key_test_plan"] is None
        assert tc.estado == EstadoTestCase.SUBIDO_A_XRAY

    def test_retorna_el_mismo_objeto_mutado_no_uno_nuevo(self):
        tc = _crear_test_case_aprobado()
        caso_de_uso = SubirTestCaseAXray(IssueTrackerFake(), TestManagementSystemFake())

        resultado = caso_de_uso.ejecutar(tc, key_test_plan="PROJ-45")

        assert resultado is tc
