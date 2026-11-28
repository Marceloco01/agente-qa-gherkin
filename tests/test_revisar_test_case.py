"""
Tests para RevisarTestCase (aprobar/editar/rechazar/descartar) y
RegenerarTestCase (chat de feedback -> nueva versión vía LLM).
"""

import pytest

from domain.models import EstadoTestCase, MensajeFeedback, TestCase
from ports.llm_provider import LLMProvider
from ports.repository import Repository
from application.revisar_test_case import RegenerarTestCase, RevisarTestCase


class LLMProviderFake(LLMProvider):
    """Fake mínimo, solo implementa regenerar_test_case (lo único que usa este caso de uso)."""

    def __init__(self, gherkin_devuelto: str, titulo_devuelto: str):
        self._gherkin_devuelto = gherkin_devuelto
        self._titulo_devuelto = titulo_devuelto
        self.historial_recibido: list[MensajeFeedback] | None = None

    def generar_test_cases(self, hu, casos_similares=None):
        raise NotImplementedError

    def generar_test_case_individual(self, hu, descripcion_escenario):
        raise NotImplementedError

    def regenerar_test_case(self, gherkin_actual, titulo_actual, historial_feedback):
        self.historial_recibido = list(historial_feedback)
        return self._gherkin_devuelto, self._titulo_devuelto

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


class RepositoryFake(Repository):
    """Fake mínimo que registra las llamadas para verificarlas en los tests."""

    def __init__(self):
        self.estados_actualizados: list[tuple] = []
        self.feedback_guardado: list[tuple] = []
        self.test_cases_sincronizados: list = []

    def guardar_hu(self, hu):
        pass

    def guardar_test_cases(self, test_cases):
        pass

    def actualizar_estado(self, test_case_id, estado, autor):
        self.estados_actualizados.append((test_case_id, estado, autor))

    def actualizar_test_case_completo(self, test_case):
        self.test_cases_sincronizados.append(test_case)

    def guardar_feedback(self, test_case_id, autor, mensaje):
        self.feedback_guardado.append((test_case_id, autor, mensaje))


    def actualizar_alucinacion(self, test_case_id, alucinacion_detectada, alucinacion_detalle):
        pass

    def actualizar_evaluacion_vera(self, hu_key, score, aprobada, motivo_bloqueo, umbral_aplicado=None):
        pass

    def registrar_generacion(self, hu_key, forzada, descripcion_usada):
        pass

    def actualizar_fecha_fin_proceso(self, hu_key):
        pass


def _crear_test_case(**overrides) -> TestCase:
    base = dict(titulo="Login OK", gherkin="Scenario: Login OK\n  Given x\n  Then y", hu_key="PROJ-1")
    base.update(overrides)
    return TestCase(**base)


class TestRevisarTestCaseAprobar:
    def test_aprobar_cambia_estado_a_aprobado(self):
        tc = _crear_test_case()
        RevisarTestCase(repository=RepositoryFake()).aprobar(tc)

        assert tc.estado == EstadoTestCase.APROBADO

    def test_aprobar_no_toca_el_gherkin_ni_el_titulo(self):
        tc = _crear_test_case(titulo="Original", gherkin="Scenario: Original")
        RevisarTestCase(repository=RepositoryFake()).aprobar(tc)

        assert tc.titulo == "Original"
        assert tc.gherkin == "Scenario: Original"


class TestRevisarTestCaseEditarYAprobar:
    def test_editar_y_aprobar_cambia_gherkin_y_estado(self):
        tc = _crear_test_case(gherkin="Scenario: Viejo")
        RevisarTestCase(repository=RepositoryFake()).editar_y_aprobar(tc, nuevo_gherkin="Scenario: Nuevo")

        assert tc.gherkin == "Scenario: Nuevo"
        assert tc.estado == EstadoTestCase.APROBADO

    def test_editar_y_aprobar_puede_cambiar_tambien_el_titulo(self):
        tc = _crear_test_case(titulo="Viejo")
        RevisarTestCase(repository=RepositoryFake()).editar_y_aprobar(tc, nuevo_gherkin="Scenario: x", nuevo_titulo="Nuevo")

        assert tc.titulo == "Nuevo"

    def test_editar_y_aprobar_sin_nuevo_titulo_conserva_el_actual(self):
        tc = _crear_test_case(titulo="Se mantiene")
        RevisarTestCase(repository=RepositoryFake()).editar_y_aprobar(tc, nuevo_gherkin="Scenario: x")

        assert tc.titulo == "Se mantiene"

    def test_editar_y_aprobar_recorta_espacios(self):
        tc = _crear_test_case()
        RevisarTestCase(repository=RepositoryFake()).editar_y_aprobar(tc, nuevo_gherkin="  Scenario: x  \n", nuevo_titulo="  Titulo  ")

        assert tc.gherkin == "Scenario: x"
        assert tc.titulo == "Titulo"


class TestRevisarTestCaseRechazar:
    def test_rechazar_cambia_estado_a_rechazado(self):
        tc = _crear_test_case()
        RevisarTestCase(repository=RepositoryFake()).rechazar(tc)

        assert tc.estado == EstadoTestCase.RECHAZADO

    def test_rechazar_con_motivo_lo_agrega_al_historial(self):
        tc = _crear_test_case()
        RevisarTestCase(repository=RepositoryFake()).rechazar(tc, motivo="Falta un caso de error")

        assert len(tc.historial_feedback) == 1
        assert tc.historial_feedback[0].autor == "usuario"
        assert tc.historial_feedback[0].texto == "Falta un caso de error"

    def test_rechazar_sin_motivo_no_agrega_nada_al_historial(self):
        tc = _crear_test_case()
        RevisarTestCase(repository=RepositoryFake()).rechazar(tc)

        assert tc.historial_feedback == []


class TestRevisarTestCaseDescartar:
    def test_descartar_con_motivo_no_lanza_error(self):
        tc = _crear_test_case()
        RevisarTestCase(repository=RepositoryFake()).descartar(tc, motivo="ya no aplica")


    def test_descartar_no_muta_el_estado_del_test_case(self):


        tc = _crear_test_case()
        estado_original = tc.estado

        RevisarTestCase(repository=RepositoryFake()).descartar(tc, motivo="ya no aplica")

        assert tc.estado == estado_original

    def test_descartar_sin_motivo_lanza_value_error(self):
        tc = _crear_test_case()
        with pytest.raises(ValueError, match="no puede estar vacío"):
            RevisarTestCase(repository=RepositoryFake()).descartar(tc, motivo="")

    def test_descartar_con_motivo_de_solo_espacios_lanza_value_error(self):
        tc = _crear_test_case()
        with pytest.raises(ValueError, match="no puede estar vacío"):
            RevisarTestCase(repository=RepositoryFake()).descartar(tc, motivo="   ")


class TestRegenerarTestCase:
    def test_regenerar_actualiza_gherkin_y_titulo(self):
        llm_fake = LLMProviderFake(gherkin_devuelto="Scenario: Corregido", titulo_devuelto="Corregido")
        tc = _crear_test_case(estado=EstadoTestCase.RECHAZADO)

        resultado = RegenerarTestCase(llm_provider=llm_fake, repository=RepositoryFake()).regenerar(tc, "Falta validar X")

        assert resultado.gherkin == "Scenario: Corregido"
        assert resultado.titulo == "Corregido"

    def test_regenerar_vuelve_a_estado_pendiente(self):
        llm_fake = LLMProviderFake(gherkin_devuelto="Scenario: x", titulo_devuelto="x")
        tc = _crear_test_case(estado=EstadoTestCase.RECHAZADO)

        RegenerarTestCase(llm_provider=llm_fake, repository=RepositoryFake()).regenerar(tc, "feedback")

        assert tc.estado == EstadoTestCase.PENDIENTE

    def test_regenerar_agrega_mensaje_del_usuario_al_historial(self):
        llm_fake = LLMProviderFake(gherkin_devuelto="Scenario: x", titulo_devuelto="x")
        tc = _crear_test_case()

        RegenerarTestCase(llm_provider=llm_fake, repository=RepositoryFake()).regenerar(tc, "Falta el caso de error 404")

        mensajes_usuario = [m for m in tc.historial_feedback if m.autor == "usuario"]
        assert any(m.texto == "Falta el caso de error 404" for m in mensajes_usuario)

    def test_regenerar_agrega_confirmacion_del_agente_al_historial(self):
        llm_fake = LLMProviderFake(gherkin_devuelto="Scenario: x", titulo_devuelto="x")
        tc = _crear_test_case()

        RegenerarTestCase(llm_provider=llm_fake, repository=RepositoryFake()).regenerar(tc, "feedback")

        mensajes_agente = [m for m in tc.historial_feedback if m.autor == "agente"]
        assert len(mensajes_agente) == 1

    def test_regenerar_pasa_todo_el_historial_acumulado_al_llm_no_solo_el_ultimo(self):
        llm_fake = LLMProviderFake(gherkin_devuelto="Scenario: x", titulo_devuelto="x")
        tc = _crear_test_case()
        tc.historial_feedback.append(MensajeFeedback(autor="usuario", texto="comentario previo"))

        RegenerarTestCase(llm_provider=llm_fake, repository=RepositoryFake()).regenerar(tc, "comentario nuevo")

        textos = [m.texto for m in llm_fake.historial_recibido]
        assert "comentario previo" in textos
        assert "comentario nuevo" in textos

    def test_regenerar_incrementa_version_contenido(self):


        llm_fake = LLMProviderFake(gherkin_devuelto="Scenario: x", titulo_devuelto="x")
        tc = _crear_test_case()
        version_inicial = tc.version_contenido

        RegenerarTestCase(llm_provider=llm_fake, repository=RepositoryFake()).regenerar(tc, "feedback")

        assert tc.version_contenido == version_inicial + 1

    def test_regenerar_muta_el_mismo_objeto_no_crea_uno_nuevo(self):
        llm_fake = LLMProviderFake(gherkin_devuelto="Scenario: x", titulo_devuelto="x")
        tc = _crear_test_case()
        id_original = tc.id

        resultado = RegenerarTestCase(llm_provider=llm_fake, repository=RepositoryFake()).regenerar(tc, "feedback")

        assert resultado is tc
        assert resultado.id == id_original
