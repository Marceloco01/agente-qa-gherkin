"""
v1.0.2: falla segura de la verificación de alucinaciones, bloqueo de la
aprobación en el caso de uso y registro del umbral de Vera.
"""

import pytest

from application.generar_casos import GenerarCasos
from application.revisar_test_case import RegenerarTestCase, RevisarTestCase
from application.validar_hu import ValidarHU
from domain.exceptions import AprobacionBloqueadaError
from domain.models import (
    DETALLE_VERIFICACION_NO_DISPONIBLE,
    EstadoTestCase,
    HistoriaUsuario,
    TestCase,
)
from tests.test_generar_test_cases import (
    LLMProviderFake as LLMGeneracionFake,
    RepositoryFake as RepoGeneracionFake,
    VectorStoreFake,
)
from tests.test_revisar_test_case import (
    LLMProviderFake as LLMRevisionFake,
    RepositoryFake as RepoRevisionFake,
)

GHERKIN = "Scenario: x\n  Given a\n  When b\n  Then c"


def _tc(titulo="Caso"):
    return TestCase(titulo=titulo, gherkin=GHERKIN, hu_key="PROJ-1")


class _LLMVerificadorFalla(LLMGeneracionFake):
    def verificar_alucinacion(self, test_cases, contexto):
        raise RuntimeError("Ollama no responde")


class _LLMVerificadorVacio(LLMGeneracionFake):
    def verificar_alucinacion(self, test_cases, contexto):
        return []


class _LLMVerificadorParcial(LLMGeneracionFake):
    def verificar_alucinacion(self, test_cases, contexto):
        return [{"test_case_id": test_cases[0].id, "alucinado": False, "razon": ""}]


def _generar(llm_cls, test_cases):
    hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="x" * 100)
    caso = GenerarCasos(
        llm_provider=llm_cls(test_cases),
        repository=RepoGeneracionFake(),
        vector_store=VectorStoreFake(),
    )
    caso.ejecutar(hu)
    return caso


class TestFallaSeguraGeneracion:
    def test_si_el_verificador_falla_todos_quedan_marcados(self):
        tcs = [_tc("a"), _tc("b")]
        caso = _generar(_LLMVerificadorFalla, tcs)
        assert all(t.alucinacion_detectada for t in tcs)
        assert all(t.alucinacion_detalle == DETALLE_VERIFICACION_NO_DISPONIBLE for t in tcs)
        assert caso.verificaciones_no_disponibles == 2

    def test_respuesta_vacia_marca_los_casos(self):
        tcs = [_tc()]
        caso = _generar(_LLMVerificadorVacio, tcs)
        assert tcs[0].alucinacion_detectada
        assert caso.verificaciones_no_disponibles == 1

    def test_solo_se_marcan_los_casos_sin_resultado(self):
        tcs = [_tc("a"), _tc("b")]
        caso = _generar(_LLMVerificadorParcial, tcs)
        assert tcs[0].alucinacion_detectada is False
        assert tcs[1].alucinacion_detectada is True
        assert caso.verificaciones_no_disponibles == 1


class TestBloqueoDeAprobacion:
    def test_aprobar_caso_marcado_lanza_error(self):
        tc = _tc()
        tc.alucinacion_detectada = True
        repo = RepoRevisionFake()
        with pytest.raises(AprobacionBloqueadaError):
            RevisarTestCase(repo).aprobar(tc)
        assert tc.estado == EstadoTestCase.PENDIENTE
        assert repo.estados_actualizados == []

    def test_editar_y_aprobar_sigue_permitido(self):
        tc = _tc()
        tc.alucinacion_detectada = True
        RevisarTestCase(RepoRevisionFake()).editar_y_aprobar(tc, GHERKIN + " editado")
        assert tc.estado == EstadoTestCase.APROBADO


class _LLMRegeneraSinVerificar(LLMRevisionFake):
    def verificar_alucinacion(self, test_cases, contexto):
        raise RuntimeError("timeout")


class TestFallaSeguraRegeneracion:
    def test_regenerar_sin_verificacion_deja_el_caso_marcado(self):
        tc = _tc()
        assert tc.alucinacion_detectada is False
        RegenerarTestCase(
            llm_provider=_LLMRegeneraSinVerificar("Scenario: nuevo", "Nuevo"),
            repository=RepoRevisionFake(),
        ).regenerar(tc, "corrige el paso 2", "descripcion de la HU")
        assert tc.alucinacion_detectada is True
        assert tc.alucinacion_detalle == DETALLE_VERIFICACION_NO_DISPONIBLE


class _LLMVera(LLMGeneracionFake):
    def __init__(self, score):
        super().__init__([])
        self._score = score

    def evaluar_hu(self, hu):
        return self._score, [], "ok"


class TestUmbralRegistrado:
    def test_validar_hu_devuelve_el_umbral_vigente(self, monkeypatch):
        monkeypatch.setenv("UMBRAL_SCORE_HU", "35")
        hu = HistoriaUsuario(key="PROJ-1", titulo="t", descripcion="x" * 100)
        ev = ValidarHU(_LLMVera(40)).ejecutar(hu)
        assert ev.umbral == 35
        assert ev.aprobada is True

    def test_dependencia_visual_no_registra_umbral(self, monkeypatch):
        monkeypatch.setenv("UMBRAL_SCORE_HU", "62")
        hu = HistoriaUsuario(key="PROJ-1", titulo="t", descripcion="Ver la imagen adjunta " + "x" * 80)
        ev = ValidarHU(_LLMVera(90)).ejecutar(hu)
        assert ev.depende_de_imagen is True
        assert ev.umbral is None
