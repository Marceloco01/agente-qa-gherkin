"""
Caso de uso: Nexus Insights, el chat real sobre todo el universo analítico
de NEXUS (`frontend/pages/7_💬_Nexus_Insights.py`).

Decisión de diseño (2026-09-02): Nexus Insights reemplaza a
Nora (`application/interpretar_dashboard.py`) como la capacidad de
interpretación del sistema -- Nora deja de ser un agente aparte y su
alcance (operativo: tiempos, alucinación, volumen/mezcla de Gio, HU
bloqueadas por Vera) queda absorbido dentro de un alcance mucho más amplio:
calidad + pruebas + defectos + Vera + Gio + IA vs. tradicional (análisis retrospectivo) +
adopción + histórico + tendencias. A diferencia de Nora (una sola pasada
por período, sin memoria), esto es un chat real con preguntas de
seguimiento.

Esta clase es una capa delgada a propósito, mismo motivo que
`InterpretarDashboard`: no tiene lógica propia más allá de delegar a
`LLMProvider.chat_nexus_insights()` (ver `ports/llm_provider.py`) y envolver
la lista cruda de pasos en un dataclass, para que el frontend no dependa de
la forma exacta del dict que devuelve el provider.
"""

from __future__ import annotations

from dataclasses import dataclass

from ports.llm_provider import LLMProvider


@dataclass
class PasoRespuestaNexus:
    """
    Un paso del pipeline de mensajes secuenciales con el que Nexus Insights
    responde (UX pedida explícitamente por el usuario, ver docstring de
    `LLMProvider.chat_nexus_insights()`). `tipo` es "info", "hallazgo" o
    "resumen" -- el frontend usa esto para elegir el estilo de la tarjeta.
    """
    tipo: str
    texto: str


class ChatNexusInsights:
    def __init__(self, llm_provider: LLMProvider):
        self._llm_provider = llm_provider

    def ejecutar(
        self,
        contexto: dict,
        historial: list[dict],
        pregunta: str,
    ) -> list[PasoRespuestaNexus]:
        pasos_crudos = self._llm_provider.chat_nexus_insights(contexto, historial, pregunta)
        return [PasoRespuestaNexus(tipo=p["tipo"], texto=p["texto"]) for p in pasos_crudos]
