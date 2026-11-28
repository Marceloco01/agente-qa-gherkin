"""
Caso de uso: Nora interpreta las métricas operativas del Dashboard.

Decisión de diseño (2026-09-02):
- Nora vive como sección fija dentro de `frontend/pages/1_📊_Dashboard.py`
  (no una página aparte, no un chat libre en esta primera versión).
- El alcance de esta primera versión es SOLO operativo: tiempos, tasa de
  alucinación, volumen y mezcla de tipos de test case (camino_feliz/borde/
  error de Gio), y HU bloqueadas por Vera por score insuficiente. Nada del
  criterio del QA sobre casos puntuales -- eso no es asunto de Nora.
- Es bajo demanda, no automática en cada rerun de Streamlit: Streamlit
  re-ejecuta toda la página en cada interacción (cambiar un filtro, tocar
  un botón, etc.), así que llamar al LLM sin control gastaría tokens sin
  que el usuario lo pida. Este caso de uso se llama SOLO cuando el frontend
  decide explícitamente pedir un análisis nuevo (botón "Analizar con
  Nora"), y el frontend cachea el resultado en `st.session_state` por
  período+filtro para no repetir la llamada en reruns posteriores del
  mismo período.

Esta clase es una capa delgada a propósito -- no tiene lógica propia más
allá de delegar a `LLMProvider.interpretar_dashboard()` (ver
`ports/llm_provider.py`). Existe como caso de uso, en vez de llamar al
provider directo desde el frontend, por el mismo motivo que el resto de
`application/`: mantener el frontend sin saber nada de qué proveedor de LLM
hay por debajo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ports.llm_provider import LLMProvider


@dataclass
class InterpretacionDashboard:
    resumen: str
    recomendaciones: list[str] = field(default_factory=list)


class InterpretarDashboard:
    def __init__(self, llm_provider: LLMProvider):
        self._llm_provider = llm_provider

    def ejecutar(self, metricas: dict) -> InterpretacionDashboard:
        resumen, recomendaciones = self._llm_provider.interpretar_dashboard(metricas)
        return InterpretacionDashboard(resumen=resumen, recomendaciones=recomendaciones)
