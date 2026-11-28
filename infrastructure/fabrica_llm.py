"""
Fábrica del proveedor de LLM activo.

El proveedor se resuelve por variable de entorno (`LLM_PROVIDER` en `.env`),
leída una sola vez al iniciar el proceso: el agente NUNCA decide en tiempo de
ejecución qué modelo usar. Eso mantiene reproducible cada corrida, que es
condición para que los resultados medidos signifiquen algo.

Valor soportado:

- ``ollama`` (default): inferencia local sobre Ollama con ``llama3.1:8b``.

Que hoy haya una sola implementación no vuelve superflua a esta fábrica. El
resto del sistema depende del puerto ``LLMProvider``, nunca de un adaptador
concreto, así que incorporar otro motor es escribir un adaptador nuevo y
sumarlo acá: ni los casos de uso ni las vistas se enteran. Ese es justamente
el aislamiento que justifica la arquitectura hexagonal.

Los embeddings del RAG corren siempre por Ollama/``nomic-embed-text`` y eso no
es configurable: mezclar modelos de embedding dentro de un mismo índice
vectorial invalida las distancias, así que es una decisión de integridad de
datos y no de rendimiento.
"""

from __future__ import annotations

import os

from adapters.llm.ollama_provider import OllamaProvider
from infrastructure.config import cargar_configuracion_ollama, obtener_logger
from ports.llm_provider import LLMProvider

_log = obtener_logger(__name__)

PROVEEDOR_POR_DEFECTO = "ollama"


def crear_llm_provider() -> LLMProvider:
    """Devuelve el proveedor configurado, o falla con un mensaje accionable."""
    proveedor = os.getenv("LLM_PROVIDER", PROVEEDOR_POR_DEFECTO).strip().lower()
    config = cargar_configuracion_ollama()

    if proveedor == "ollama":
        _log.info("Proveedor de LLM activo: Ollama (%s)", config.modelo)
        return OllamaProvider(modelo=config.modelo, host=config.host)

    raise ValueError(
        f"LLM_PROVIDER={proveedor!r} no reconocido. Valor válido: 'ollama'. "
        "Revisá el archivo .env."
    )
