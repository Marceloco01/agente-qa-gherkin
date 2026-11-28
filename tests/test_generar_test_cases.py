"""
Tests del caso de uso GenerarTestCases, usando dobles de prueba (fakes) de
IssueTracker y LLMProvider — así se valida la orquestación sin depender de
Jira ni Ollama reales.
"""

from domain.models import HistoriaUsuario, TestCase
from ports.issue_tracker import IssueTracker
from ports.llm_provider import LLMProvider
from ports.repository import Repository
from ports.vector_store import VectorStore
from application.generar_test_cases import GenerarTestCases


class IssueTrackerFake(IssueTracker):
    def __init__(self, hu: HistoriaUsuario):
        self._hu = hu

    def obtener_hu(self, key: str) -> HistoriaUsuario:
        return self._hu

    def detectar_test_plan(self, key_hu: str) -> list[str]:
        raise NotImplementedError

    def vincular_test_plan_a_hu(self, key_hu: str, key_test_plan: str) -> None:
        raise NotImplementedError

    def project_key_de(self, key_issue: str) -> str:
        raise NotImplementedError

    def obtener_fecha_entrada_qa(self, key_hu):


        raise NotImplementedError


class LLMProviderFake(LLMProvider):
    def __init__(self, test_cases: list[TestCase]):
        self._test_cases = test_cases
        self.ultima_llamada_casos_similares = "no_llamado"

    def generar_test_cases(self, hu: HistoriaUsuario, casos_similares=None) -> list[TestCase]:
        self.ultima_llamada_casos_similares = casos_similares
        return self._test_cases

    def generar_test_case_individual(self, hu, descripcion_escenario):
        raise NotImplementedError

    def regenerar_test_case(self, gherkin_actual, titulo_actual, historial_feedback):
        raise NotImplementedError

    def generar_embedding(self, texto: str) -> list[float]:
        raise NotImplementedError

    def verificar_alucinacion(self, test_cases, contexto):
        raise NotImplementedError

    def evaluar_hu(self, hu):


        return 100, [], "Aprobada por el fake de prueba"


    def clasificar_cobertura_criterios(self, criterios, tests):
        raise NotImplementedError

    def interpretar_dashboard(self, metricas):
        raise NotImplementedError

    def chat_nexus_insights(self, contexto, historial, pregunta):
        raise NotImplementedError


class RepositoryFake(Repository):
    def guardar_hu(self, hu): pass
    def guardar_test_cases(self, test_cases): pass
    def actualizar_estado(self, test_case_id, estado, autor): pass
    def guardar_feedback(self, test_case_id, autor, mensaje): pass
    def actualizar_test_case_completo(self, test_case): pass

    def actualizar_alucinacion(self, test_case_id, alucinacion_detectada, alucinacion_detalle): pass
    def actualizar_evaluacion_vera(self, hu_key, score, aprobada, motivo_bloqueo, umbral_aplicado=None): pass
    def registrar_generacion(self, hu_key, forzada, descripcion_usada): pass
    def actualizar_fecha_fin_proceso(self, hu_key): pass


class VectorStoreFake(VectorStore):
    def guardar_embedding(self, referencia_id, vector, metadata): pass
    def buscar_similares(self, vector, top_k) -> list[dict]:
        return []


def _caso_de_uso(hu, test_cases):
    """Helper: construye GenerarTestCases con todos los fakes requeridos."""
    return GenerarTestCases(
        issue_tracker=IssueTrackerFake(hu),
        llm_provider=LLMProviderFake(test_cases),
        repository=RepositoryFake(),
        vector_store=VectorStoreFake(),
    )


class TestGenerarTestCases:
    def test_devuelve_la_hu_y_los_test_cases_generados(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="x" * 100)
        test_cases = [TestCase(titulo="Login OK", gherkin="Scenario: x", hu_key="PROJ-1")]

        caso_de_uso = _caso_de_uso(hu, test_cases)

        resultado = caso_de_uso.ejecutar("PROJ-1")

        assert resultado.hu == hu
        assert resultado.test_cases == test_cases

    def test_fase_1_no_pasa_casos_similares_al_llm(self):


        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="x" * 100)
        llm_fake = LLMProviderFake([])

        caso_de_uso = GenerarTestCases(
            issue_tracker=IssueTrackerFake(hu),
            llm_provider=llm_fake,
            repository=RepositoryFake(),
            vector_store=VectorStoreFake(),
        )
        caso_de_uso.ejecutar("PROJ-1")

        assert llm_fake.ultima_llamada_casos_similares is None

    def test_marca_descripcion_pobre_correctamente(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="muy corta")

        caso_de_uso = _caso_de_uso(hu, [])
        resultado = caso_de_uso.ejecutar("PROJ-1")

        assert resultado.descripcion_es_pobre is True

    def test_no_marca_descripcion_pobre_cuando_es_suficiente(self):
        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="x" * 100)

        caso_de_uso = _caso_de_uso(hu, [])
        resultado = caso_de_uso.ejecutar("PROJ-1")

        assert resultado.descripcion_es_pobre is False

    def test_no_bloquea_la_generacion_aunque_la_descripcion_sea_pobre(self):


        hu = HistoriaUsuario(key="PROJ-1", titulo="Login", descripcion="corta")
        test_cases = [TestCase(titulo="x", gherkin="Scenario: x", hu_key="PROJ-1")]

        caso_de_uso = _caso_de_uso(hu, test_cases)
        resultado = caso_de_uso.ejecutar("PROJ-1")

        assert resultado.test_cases == test_cases
        assert resultado.descripcion_es_pobre is True
