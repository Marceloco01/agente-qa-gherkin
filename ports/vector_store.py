"""
Port (contrato) para búsqueda de embeddings (RAG).

Fase 1: este archivo NO se usa todavía. No hay RAG en Fase 1: el LLM genera
test cases solo con el contexto de la HU, sin buscar casos históricos
similares. Se incluye desde ya por consistencia con la estructura de carpetas
definitiva (spec, sección 3.2), pero ningún código de Fase 1 lo importa.

Se implementa recién en Fase 3, con `PostgresPgvectorAdapter`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class VectorStore(ABC):
    @abstractmethod
    def guardar_embedding(
        self,
        referencia_id: str,
        vector: list[float],
        metadata: dict,
    ) -> None:
        """Guarda el embedding de un caso histórico junto a su metadata."""
        raise NotImplementedError

    @abstractmethod
    def buscar_similares(self, vector: list[float], top_k: int) -> list[dict]:
        """Busca los `top_k` casos históricos más similares a un vector dado."""
        raise NotImplementedError
