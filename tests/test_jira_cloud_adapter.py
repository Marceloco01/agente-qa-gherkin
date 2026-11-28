"""Tests para la extracción de texto plano desde formato ADF de Jira."""

from unittest.mock import MagicMock

import httpx
import pytest

from adapters.issue_tracker.jira_cloud_adapter import JiraCloudAdapter


class TestAdfATexto:
    def test_adf_none_devuelve_string_vacio(self):
        assert JiraCloudAdapter._adf_a_texto(None) == ""

    def test_adf_sin_contenido_devuelve_string_vacio(self):
        assert JiraCloudAdapter._adf_a_texto({"type": "doc", "content": []}) == ""

    def test_un_parrafo_simple(self):
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Hola mundo"}]}
            ],
        }
        assert JiraCloudAdapter._adf_a_texto(adf) == "Hola mundo"

    def test_varios_parrafos_quedan_en_lineas_separadas(self):
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Primera línea"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Segunda línea"}]},
            ],
        }
        texto = JiraCloudAdapter._adf_a_texto(adf)
        assert texto == "Primera línea\nSegunda línea"

    def test_bullet_list_genera_guiones(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "Item uno"}]}
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "Item dos"}]}
                            ],
                        },
                    ],
                }
            ],
        }
        texto = JiraCloudAdapter._adf_a_texto(adf)
        assert "- Item uno" in texto
        assert "- Item dos" in texto

    def test_marks_de_formato_se_ignoran_pero_texto_se_conserva(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "texto en negrita",
                            "marks": [{"type": "strong"}],
                        }
                    ],
                }
            ],
        }
        texto = JiraCloudAdapter._adf_a_texto(adf)
        assert texto == "texto en negrita"

    def test_tipo_no_reconocido_no_pierde_texto_anidado(self):


        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "panel",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Texto en panel"}]}
                    ],
                }
            ],
        }
        texto = JiraCloudAdapter._adf_a_texto(adf)
        assert "Texto en panel" in texto

    def test_caso_realista_parrafo_y_lista_combinados(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Como usuario quiero loguearme."}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Criterios de aceptación:"}],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Valida email."}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Muestra error si falla."}],
                                }
                            ],
                        },
                    ],
                },
            ],
        }
        texto = JiraCloudAdapter._adf_a_texto(adf)
        assert texto == (
            "Como usuario quiero loguearme.\n"
            "Criterios de aceptación:\n"
            "- Valida email.\n"
            "- Muestra error si falla."
        )


class TestDetectarTestPlan:
    """
    Usa el endpoint de búsqueda JQL (/rest/api/3/search/jql) en vez de
    confiar en los campos anidados de `issuelinks`, porque en la práctica el
    campo `issuetype` del issue vinculado no siempre viene poblado ahí (esto
    causaba que la detección fallara en silencio incluso cuando el Test Plan
    sí existía y estaba bien vinculado).
    """

    def _crear_adapter_con_respuesta(self, issues: list[dict]) -> JiraCloudAdapter:
        adapter = JiraCloudAdapter(base_url="https://x.atlassian.net", email="a@b.com", api_token="t")
        respuesta_mock = MagicMock()
        respuesta_mock.json.return_value = {"issues": issues}
        respuesta_mock.raise_for_status.return_value = None
        adapter._client.post = MagicMock(return_value=respuesta_mock)
        return adapter

    def test_encuentra_test_plan_cuando_la_busqueda_devuelve_un_resultado(self):
        issues = [{"key": "PROJ-45", "fields": {"summary": "Test Plan - Login", "status": {"name": "Open"}}}]
        adapter = self._crear_adapter_con_respuesta(issues)

        resultado = adapter.detectar_test_plan("PROJ-1")

        assert len(resultado) == 1
        assert resultado[0].key == "PROJ-45"
        assert resultado[0].titulo == "Test Plan - Login"
        assert resultado[0].estado == "Open"

    def test_devuelve_lista_vacia_si_la_busqueda_no_encuentra_nada(self):
        adapter = self._crear_adapter_con_respuesta([])
        assert adapter.detectar_test_plan("PROJ-1") == []

    def test_usa_el_endpoint_de_busqueda_jql_correcto(self):
        adapter = self._crear_adapter_con_respuesta([])
        adapter.detectar_test_plan("PROJ-1")

        args, kwargs = adapter._client.post.call_args
        url_llamada = args[0] if args else kwargs.get("url")
        assert url_llamada == "https://x.atlassian.net/rest/api/3/search/jql"

    def test_pide_key_summary_y_status_en_la_misma_consulta(self):


        adapter = self._crear_adapter_con_respuesta([])
        adapter.detectar_test_plan("PROJ-1")

        _, kwargs = adapter._client.post.call_args
        assert set(kwargs["json"]["fields"]) == {"key", "summary", "status"}

    def test_construye_el_jql_exacto_con_linkedissues_y_type_test_plan(self):


        adapter = self._crear_adapter_con_respuesta([])
        adapter.detectar_test_plan("HU-001")

        _, kwargs = adapter._client.post.call_args
        jql_enviado = kwargs["json"]["jql"]
        assert jql_enviado == (
            'issue in linkedIssues("HU-001", "Será atendido por") AND type = "Test Plan"'
        )

    def test_devuelve_todos_si_hay_varios_resultados_con_su_titulo_y_estado(self):


        issues = [
            {"key": "PROJ-45", "fields": {"summary": "Test Plan - viejo", "status": {"name": "Done"}}},
            {"key": "PROJ-46", "fields": {"summary": "Test Plan - nuevo", "status": {"name": "Open"}}},
        ]
        adapter = self._crear_adapter_con_respuesta(issues)

        resultado = adapter.detectar_test_plan("PROJ-1")

        assert [tp.key for tp in resultado] == ["PROJ-45", "PROJ-46"]
        assert resultado[0].titulo == "Test Plan - viejo"
        assert resultado[0].estado == "Done"
        assert resultado[1].titulo == "Test Plan - nuevo"
        assert resultado[1].estado == "Open"

    def test_summary_o_status_faltantes_no_rompen_no_quedan_strings_vacios(self):


        issues = [{"key": "PROJ-45", "fields": {}}]
        adapter = self._crear_adapter_con_respuesta(issues)

        resultado = adapter.detectar_test_plan("PROJ-1")

        assert resultado[0].titulo == ""
        assert resultado[0].estado == ""


_TIPOS_DE_LINK_REALISTAS = {
    "issueLinkTypes": [
        {"id": "10000", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
        {"id": "10001", "name": "Gestion de Pruebas", "inward": "Será atendido por", "outward": "Atiende"},
        {"id": "10002", "name": "Cloners", "inward": "is cloned by", "outward": "clones"},
    ]
}


class TestVincularTestPlanAHu:
    def _crear_adapter_con_post_exitoso(self) -> JiraCloudAdapter:
        adapter = JiraCloudAdapter(base_url="https://x.atlassian.net", email="a@b.com", api_token="t")

        respuesta_tipos = MagicMock()
        respuesta_tipos.json.return_value = _TIPOS_DE_LINK_REALISTAS
        respuesta_tipos.raise_for_status.return_value = None
        adapter._client.get = MagicMock(return_value=respuesta_tipos)

        respuesta_link = MagicMock()
        respuesta_link.raise_for_status.return_value = None
        adapter._client.post = MagicMock(return_value=respuesta_link)

        return adapter

    def test_llama_al_endpoint_correcto(self):
        adapter = self._crear_adapter_con_post_exitoso()
        adapter.vincular_test_plan_a_hu(key_hu="PROJ-1", key_test_plan="PROJ-50")

        args, kwargs = adapter._client.post.call_args
        url_llamada = args[0] if args else kwargs.get("url")
        assert url_llamada == "https://x.atlassian.net/rest/api/3/issueLink"

    def test_usa_el_nombre_interno_real_no_el_texto_visible(self):


        adapter = self._crear_adapter_con_post_exitoso()
        adapter.vincular_test_plan_a_hu(key_hu="PROJ-1", key_test_plan="PROJ-50")

        _, kwargs = adapter._client.post.call_args
        assert kwargs["json"]["type"] == {"name": "Gestion de Pruebas"}

    def test_hu_va_como_inward_y_test_plan_como_outward(self):
        adapter = self._crear_adapter_con_post_exitoso()
        adapter.vincular_test_plan_a_hu(key_hu="PROJ-1", key_test_plan="PROJ-50")

        _, kwargs = adapter._client.post.call_args
        assert kwargs["json"]["inwardIssue"] == {"key": "PROJ-1"}
        assert kwargs["json"]["outwardIssue"] == {"key": "PROJ-50"}

    def test_error_http_se_convierte_en_value_error_con_detalle(self):


        adapter = self._crear_adapter_con_post_exitoso()

        respuesta_error = MagicMock()
        respuesta_error.status_code = 404
        respuesta_error.json.return_value = {
            "errorMessages": ["No se encontró un tipo de enlace a incidencia con el nombre 'X'."]
        }
        respuesta_error.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=respuesta_error
        )
        adapter._client.post = MagicMock(return_value=respuesta_error)

        with pytest.raises(ValueError, match="No se encontró un tipo de enlace"):
            adapter.vincular_test_plan_a_hu(key_hu="PROJ-1", key_test_plan="PROJ-50")

    def test_error_sin_body_parseable_usa_el_texto_crudo(self):
        adapter = self._crear_adapter_con_post_exitoso()

        respuesta_error = MagicMock()
        respuesta_error.status_code = 500
        respuesta_error.json.side_effect = ValueError()
        respuesta_error.text = "Internal Server Error"
        respuesta_error.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=respuesta_error
        )
        adapter._client.post = MagicMock(return_value=respuesta_error)

        with pytest.raises(ValueError, match="Internal Server Error"):
            adapter.vincular_test_plan_a_hu(key_hu="PROJ-1", key_test_plan="PROJ-50")

    def test_el_resultado_se_cachea_no_pide_los_tipos_dos_veces(self):
        adapter = self._crear_adapter_con_post_exitoso()

        adapter.vincular_test_plan_a_hu(key_hu="PROJ-1", key_test_plan="PROJ-50")
        adapter.vincular_test_plan_a_hu(key_hu="PROJ-2", key_test_plan="PROJ-51")

        assert adapter._client.get.call_count == 1


class TestResolverNombreRealDeLink:
    def _crear_adapter_con_tipos(self, tipos: dict) -> JiraCloudAdapter:
        adapter = JiraCloudAdapter(base_url="https://x.atlassian.net", email="a@b.com", api_token="t")
        respuesta = MagicMock()
        respuesta.json.return_value = tipos
        respuesta.raise_for_status.return_value = None
        adapter._client.get = MagicMock(return_value=respuesta)
        return adapter

    def test_encuentra_por_inward(self):
        adapter = self._crear_adapter_con_tipos({
            "issueLinkTypes": [
                {"name": "X", "inward": "Será atendido por", "outward": "Y"},
            ]
        })
        assert adapter._resolver_nombre_real_de_link() == "X"

    def test_encuentra_por_outward(self):
        adapter = self._crear_adapter_con_tipos({
            "issueLinkTypes": [
                {"name": "X", "inward": "Y", "outward": "Atiende"},
            ]
        })
        assert adapter._resolver_nombre_real_de_link() == "X"

    def test_busqueda_no_distingue_mayusculas(self):
        adapter = self._crear_adapter_con_tipos({
            "issueLinkTypes": [
                {"name": "X", "inward": "SERÁ ATENDIDO POR", "outward": "Y"},
            ]
        })
        assert adapter._resolver_nombre_real_de_link() == "X"

    def test_no_encontrar_ninguno_lanza_error_con_los_disponibles(self):
        adapter = self._crear_adapter_con_tipos({
            "issueLinkTypes": [
                {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
            ]
        })
        with pytest.raises(ValueError, match="Blocks"):
            adapter._resolver_nombre_real_de_link()

    def test_llama_al_endpoint_correcto(self):
        adapter = self._crear_adapter_con_tipos({"issueLinkTypes": []})
        try:
            adapter._resolver_nombre_real_de_link()
        except ValueError:
            pass

        args, kwargs = adapter._client.get.call_args
        url_llamada = args[0] if args else kwargs.get("url")
        assert url_llamada == "https://x.atlassian.net/rest/api/3/issueLinkType"


class TestExtraerDetalleError:
    def _adapter(self) -> JiraCloudAdapter:
        return JiraCloudAdapter(base_url="https://x.atlassian.net", email="a@b.com", api_token="t")

    def test_extrae_error_messages(self):
        respuesta = MagicMock()
        respuesta.json.return_value = {"errorMessages": ["No tienes permiso."]}
        assert self._adapter()._extraer_detalle_error(respuesta) == "No tienes permiso."

    def test_extrae_errors_por_campo(self):
        respuesta = MagicMock()
        respuesta.json.return_value = {"errorMessages": [], "errors": {"issuetype": "Tipo inválido."}}
        assert self._adapter()._extraer_detalle_error(respuesta) == "issuetype: Tipo inválido."

    def test_combina_error_messages_y_errors_si_hay_ambos(self):
        respuesta = MagicMock()
        respuesta.json.return_value = {
            "errorMessages": ["Mensaje general."],
            "errors": {"campo": "Detalle del campo."},
        }
        detalle = self._adapter()._extraer_detalle_error(respuesta)
        assert "Mensaje general." in detalle
        assert "campo: Detalle del campo." in detalle

    def test_sin_body_parseable_devuelve_texto_crudo(self):
        respuesta = MagicMock()
        respuesta.json.side_effect = ValueError()
        respuesta.text = "texto plano de error"
        assert self._adapter()._extraer_detalle_error(respuesta) == "texto plano de error"
