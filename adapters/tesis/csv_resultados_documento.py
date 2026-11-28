"""
Adaptador: los 60 ciclos del documento, leídos de `resultados_documento_60ciclos.csv`.

El CSV vive en la raíz del proyecto y es una exportación congelada de las hojas
"Datos pre" y "Datos post" de `Tablas_Resultados_v3_1.xlsx`. Congelada a
propósito: el documento ya está escrito con esos números, así que esta pantalla
tiene que mostrar EXACTAMENTE eso y no un recálculo que pueda derivar. Si el
libro cambia, se vuelve a exportar el CSV -- ese es el único camino.

Sin pandas: son 60 filas y 31 columnas. `csv` de la librería estándar alcanza y
evita arrastrar una dependencia a la capa de adaptadores.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ports.resultados_documento import (
    ORDEN_SEVERIDAD,
    CicloMedido,
    ResultadosDocumentoRepository,
)

ARCHIVO = "resultados_documento_60ciclos.csv"


_SUFIJO = {"Bajo": "bajo", "Medio": "medio", "Alto": "alto", "Crítico": "critico"}


def _n(fila: dict[str, str], clave: str) -> int:
    valor = (fila.get(clave) or "").strip()
    return int(valor) if valor else 0


def _por_severidad(fila: dict[str, str], prefijo: str, lado: str) -> dict[str, int]:
    return {sev: _n(fila, f"{prefijo}_{_SUFIJO[sev]}_{lado}") for sev in ORDEN_SEVERIDAD}


class CsvResultadosDocumento(ResultadosDocumentoRepository):
    def __init__(self, raiz: Path):
        self._ruta = Path(raiz) / ARCHIVO

    def obtener_ciclos(self) -> tuple[CicloMedido, ...]:
        if not self._ruta.exists():


            raise FileNotFoundError(
                f"No está {self._ruta}. Es la exportación de las hojas 'Datos pre' "
                f"y 'Datos post' de Tablas_Resultados_v3_1.xlsx."
            )
        with self._ruta.open(encoding="utf-8-sig", newline="") as fh:
            filas = [f for f in csv.DictReader(fh) if (f.get("ciclo") or "").strip()]
        return tuple(
            CicloMedido(
                ciclo=_n(f, "ciclo"),
                id_pre=(f.get("id_pre") or "").strip(),
                id_post=(f.get("id_post") or "").strip(),
                situaciones_identificadas_pre=_n(f, "situaciones_identificadas_pre"),
                situaciones_cubiertas_pre=_n(f, "situaciones_cubiertas_pre"),
                situaciones_identificadas_post=_n(f, "situaciones_identificadas_post"),
                situaciones_cubiertas_post=_n(f, "situaciones_cubiertas_post"),
                casos_especificados_pre=_n(f, "casos_especificados_pre"),
                casos_ejecutados_pre=_n(f, "casos_ejecutados_pre"),
                casos_especificados_post=_n(f, "casos_especificados_post"),
                casos_ejecutados_post=_n(f, "casos_ejecutados_post"),
                defectos_detectados_pre=_n(f, "defectos_detectados_pre"),
                defectos_corregidos_pre=_n(f, "defectos_corregidos_pre"),
                defectos_detectados_post=_n(f, "defectos_detectados_post"),
                defectos_corregidos_post=_n(f, "defectos_corregidos_post"),
                detectados_por_severidad_pre=_por_severidad(f, "det", "pre"),
                corregidos_por_severidad_pre=_por_severidad(f, "corr", "pre"),
                detectados_por_severidad_post=_por_severidad(f, "det", "post"),
                corregidos_por_severidad_post=_por_severidad(f, "corr", "post"),
            )
            for f in filas
        )
