"""Tests para OllamaProvider, en particular el parseo robusto de JSON."""

import json
from unittest.mock import MagicMock

import pytest

from adapters.llm.ollama_provider import OllamaProvider
from domain.models import HistoriaUsuario, MensajeFeedback


class TestParsearRespuestaJson:
    def test_json_limpio(self):
        contenido = '{"test_cases": [{"titulo": "Login OK", "gherkin": "Scenario: x"}]}'
        resultado = OllamaProvider._parsear_respuesta_json(contenido)
        assert resultado["test_cases"][0]["titulo"] == "Login OK"

    def test_json_envuelto_en_markdown_fences(self):
        contenido = '```json\n{"test_cases": []}\n```'
        resultado = OllamaProvider._parsear_respuesta_json(contenido)
        assert resultado == {"test_cases": []}

    def test_json_con_texto_explicativo_alrededor(self):
        contenido = 'Aquí tienes el resultado:\n{"test_cases": []}\nListo.'
        resultado = OllamaProvider._parsear_respuesta_json(contenido)
        assert resultado == {"test_cases": []}

    def test_json_invalido_lanza_value_error(self):
        with pytest.raises(ValueError):
            OllamaProvider._parsear_respuesta_json("esto no es json")

    def test_json_con_llaves_pero_estructura_rota_lanza_value_error(self):
        with pytest.raises(ValueError):
            OllamaProvider._parsear_respuesta_json("{esto: 'no es', json: valido,}")

    def test_json_con_saltos_de_linea_reales_sin_escapar_se_tolera(self):


        contenido = '{"titulo": "x", "gherkin": "Scenario: x\n  Given a\n  Then b"}'
        resultado = OllamaProvider._parsear_respuesta_json(contenido)
        assert resultado["titulo"] == "x"
        assert "Given a" in resultado["gherkin"]


class TestRegenerarTestCase:
    def _provider_con_respuesta(self, contenido_json: str) -> OllamaProvider:
        provider = OllamaProvider(modelo="llama3.1:8b")
        provider._client.chat = MagicMock(return_value={"message": {"content": contenido_json}})
        return provider

    def test_regenera_con_feedback_devuelve_gherkin_y_titulo_nuevos(self):
        contenido = json.dumps({
            "titulo": "Login corregido",
            "gherkin": "Scenario: Login corregido\n  Given x\n  Then y",
        })
        provider = self._provider_con_respuesta(contenido)

        historial = [MensajeFeedback(autor="usuario", texto="Falta validar contraseña vacía")]
        nuevo_gherkin, nuevo_titulo = provider.regenerar_test_case(
            gherkin_actual="Scenario: Login\n  Given x\n  Then y",
            titulo_actual="Login",
            historial_feedback=historial,
        )

        assert nuevo_titulo == "Login corregido"
        assert "Login corregido" in nuevo_gherkin

    def test_incluye_todo_el_historial_en_el_prompt(self):
        contenido = json.dumps({"titulo": "x", "gherkin": "Scenario: x"})
        provider = self._provider_con_respuesta(contenido)

        historial = [
            MensajeFeedback(autor="usuario", texto="primer comentario"),
            MensajeFeedback(autor="agente", texto="Test case regenerado según tu feedback."),
            MensajeFeedback(autor="usuario", texto="segundo comentario, todavía falta algo"),
        ]
        provider.regenerar_test_case(
            gherkin_actual="Scenario: x",
            titulo_actual="x",
            historial_feedback=historial,
        )

        _, kwargs = provider._client.chat.call_args
        prompt_enviado = kwargs["messages"][1]["content"]
        assert "primer comentario" in prompt_enviado
        assert "segundo comentario" in prompt_enviado

    def test_si_llm_no_devuelve_titulo_usa_el_actual_como_fallback(self):
        contenido = json.dumps({"titulo": "", "gherkin": "Scenario: x corregido"})
        provider = self._provider_con_respuesta(contenido)

        _, nuevo_titulo = provider.regenerar_test_case(
            gherkin_actual="Scenario: x",
            titulo_actual="Título original",
            historial_feedback=[],
        )

        assert nuevo_titulo == "Título original"

    def test_gherkin_vacio_lanza_value_error(self):
        contenido = json.dumps({"titulo": "x", "gherkin": ""})
        provider = self._provider_con_respuesta(contenido)

        with pytest.raises(ValueError, match="Gherkin vacío"):
            provider.regenerar_test_case(
                gherkin_actual="Scenario: x",
                titulo_actual="x",
                historial_feedback=[],
            )


class TestGenerarTestCaseIndividual:
    def _provider_con_respuesta(self, contenido_json: str) -> OllamaProvider:
        provider = OllamaProvider(modelo="llama3.1:8b")
        provider._client.chat = MagicMock(return_value={"message": {"content": contenido_json}})
        return provider

    def test_genera_gherkin_y_titulo_a_partir_de_la_descripcion(self):
        contenido = json.dumps({
            "titulo": "Contraseña corta",
            "gherkin": "Scenario: Contraseña corta\n  Given x\n  Then y",
        })
        provider = self._provider_con_respuesta(contenido)
        hu = HistoriaUsuario(key="PROJ-1", titulo="Registro", descripcion="x" * 60)

        gherkin, titulo = provider.generar_test_case_individual(hu, "que pase si la contraseña es corta")

        assert titulo == "Contraseña corta"
        assert "Contraseña corta" in gherkin

    def test_incluye_la_descripcion_del_escenario_en_el_prompt(self):
        contenido = json.dumps({"titulo": "x", "gherkin": "Scenario: x"})
        provider = self._provider_con_respuesta(contenido)
        hu = HistoriaUsuario(key="PROJ-1", titulo="Registro", descripcion="x" * 60)

        provider.generar_test_case_individual(hu, "escenario muy específico de prueba")

        _, kwargs = provider._client.chat.call_args
        prompt_enviado = kwargs["messages"][1]["content"]
        assert "escenario muy específico de prueba" in prompt_enviado

    def test_incluye_titulo_y_descripcion_de_la_hu_en_el_prompt(self):
        contenido = json.dumps({"titulo": "x", "gherkin": "Scenario: x"})
        provider = self._provider_con_respuesta(contenido)
        hu = HistoriaUsuario(key="PROJ-1", titulo="Registro de usuario", descripcion="Texto de la HU" * 5)

        provider.generar_test_case_individual(hu, "escenario")

        _, kwargs = provider._client.chat.call_args
        prompt_enviado = kwargs["messages"][1]["content"]
        assert "Registro de usuario" in prompt_enviado
        assert "Texto de la HU" in prompt_enviado

    def test_gherkin_vacio_lanza_value_error(self):
        contenido = json.dumps({"titulo": "x", "gherkin": ""})
        provider = self._provider_con_respuesta(contenido)
        hu = HistoriaUsuario(key="PROJ-1", titulo="x", descripcion="x" * 60)

        with pytest.raises(ValueError, match="Gherkin vacío"):
            provider.generar_test_case_individual(hu, "escenario")
