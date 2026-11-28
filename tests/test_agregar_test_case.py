"""Tests para AgregarTestCase: agregar manual y agregar vía IA."""

import pytest

from domain.models import EstadoTestCase, HistoriaUsuario
from ports.llm_provider import LLMProvider
from application.agregar_test_case import AgregarTestCase


class LLMProviderFake(LLMProvider):
    def __init__(self, gherkin_devuelto: str = "Scenario: x", titulo_devuelto: str = "x"):
        self._gherkin_devuelto = gherkin_devuelto
        self._titulo_devuelto = titulo_devuelto
        self.ultima_descripcion_escenario: str | None = None
        self.ultima_hu: HistoriaUsuario | None = None

    def generar_test_cases(self, hu, casos_similares=None):
        raise NotImplementedError

    def generar_test_case_individual(self, hu, descripcion_escenario):
        self.ultima_hu = hu
        self.ultima_descripcion_escenario = descripcion_escenario
        return self._gherkin_devuelto, self._titulo_devuelto

    def regenerar_test_case(self, gherkin_actual, titulo_actual, historial_feedback):
        raise NotImplementedError

    def generar_embedding(self, texto):
        raise NotImplementedError

    def verificar_alucinacion(self, test_cases, contexto):
        raise NotImplementedError


    def evaluar_hu(self, hu):
        raise NotImplementedError

    def clasificar_cobertura_criterios(self, criterios, tests):
        raise NotImplementedError

    def interpretar_dashboard(self, metricas):
        raise NotImplementedError

    def chat_nexus_insights(self, contexto, historial, pregunta):
        raise NotImplementedError


class TestAgregarManual:
    def test_agrega_con_titulo_y_gherkin_dados(self):
        resultado = AgregarTestCase().agregar_manual(
            hu_key="PROJ-1", titulo="Mi caso", gherkin="Scenario: Mi caso\n  Given x\n  Then y",
        )

        assert resultado.titulo == "Mi caso"
        assert resultado.gherkin == "Scenario: Mi caso\n  Given x\n  Then y"
        assert resultado.hu_key == "PROJ-1"

    def test_queda_en_estado_pendiente(self):
        resultado = AgregarTestCase().agregar_manual(
            hu_key="PROJ-1", titulo="x", gherkin="Scenario: x",
        )
        assert resultado.estado == EstadoTestCase.PENDIENTE

    def test_gherkin_vacio_lanza_error(self):
        with pytest.raises(ValueError, match="no puede estar vacío"):
            AgregarTestCase().agregar_manual(hu_key="PROJ-1", titulo="x", gherkin="   ")

    def test_titulo_vacio_usa_fallback(self):
        resultado = AgregarTestCase().agregar_manual(
            hu_key="PROJ-1", titulo="  ", gherkin="Scenario: x",
        )
        assert resultado.titulo == "(sin título)"

    def test_recorta_espacios(self):
        resultado = AgregarTestCase().agregar_manual(
            hu_key="PROJ-1", titulo="  Mi caso  ", gherkin="  Scenario: x  \n",
        )
        assert resultado.titulo == "Mi caso"
        assert resultado.gherkin == "Scenario: x"

    def test_no_requiere_llm_provider(self):

        caso_de_uso = AgregarTestCase(llm_provider=None)
        resultado = caso_de_uso.agregar_manual(hu_key="PROJ-1", titulo="x", gherkin="Scenario: x")
        assert resultado.titulo == "x"


class TestAgregarConIA:
    def test_agrega_con_gherkin_y_titulo_del_llm(self):
        llm_fake = LLMProviderFake(gherkin_devuelto="Scenario: Generado", titulo_devuelto="Caso generado")
        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="x" * 60)

        resultado = AgregarTestCase(llm_fake).agregar_con_ia(hu, "que falle con contraseña corta")

        assert resultado.gherkin == "Scenario: Generado"
        assert resultado.titulo == "Caso generado"
        assert resultado.hu_key == "PROJ-1"

    def test_queda_en_estado_pendiente(self):
        llm_fake = LLMProviderFake()
        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="x" * 60)

        resultado = AgregarTestCase(llm_fake).agregar_con_ia(hu, "escenario")

        assert resultado.estado == EstadoTestCase.PENDIENTE

    def test_pasa_la_hu_y_descripcion_al_llm(self):
        llm_fake = LLMProviderFake()
        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="x" * 60)

        AgregarTestCase(llm_fake).agregar_con_ia(hu, "que pase si la contraseña es corta")

        assert llm_fake.ultima_hu == hu
        assert llm_fake.ultima_descripcion_escenario == "que pase si la contraseña es corta"

    def test_sin_llm_provider_lanza_error_claro(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="x" * 60)
        caso_de_uso = AgregarTestCase(llm_provider=None)

        with pytest.raises(ValueError, match="requiere un LLMProvider"):
            caso_de_uso.agregar_con_ia(hu, "escenario")

    def test_descripcion_de_escenario_vacia_lanza_error(self):
        llm_fake = LLMProviderFake()
        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="x" * 60)

        with pytest.raises(ValueError, match="no puede estar vacía"):
            AgregarTestCase(llm_fake).agregar_con_ia(hu, "   ")
