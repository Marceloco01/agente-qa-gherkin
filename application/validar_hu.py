"""
Caso de uso: Vera -- valida una HU antes de que Gio genere test cases.

Dos pasos, en este orden exacto (decisión de eficiencia confirmada con el
usuario): primero un chequeo determinista por código (gratis, sin LLM) que
busca si la HU depende de contenido visual que el agente no puede leer (ej.
"ver IMAGEN 1"); si lo encuentra, bloquea ahí mismo sin gastar ninguna
llamada al LLM. Solo si ese chequeo pasa, se le pide al LLM que puntúe
claridad, completitud de criterios reales y testabilidad.

Decisiones de diseño documentadas el 2026-08-28 (umbral, bloqueo y persistencia; esta fecha no establece la primera disponibilidad de Vera):
- Umbral de aprobación configurable vía UMBRAL_SCORE_HU (.env), no
  hardcodeado (default 70).
- Score bajo (< umbral) bloquea la generación; el resultado queda
  persistido para el indicador del Dashboard (ver
  application/generar_test_cases.py y Repository.actualizar_evaluacion_vera).
- Dependencia visual bloquea SIEMPRE, sin importar qué tan bien puntúe lo
  demás -- pasa sí o sí por revisión humana.
"""

from __future__ import annotations

import re

from domain.models import EvaluacionHU, HistoriaUsuario
from infrastructure.config import cargar_configuracion_vera, obtener_logger
from ports.llm_provider import LLMProvider

_log = obtener_logger(__name__)


_PATRON_DEPENDENCIA_VISUAL = re.compile(
    r"\b(imagen|im[aá]genes|ver\s+adjunto|adjunto|captura|screenshot)\b",
    re.IGNORECASE,
)


class ValidarHU:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider
        self._umbral = cargar_configuracion_vera().umbral_score

    def ejecutar(self, hu: HistoriaUsuario) -> EvaluacionHU:
        coincidencia = _PATRON_DEPENDENCIA_VISUAL.search(hu.descripcion or "")
        if coincidencia:
            _log.warning(
                "Vera bloqueó %s: la descripción menciona '%s', posible "
                "dependencia de contenido visual que el agente no puede leer",
                hu.key, coincidencia.group(0),
            )
            return EvaluacionHU(
                aprobada=False,
                depende_de_imagen=True,
                score=None,
                criterios_faltantes=[],
                detalle=(
                    f"La HU menciona '{coincidencia.group(0)}' en su descripción. "
                    "El agente solo puede leer texto, no puede evaluar contenido "
                    "visual (imágenes, capturas, adjuntos). Revisá esta HU "
                    "manualmente antes de continuar."
                ),
            )

        _log.info("Vera evaluando %s con el LLM (claridad, completitud, testabilidad)", hu.key)
        score, criterios_faltantes, detalle = self._llm_provider.evaluar_hu(hu)

        aprobada = score >= self._umbral
        if not aprobada:
            _log.warning(
                "Vera bloqueó %s: score %s < umbral %s. Faltantes: %s",
                hu.key, score, self._umbral, criterios_faltantes,
            )
        else:
            _log.info("Vera aprobó %s con score %s", hu.key, score)

        return EvaluacionHU(
            aprobada=aprobada,
            depende_de_imagen=False,
            score=score,
            criterios_faltantes=criterios_faltantes,
            detalle=detalle,
            umbral=self._umbral,
        )
