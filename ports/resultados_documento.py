"""
Puerto: los resultados tal como quedaron publicados en el documento de tesis.

Este puerto NO es el de `tesis_repository.py` y no lo reemplaza. Son dos
fuentes distintas, y mezclarlas sería el error más caro de esta pantalla:

- `TesisRepository` sirve el corpus operativo del estudio: 61 HU, 274
  criterios, y un Estado de defectos definido como "defectos que las pruebas
  del agente habrían mitigado" (contrafáctico, validado uno por uno).
- Este puerto sirve lo que está IMPRESO en el documento: 60 ciclos de prueba,
  y un Estado de defectos definido como `corregidos / detectados`, medido en
  los DOS periodos, que es la fórmula del libro [29].

Los dos números son correctos cada uno en su marco y NO coinciden. La pantalla
que consume este puerto muestra el marco del documento, y lo dice en pantalla
para que nadie compare peras con manzanas.

Origen de los datos: `resultados_documento_60ciclos.csv`, exportado una sola
vez desde `Tablas_Resultados_v3_1.xlsx` (hojas "Datos pre" y "Datos post"), que
es el libro que acompaña al documento. Nada se transcribió a mano: los totales
del CSV reproducen las Tablas II, III, VII, VIII, XII y XIII al decimal.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


ORDEN_SEVERIDAD = ("Bajo", "Medio", "Alto", "Crítico")


@dataclass(frozen=True)
class CicloMedido:
    """
    Una fila de la exportación ancha de resultados: un ciclo del pre-test (CPN)
    y un ciclo del post-test (PTN) que comparten solo el número de fila.

    OJO: son ciclos DISTINTOS (historias distintas). La fila N no forma un par;
    el estudio compara muestras independientes (U de Mann-Whitney). El formato
    largo y sin esta ambigüedad es la Hoja de datos 1
    (`application/tesis/hoja_datos.py`).
    """

    ciclo: int
    id_pre: str
    id_post: str

    situaciones_identificadas_pre: int
    situaciones_cubiertas_pre: int
    situaciones_identificadas_post: int
    situaciones_cubiertas_post: int

    casos_especificados_pre: int
    casos_ejecutados_pre: int
    casos_especificados_post: int
    casos_ejecutados_post: int

    defectos_detectados_pre: int
    defectos_corregidos_pre: int
    defectos_detectados_post: int
    defectos_corregidos_post: int

    detectados_por_severidad_pre: dict[str, int]
    corregidos_por_severidad_pre: dict[str, int]
    detectados_por_severidad_post: dict[str, int]
    corregidos_por_severidad_post: dict[str, int]


class ResultadosDocumentoRepository(ABC):
    """Fuente de los 60 ciclos del documento. Una implementación por origen."""

    @abstractmethod
    def obtener_ciclos(self) -> tuple[CicloMedido, ...]:
        """Las 60 filas de la exportación (60 ciclos por periodo), en su orden."""
        raise NotImplementedError
