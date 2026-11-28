"""
Construye y valida la Hoja de datos 1 (tabla por ciclo del artículo).

    python scripts/construir_hoja_datos.py \
        --tabla-ancha resultados_documento_60ciclos.csv \
        --marcas marcas_sensibilidad.csv \
        --salida datos/hoja_datos_1.csv

Entradas:

- `--tabla-ancha`: exportación de las hojas "Datos pre" y "Datos post" del
  libro de resultados (la misma que lee la pantalla de Resultados). Contiene,
  por ciclo, las situaciones identificadas y cubiertas, los casos especificados
  y ejecutados y los defectos detectados y corregidos por severidad, tal como
  se consolidaron desde las exportaciones de Jira y Xray.
- `--marcas`: CSV con columnas `periodo,ciclo,marca`, una fila por marca. Las
  marcas válidas y su significado están en `application/tesis/hoja_datos.py`
  (MARCAS). Definen, sin ambigüedad, qué excluye cada análisis de sensibilidad.

Alternativa: `--hoja` valida una Hoja de datos 1 ya construida (formato largo)
sin reconstruirla.

Salidas: la hoja en CSV (formato largo, una fila por ciclo y periodo, códigos
CPn / PTn) y, si openpyxl está instalado, un .xlsx con la hoja, el diccionario
de columnas y el significado de las marcas, listo para el material
suplementario. El script termina con código 1 si la hoja no es consistente.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from application.tesis.hoja_datos import (
    ANALISIS,
    COLUMNAS,
    MARCAS,
    desde_tabla_ancha,
    escribir_hoja,
    leer_hoja,
    leer_marcas,
    marcas_sin_ciclo,
    validar,
)

DICCIONARIO = {
    "periodo": "pre = proceso manual; post = proceso con el agente. Son ciclos distintos.",
    "ciclo": "Código anónimo del ciclo de prueba (CPn en el pre-test, PTn en el post-test).",
    "situaciones_identificadas": "Situaciones de prueba reconocidas en los criterios de aceptación.",
    "situaciones_cubiertas": "Situaciones con al menos un caso de prueba que las cubre.",
    "casos_especificados": "Casos de prueba del plan de la historia.",
    "casos_ejecutados": "Casos con al menos una ejecución registrada en Xray.",
    "defectos_detectados": "Defectos vinculados al ciclo.",
    "defectos_corregidos": "Defectos con estado corregido al cierre del ciclo.",
    "det_*": "Defectos detectados por severidad (bajo, medio, alto, crítico).",
    "corr_*": "Defectos corregidos por severidad.",
    "marcas": "Motivos documentados para excluir el ciclo en un análisis de sensibilidad.",
    "excluido_A/B/C": "1 si el ciclo se excluye en ese análisis de sensibilidad.",
}


def _escribir_xlsx(ciclos, ruta: Path) -> bool:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        return False
    wb = Workbook()
    ws = wb.active
    ws.title = "Hoja de datos 1"
    ws.append(COLUMNAS)
    for celda in ws[1]:
        celda.font = Font(bold=True)
    for c in sorted(ciclos, key=lambda c: (c.periodo != "pre", int(c.ciclo[2:]))):
        fila = c.como_fila()
        ws.append([fila[k] for k in COLUMNAS])
    ws.freeze_panes = "C2"
    dic = wb.create_sheet("Diccionario")
    dic.append(["Columna", "Descripción"])
    for k, v in DICCIONARIO.items():
        dic.append([k, v])
    mar = wb.create_sheet("Marcas y análisis")
    mar.append(["Marca", "Significado"])
    for k, v in MARCAS.items():
        mar.append([k, v])
    mar.append([])
    mar.append(["Análisis", "Periodo afectado", "Excluye los ciclos con alguna de estas marcas"])
    for nombre, (periodo, motivos) in ANALISIS.items():
        mar.append([nombre, periodo, "; ".join(sorted(motivos))])
    for hoja in (ws, dic, mar):
        for col in hoja.columns:
            ancho = max(len(str(c.value or "")) for c in col)
            hoja.column_dimensions[col[0].column_letter].width = min(60, ancho + 2)
    wb.save(ruta)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    origen = ap.add_mutually_exclusive_group(required=True)
    origen.add_argument("--tabla-ancha", type=Path)
    origen.add_argument("--hoja", type=Path, help="Validar una Hoja de datos 1 existente.")
    ap.add_argument("--marcas", type=Path, help="marcas_sensibilidad.csv")
    ap.add_argument("--salida", type=Path, default=RAIZ / "datos" / "hoja_datos_1.csv")
    ap.add_argument("--ciclos-por-periodo", type=int, default=60)
    args = ap.parse_args(argv)

    errores: list[str] = []
    if args.hoja:
        ciclos = leer_hoja(args.hoja)
    else:
        if not args.marcas:
            ap.error("--tabla-ancha requiere --marcas.")
        marcas = leer_marcas(args.marcas)
        ciclos = desde_tabla_ancha(args.tabla_ancha, marcas)
        errores += marcas_sin_ciclo(marcas, ciclos)

    errores += validar(ciclos, args.ciclos_por_periodo)
    pre = [c for c in ciclos if c.periodo == "pre"]
    post = [c for c in ciclos if c.periodo == "post"]
    print(f"Ciclos: {len(pre)} pre-test, {len(post)} post-test")
    for nombre in ANALISIS:
        excl = [c.ciclo for c in ciclos if c.excluido_en(nombre)]
        print(f"  Análisis {nombre}: excluye {len(excl)} -> {', '.join(excl) or '-'}")
    for etiqueta, grupo in (("pre", pre), ("post", post)):
        print(f"  {etiqueta}: situaciones {sum(c.situaciones_cubiertas for c in grupo)}/"
              f"{sum(c.situaciones_identificadas for c in grupo)}, casos "
              f"{sum(c.casos_ejecutados for c in grupo)}/"
              f"{sum(c.casos_especificados for c in grupo)}, defectos "
              f"{sum(c.defectos_corregidos for c in grupo)}/"
              f"{sum(c.defectos_detectados for c in grupo)}")
    if errores:
        print("\nLa hoja NO es consistente:")
        for e in errores:
            print(f"  - {e}")
        return 1

    if not args.hoja:
        escribir_hoja(ciclos, args.salida)
        print(f"\nHoja de datos 1 (CSV): {args.salida}")
        xlsx = args.salida.with_suffix(".xlsx")
        if _escribir_xlsx(ciclos, xlsx):
            print(f"Hoja de datos 1 (Excel): {xlsx}")
    print("Validación: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
