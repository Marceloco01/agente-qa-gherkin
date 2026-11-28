"""
Caso de uso: agregar un test case nuevo a la lista de una HU (como experto QA,
agregar manualmente o pedirle a la IA que lo redacte a partir de una
descripción del escenario).

Esto es distinto de `generar_test_cases.py` (genera varios casos de una vez,
automáticamente, al traer la HU) y de `revisar_test_case.py` (opera sobre
casos que ya existen en la lista). Este caso de uso crea un `TestCase` nuevo
desde cero y lo deja en estado PENDIENTE, listo para entrar al mismo flujo de
revisión que los demás.
"""

from __future__ import annotations

from domain.models import EstadoTestCase, HistoriaUsuario, TestCase
from infrastructure.config import obtener_logger
from ports.llm_provider import LLMProvider

_log = obtener_logger(__name__)


class AgregarTestCase:
    def __init__(self, llm_provider: LLMProvider | None = None):
        """
        Args:
            llm_provider: necesario solo para `agregar_con_ia()`. Se puede
                omitir si solo se va a usar `agregar_manual()` (ej. en tests
                que no necesitan tocar el LLM).
        """
        self._llm_provider = llm_provider

    def agregar_manual(self, hu_key: str, titulo: str, gherkin: str) -> TestCase:
        """
        Agrega un test case escrito directamente por el usuario, sin pasar
        por el LLM. Queda en estado PENDIENTE, igual que cualquier otro caso
        recién generado -- entra al mismo flujo de revisión 1×1.
        """
        if not gherkin.strip():
            raise ValueError("El Gherkin no puede estar vacío.")

        test_case = TestCase(
            titulo=titulo.strip() or "(sin título)",
            gherkin=gherkin.strip(),
            hu_key=hu_key,
            estado=EstadoTestCase.PENDIENTE,
        )
        _log.info("Test case manual agregado para %s: '%s'", hu_key, test_case.titulo)
        return test_case

    def agregar_con_ia(self, hu: HistoriaUsuario, descripcion_escenario: str) -> TestCase:
        """
        Le pide al LLM que redacte un test case nuevo a partir de una
        descripción libre del escenario (ej. "que pase si la contraseña
        tiene menos de 8 caracteres"). Queda en estado PENDIENTE.
        """
        if self._llm_provider is None:
            raise ValueError("agregar_con_ia() requiere un LLMProvider; no se proporcionó ninguno.")
        if not descripcion_escenario.strip():
            raise ValueError("La descripción del escenario no puede estar vacía.")

        _log.info("Generando test case con IA para %s, escenario: '%s'", hu.key, descripcion_escenario)
        gherkin, titulo = self._llm_provider.generar_test_case_individual(hu, descripcion_escenario)

        test_case = TestCase(
            titulo=titulo,
            gherkin=gherkin,
            hu_key=hu.key,
            estado=EstadoTestCase.PENDIENTE,
        )
        _log.info("Test case con IA agregado para %s: '%s'", hu.key, test_case.titulo)
        return test_case
