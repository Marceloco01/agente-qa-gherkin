"""
Tests para XrayCloudAdapter: renovación de token, escapado GraphQL, el
flujo completo de crear_test() (creación + vinculación a Test Plan), y el
reintento ante errores de re-indexación pendiente en Xray.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from adapters.issue_tracker.xray_cloud_adapter import (
    XrayCloudAdapter,
    _DURACION_TOKEN_SEGUNDOS,
    _MARGEN_SEGURIDAD_SEGUNDOS,
    _REINTENTOS_REINDEXACION,
)
from domain.models import TestCase


def _crear_adapter_con_post_mockeado(token_devuelto: str = "token-de-prueba"):
    adapter = XrayCloudAdapter(client_id="id123", client_secret="secret456")
    respuesta_mock = MagicMock()
    respuesta_mock.json.return_value = token_devuelto
    respuesta_mock.raise_for_status.return_value = None
    adapter._client.post = MagicMock(return_value=respuesta_mock)
    return adapter


def _mock_json(valor):
    m = MagicMock()
    m.json.return_value = valor
    m.raise_for_status.return_value = None
    return m


def _crear_adapter_con_secuencia_graphql(*respuestas_graphql, token="token-abc"):
    """
    Crea un adapter cuyo `_client.post` devuelve, en orden: primero el token
    de autenticación, y luego cada una de las respuestas GraphQL indicadas.
    """
    adapter = XrayCloudAdapter(client_id="id123", client_secret="secret456")
    secuencia = [_mock_json(token)] + [_mock_json(r) for r in respuestas_graphql]
    adapter._client.post = MagicMock(side_effect=secuencia)
    return adapter


class TestTokenValido:
    def test_primera_llamada_autentica(self):
        adapter = _crear_adapter_con_post_mockeado("token-abc")
        token = adapter._token_valido()

        assert token == "token-abc"
        assert adapter._client.post.call_count == 1

    def test_llamada_envia_client_id_y_secret_correctos(self):
        adapter = _crear_adapter_con_post_mockeado()
        adapter._token_valido()

        _, kwargs = adapter._client.post.call_args
        assert kwargs["json"] == {"client_id": "id123", "client_secret": "secret456"}

    def test_segunda_llamada_inmediata_no_reautentica(self):
        adapter = _crear_adapter_con_post_mockeado()
        adapter._token_valido()
        adapter._token_valido()

        assert adapter._client.post.call_count == 1

    def test_token_por_expirar_se_renueva_automaticamente(self):
        adapter = _crear_adapter_con_post_mockeado()
        adapter._token_valido()


        adapter._token_obtenido_en = time.monotonic() - (
            _DURACION_TOKEN_SEGUNDOS - _MARGEN_SEGURIDAD_SEGUNDOS + 1
        )
        adapter._token_valido()

        assert adapter._client.post.call_count == 2

    def test_token_recien_obtenido_no_se_renueva(self):
        adapter = _crear_adapter_con_post_mockeado()
        adapter._token_valido()


        adapter._token_obtenido_en = time.monotonic() - 10
        adapter._token_valido()

        assert adapter._client.post.call_count == 1


class TestEscaparParaGraphql:
    """
    El Gherkin generado por el LLM siempre tiene saltos de línea, y puede
    tener comillas dentro de los pasos (ej. nombres de campos, valores
    esperados) -- por eso este escapado no es un caso límite raro, es el
    caso normal.
    """

    def test_texto_simple_no_cambia(self):
        assert XrayCloudAdapter._escapar_para_graphql("texto simple") == "texto simple"

    def test_comillas_dobles_se_escapan(self):
        resultado = XrayCloudAdapter._escapar_para_graphql('con "comillas"')
        assert resultado == 'con \\"comillas\\"'

    def test_saltos_de_linea_se_convierten_a_n_literal(self):
        resultado = XrayCloudAdapter._escapar_para_graphql("linea1\nlinea2")
        assert resultado == "linea1\\nlinea2"

    def test_backslash_se_escapa(self):
        resultado = XrayCloudAdapter._escapar_para_graphql("con \\ backslash")
        assert resultado == "con \\\\ backslash"

    def test_combinacion_realista_de_gherkin(self):
        gherkin = 'Scenario: Login\n  Given el campo "usuario" está vacío\n  Then ve error'
        escapado = XrayCloudAdapter._escapar_para_graphql(gherkin)

        assert "\n" not in escapado
        assert '\\"' in escapado
        assert "\\n" in escapado

    def test_escapado_es_reversible_via_json(self):


        import json

        original = 'Scenario: con "comillas" y \nsalto y \\ backslash'
        escapado = XrayCloudAdapter._escapar_para_graphql(original)
        reconstruido = json.loads(f'"{escapado}"')
        assert reconstruido == original


class TestCrearTest:
    def test_requiere_project_key_destino(self):
        adapter = _crear_adapter_con_post_mockeado()
        tc = TestCase(titulo="x", gherkin="Scenario: x", hu_key="PROJ-1")

        with pytest.raises(ValueError, match="project_key_destino"):
            adapter.crear_test(tc, key_test_plan=None, project_key_destino=None)

    def test_crea_test_y_vincula_a_test_plan(self):
        adapter = _crear_adapter_con_secuencia_graphql(
            {"data": {"createTest": {"test": {"issueId": "9001"}, "warnings": []}}},
            {"data": {"getTestPlans": {"results": [{"issueId": "8001"}]}}},
            {"data": {"addTestsToTestPlan": {"addedTests": ["9001"], "warning": None}}},
            {"data": {"getTest": {"jira": {"key": "PROJ-999"}}}},
        )
        tc = TestCase(titulo="Login OK", gherkin="Scenario: Login OK\n  Given x\n  Then y", hu_key="PROJ-1")

        resultado = adapter.crear_test(tc, key_test_plan="PROJ-45", project_key_destino="PROJ")

        assert resultado == "PROJ-999"

        assert adapter._client.post.call_count == 5

    def test_crea_test_sin_test_plan_no_llama_a_vincular(self):
        adapter = _crear_adapter_con_secuencia_graphql(
            {"data": {"createTest": {"test": {"issueId": "9001"}, "warnings": []}}},
            {"data": {"getTest": {"jira": {"key": "PROJ-999"}}}},
        )
        tc = TestCase(titulo="Sin TP", gherkin="Scenario: x", hu_key="PROJ-1")

        resultado = adapter.crear_test(tc, key_test_plan=None, project_key_destino="PROJ")

        assert resultado == "PROJ-999"

        assert adapter._client.post.call_count == 3

    def test_test_plan_no_encontrado_lanza_error_claro(self):
        adapter = _crear_adapter_con_secuencia_graphql(
            {"data": {"createTest": {"test": {"issueId": "9001"}, "warnings": []}}},
            {"data": {"getTestPlans": {"results": []}}},
        )
        tc = TestCase(titulo="x", gherkin="Scenario: x", hu_key="PROJ-1")

        with pytest.raises(ValueError, match="no encontró ningún Test Plan"):
            adapter.crear_test(tc, key_test_plan="PROJ-999-NO-EXISTE", project_key_destino="PROJ")

    def test_vinculacion_no_confirmada_lanza_error(self):


        adapter = _crear_adapter_con_secuencia_graphql(
            {"data": {"createTest": {"test": {"issueId": "9001"}, "warnings": []}}},
            {"data": {"getTestPlans": {"results": [{"issueId": "8001"}]}}},
            {"data": {"addTestsToTestPlan": {"addedTests": [], "warning": "algo falló"}}},
        )
        tc = TestCase(titulo="x", gherkin="Scenario: x", hu_key="PROJ-1")

        with pytest.raises(ValueError, match="No se pudo confirmar"):
            adapter.crear_test(tc, key_test_plan="PROJ-45", project_key_destino="PROJ")

    def test_errores_de_graphql_se_propagan(self):

        adapter = _crear_adapter_con_secuencia_graphql(
            {"errors": [{"message": "Field 'summary' is required"}]},
        )
        tc = TestCase(titulo="", gherkin="Scenario: x", hu_key="PROJ-1")

        with pytest.raises(ValueError, match="errores"):
            adapter.crear_test(tc, key_test_plan=None, project_key_destino="PROJ")


class TestCrearTestPlan:
    def test_crea_test_plan_y_devuelve_su_key(self):
        adapter = _crear_adapter_con_secuencia_graphql(
            {"data": {"createTestPlan": {"testPlan": {"issueId": "7001"}, "warnings": []}}},
            {"data": {"getTestPlan": {"jira": {"key": "PROJ-50"}}}},
        )

        resultado = adapter.crear_test_plan(summary="Test Plan - Login", project_key="PROJ")

        assert resultado == "PROJ-50"

        assert adapter._client.post.call_count == 3

    def test_envia_el_summary_y_project_key_correctos(self):
        adapter = _crear_adapter_con_secuencia_graphql(
            {"data": {"createTestPlan": {"testPlan": {"issueId": "7001"}, "warnings": []}}},
            {"data": {"getTestPlan": {"jira": {"key": "PROJ-50"}}}},
        )

        adapter.crear_test_plan(summary="Test Plan - Login de usuario", project_key="PROJ")

        _, kwargs = adapter._client.post.call_args_list[1]
        query_enviada = kwargs["json"]["query"]
        assert "Test Plan - Login de usuario" in query_enviada
        assert 'project: { key: "PROJ" }' in query_enviada

    def test_escapa_el_summary_con_comillas(self):
        adapter = _crear_adapter_con_secuencia_graphql(
            {"data": {"createTestPlan": {"testPlan": {"issueId": "7001"}, "warnings": []}}},
            {"data": {"getTestPlan": {"jira": {"key": "PROJ-50"}}}},
        )


        adapter.crear_test_plan(summary='Test Plan - HU con "comillas"', project_key="PROJ")

        assert adapter._client.post.call_count == 3

    def test_no_encontrar_el_test_plan_recien_creado_lanza_error_claro(self):
        adapter = _crear_adapter_con_secuencia_graphql(
            {"data": {"createTestPlan": {"testPlan": {"issueId": "7001"}, "warnings": []}}},
            {"data": {"getTestPlan": None}},
        )

        with pytest.raises(ValueError, match="No se pudo recuperar la key"):
            adapter.crear_test_plan(summary="Test Plan - x", project_key="PROJ")


class TestReintentoDeIndexacion:
    """
    Caso real observado: justo después de crear un Test Plan en Xray, pedirle
    sus campos de Jira puede fallar con "...the project may need to be
    re-indexed!" -- es un estado transitorio (Xray no tiene aún la info de
    Jira de ese issue disponible internamente), no un error real. Se
    reintenta con espera creciente antes de propagar el error.
    """

    _ERROR_REINDEXACION = {
        "errors": [{"message": "Error collecting jira information for issue '246353', the project may need to be re-indexed!"}]
    }
    _ERROR_DISTINTO = {"errors": [{"message": "Field 'summary' is required"}]}

    def test_reintenta_y_consigue_exito_tras_fallar_con_error_de_reindexacion(self):
        adapter = _crear_adapter_con_secuencia_graphql(
            self._ERROR_REINDEXACION,
            self._ERROR_REINDEXACION,
            {"data": {"getTestPlan": {"jira": {"key": "PROJ-50"}}}},
        )

        with patch("adapters.issue_tracker.xray_cloud_adapter.time.sleep") as mock_sleep:
            resultado = adapter._obtener_key_de_issue_id_test_plan("246353")

        assert resultado == "PROJ-50"

        assert adapter._client.post.call_count == 4
        assert mock_sleep.call_count == 2

    def test_la_espera_crece_exponencialmente(self):
        adapter = _crear_adapter_con_secuencia_graphql(
            self._ERROR_REINDEXACION,
            self._ERROR_REINDEXACION,
            {"data": {"getTestPlan": {"jira": {"key": "PROJ-50"}}}},
        )

        with patch("adapters.issue_tracker.xray_cloud_adapter.time.sleep") as mock_sleep:
            adapter._obtener_key_de_issue_id_test_plan("246353")

        esperas = [llamada.args[0] for llamada in mock_sleep.call_args_list]
        assert esperas == [2.0, 4.0]

    def test_no_reintenta_ante_un_error_de_graphql_distinto(self):
        adapter = _crear_adapter_con_secuencia_graphql(self._ERROR_DISTINTO)

        with patch("adapters.issue_tracker.xray_cloud_adapter.time.sleep") as mock_sleep:
            with pytest.raises(ValueError, match="summary"):
                adapter._obtener_key_de_issue_id_test_plan("246353")

        assert mock_sleep.call_count == 0

        assert adapter._client.post.call_count == 2

    def test_propaga_el_error_si_persiste_tras_agotar_los_reintentos(self):
        respuestas = [self._ERROR_REINDEXACION] * _REINTENTOS_REINDEXACION
        adapter = _crear_adapter_con_secuencia_graphql(*respuestas)

        with patch("adapters.issue_tracker.xray_cloud_adapter.time.sleep"):
            with pytest.raises(ValueError, match="re-indexed"):
                adapter._obtener_key_de_issue_id_test_plan("246353")


        assert adapter._client.post.call_count == _REINTENTOS_REINDEXACION + 1

    def test_obtener_key_de_test_tambien_usa_el_reintento(self):

        adapter = _crear_adapter_con_secuencia_graphql(
            self._ERROR_REINDEXACION,
            {"data": {"getTest": {"jira": {"key": "PROJ-999"}}}},
        )

        with patch("adapters.issue_tracker.xray_cloud_adapter.time.sleep"):
            resultado = adapter._obtener_key_de_issue_id("9001")

        assert resultado == "PROJ-999"
