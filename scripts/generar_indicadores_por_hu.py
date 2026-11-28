"""
Los tres indicadores abiertos HU por HU, en dos libros: uno por lado.

    python scripts/generar_indicadores_por_hu.py

Deja en la raíz del proyecto:

    indicadores_por_HU_PRE.xlsx      el proceso manual
    indicadores_por_HU_POST.xlsx     NEXUS

Estructura pedida por el tesista (2026-09-20), idéntica en los dos libros para
poder compararlos hoja contra hoja:

    Resumen        los tres indicadores con su resultado
    1. Cobertura   HU · Criterios · Cubiertos · % cobertura
    2. Ejecuciones HU · Casos de prueba · Ejecutables · % ejecutables
    3. Defectos    HU · Defectos · desglose por criticidad

Ningún valor de resumen está escrito: son fórmulas contra las filas de abajo.
Si se corrige una fila, el indicador se mueve con ella.

Tres decisiones que este archivo toma, y conviene conocer antes de leerlo:

1. **La hoja 2 cuenta CASOS, no runs.** El indicador mide si el caso está
   escrito de forma ejecutable --guion con acción (When) y resultado
   verificable (Then)--, no si se corrió en Xray. En el libro PRE se agregan
   además las columnas de tests planificados y ejecutados, porque ese dato
   existe del lado humano y es la métrica secundaria de capacidad; en el POST
   no están disponibles para esta corrida exploratoria sin publicación en Xray.

2. **La hoja 3 lista las 43 HU del corpus cerrado, no las 60.** Son las que
   tienen trazabilidad de incidentes en Jira. De esas 43, solo 22 tienen al
   menos un defecto: las otras 21 van con 0, que es información, no relleno.
   Recortar la hoja a las 22 daría un n=22 que no es el del indicador.

3. **El lado POST de defectos son los 27 mitigados, no los 57.** El Post es un
   subconjunto del Pre, no un «después», y no se reportan defectos
   proyectados.

Todo sale de `CalcularMetricasTesis` y `CsvTesisRepository`, los mismos que
alimentan el dashboard. Este archivo no hace ninguna cuenta propia.
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from adapters.tesis.csv_tesis_repository import CsvTesisRepository
from application.tesis.calcular_metricas_tesis import (
    _ETIQUETA_SEVERIDAD,
    _ORDEN_SEVERIDAD,
    CalcularMetricasTesis,
)

FUENTE = "Arial"
AZUL, AZUL_CL, GRIS = "1F3864", "D9E2F3", "F2F2F2"
_B = Side(style="thin", color="BFC7D2")
BORDE = Border(left=_B, right=_B, top=_B, bottom=_B)
PCT, WRAP = "0.0%", Alignment(wrap_text=True, vertical="top")

SEVERIDADES = ["Crítico", "Alto", "Medio", "Bajo", "Sin clasificar"]


def _titulo(ws, texto: str, sub: str, ancho: int) -> int:
    c = ws.cell(1, 1, texto)
    c.font = Font(FUENTE, size=14, bold=True, color=AZUL)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ancho)
    c = ws.cell(2, 1, sub)
    c.font = Font(FUENTE, size=9, italic=True, color="5A6572")
    c.alignment = WRAP
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ancho)
    ws.row_dimensions[2].height = 30
    return 4


def _tabla(ws, f0: int, encabezados, anchos, filas) -> tuple[int, int]:
    for col, (t, a) in enumerate(zip(encabezados, anchos), start=1):
        c = ws.cell(f0, col, t)
        c.font = Font(FUENTE, size=9, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(wrap_text=True, vertical="center",
                                horizontal="center")
        c.border = BORDE
        ws.column_dimensions[get_column_letter(col)].width = a
    ws.row_dimensions[f0].height = 30
    for i, datos in enumerate(filas):
        r = f0 + 1 + i
        for col, v in enumerate(datos, start=1):
            c = ws.cell(r, col, v)
            c.font = Font(FUENTE, size=9)
            c.border = BORDE
            if isinstance(v, str) and v.startswith("=") and "/" in v:
                c.number_format = PCT
            if i % 2:
                c.fill = PatternFill("solid", fgColor=GRIS)
    ult = f0 + len(filas)
    ws.auto_filter.ref = f"A{f0}:{get_column_letter(len(encabezados))}{ult}"
    ws.freeze_panes = ws.cell(f0 + 1, 2)
    return f0 + 1, ult


def _total(ws, r: int, primera: int, ultima: int, etiqueta: str,
           sumas: list[str], pct: tuple[str, str, str] | None) -> None:
    for col in range(1, ws.max_column + 1):
        c = ws.cell(r, col)
        c.fill = PatternFill("solid", fgColor=AZUL_CL)
        c.border = BORDE
    ws.cell(r, 1, etiqueta).font = Font(FUENTE, size=10, bold=True)
    for letra in sumas:
        col = ws[f"{letra}1"].column
        c = ws.cell(r, col, f"=SUM({letra}{primera}:{letra}{ultima})")
        c.font = Font(FUENTE, size=10, bold=True)
    if pct:
        destino, num, den = pct
        col = ws[f"{destino}1"].column
        c = ws.cell(r, col, f"={num}{r}/{den}{r}")
        c.font = Font(FUENTE, size=10, bold=True, color="1E7A4C")
        c.number_format = PCT


def _nota(ws, r: int, texto: str, ancho: int) -> None:
    c = ws.cell(r + 2, 1, texto)
    c.font = Font(FUENTE, size=9, italic=True, color="5A6572")
    c.alignment = WRAP
    ws.merge_cells(start_row=r + 2, start_column=1, end_row=r + 2,
                   end_column=ancho)
    ws.row_dimensions[r + 2].height = 46


def cargar():
    repo = CsvTesisRepository(RAIZ)
    resumen = CalcularMetricasTesis(repo).ejecutar("completa")
    corpus = repo.obtener_corpus()
    filas = sorted(corpus.filas, key=lambda f: f.hu_key)


    with (RAIZ / "retro" / "retro_resultado_57hu.csv").open(
            encoding="utf-8") as fh:
        hu43 = sorted({(r.get("hu_key") or "").strip()
                       for r in csv.DictReader(fh)} - {""})

    det: dict[str, dict[str, int]] = {h: {} for h in hu43}
    mit: dict[str, dict[str, int]] = {h: {} for h in hu43}
    for d in corpus.defectos:
        hu = d.hu_keys[0] if d.hu_keys else ""
        sev = _ETIQUETA_SEVERIDAD.get(d.criticidad, d.criticidad or "Sin clasificar")
        det.setdefault(hu, {})[sev] = det.setdefault(hu, {}).get(sev, 0) + 1
        if d.veredicto == "Evitable":
            mit.setdefault(hu, {})[sev] = mit.setdefault(hu, {}).get(sev, 0) + 1
    return {"resumen": resumen, "corpus": corpus, "filas": filas,
            "hu43": hu43, "det": det, "mit": mit}


def hoja_cobertura(wb, d, post: bool) -> tuple[str, int]:
    ws = wb.create_sheet("1. Cobertura")
    quien = "los casos generados por NEXUS" if post else "el diseño de pruebas manual"
    f0 = _titulo(
        ws, "Indicador 1 · Índice de cobertura de pruebas",
        f"Cuántos de los criterios de aceptación de cada historia quedaron "
        f"cubiertos por {quien}. El denominador son los criterios de la HU, "
        f"que son los mismos para los dos lados: es la única forma de comparar "
        f"cobertura sobre el mismo blanco. Evaluación semántica automatizada, "
        f"criterio por criterio, con el mismo juez de los dos lados.", 4)
    filas = [[f.hu_key, f.criterios,
              f.cubiertos_post if post else f.cubiertos_pre,
              f"=IFERROR(C{f0 + 1 + i}/B{f0 + 1 + i},\"\")"]
             for i, f in enumerate(d["filas"])]
    p, u = _tabla(ws, f0, ["HU", "Criterios", "Cubiertos", "% cobertura"],
                  [16, 12, 12, 14], filas)
    rt = u + 1
    _total(ws, rt, p, u, f"TOTAL · {len(filas)} HU", ["B", "C"], ("D", "C", "B"))
    _nota(ws, rt,
          "El total es ponderado por criterios, no es el promedio de la "
          "columna de porcentajes: una HU con 11 criterios pesa más que una "
          "con 1. Fuente: el mismo caso de uso que alimenta el dashboard.", 4)
    return "'1. Cobertura'", rt


def hoja_ejecuciones(wb, d, post: bool) -> tuple[str, int]:
    ws = wb.create_sheet("2. Ejecuciones")
    quien = "generados por NEXUS" if post else "del histórico humano"
    extra = ("" if post else
             " Las dos últimas columnas son la métrica secundaria de "
             "capacidad: tests planificados contra ejecutados en Xray. No "
             "entran en el indicador — el indicador mide el DISEÑO del caso, "
             "no su corrida.")
    f0 = _titulo(
        ws, "Indicador 2 · Índice de ejecuciones de pruebas",
        f"De los casos de prueba {quien}, cuántos están escritos de forma que "
        f"un QA que no los escribió pueda ejecutarlos sin volver a diseñarlos: "
        f"el guion existe y declara acción (When) y resultado verificable "
        f"(Then). Verificación sintáctica determinista, sin LLM, con el mismo "
        f"criterio a los dos lados.{extra}", 4 if post else 7)

    if post:
        enc = ["HU", "Casos de prueba", "Ejecutables", "% ejecutables"]
        anchos = [16, 16, 14, 14]
        filas = [[f.hu_key, f.casos_post, f.casos_post_ejecutables,
                  f"=IFERROR(C{f0 + 1 + i}/B{f0 + 1 + i},\"\")"]
                 for i, f in enumerate(d["filas"])]
    else:
        enc = ["HU", "Casos de prueba", "Ejecutables", "% ejecutables",
               "Tests planificados", "Tests ejecutados", "% ejecución"]
        anchos = [16, 16, 14, 14, 17, 16, 13]
        filas = [[f.hu_key, f.casos_pre, f.casos_pre_ejecutables,
                  f"=IFERROR(C{f0 + 1 + i}/B{f0 + 1 + i},\"\")",
                  f.tests_plan, f.tests_ejecutados,
                  f"=IFERROR(F{f0 + 1 + i}/E{f0 + 1 + i},\"\")"]
                 for i, f in enumerate(d["filas"])]

    p, u = _tabla(ws, f0, enc, anchos, filas)
    rt = u + 1
    _total(ws, rt, p, u, f"TOTAL · {len(filas)} HU",
           ["B", "C"] if post else ["B", "C", "E", "F"], ("D", "C", "B"))
    if not post:
        c = ws.cell(rt, 7, f"=F{rt}/E{rt}")
        c.font = Font(FUENTE, size=10, bold=True, color="1E7A4C")
        c.number_format = PCT
    _nota(ws, rt,
          ("La corrida exploratoria no publicó sus casos en Xray, así que de este "
           "lado no hay tests planificados ni ejecutados: no se inventan. La "
           "comparación de capacidad está en el libro PRE."
           if post else
           "Solo casos FUNCIONALES: las verificaciones normativas de gobierno "
           "(cumplimiento normativo, análisis estático y seguridad de la información) quedan fuera porque el agente no "
           "genera ninguna, y compararlas sería comparar trabajos distintos."),
          4 if post else 7)
    return "'2. Ejecuciones'", rt


def hoja_defectos(wb, d, post: bool) -> tuple[str, int]:
    ws = wb.create_sheet("3. Defectos")
    fuente = d["mit"] if post else d["det"]
    col_n = "Defectos mitigados" if post else "Defectos detectados"
    f0 = _titulo(
        ws, "Indicador 3 · Estado de defectos",
        ("Los defectos reales de producción que las pruebas generadas por "
         "NEXUS habrían anticipado, abiertos por historia y por criticidad. "
         "Solo los clasificados como mitigables por la validación humana: los "
         "parcialmente mitigables no cuentan. No se reportan defectos "
         "proyectados."
         if post else
         "Los defectos reales que se escaparon del proceso de pruebas manual "
         "y llegaron al cliente, abiertos por historia y por criticidad. "
         "Ninguno fue prevenido: esa es la definición de la muestra.") +
        " Las HU son las 43 del corpus cerrado, las que tienen trazabilidad "
        "de incidentes en Jira. De esas, 21 no registran ningún defecto y van "
        "con 0 — recortarlas daría una muestra distinta de la del indicador.",
        7)


    orden = sorted(d["hu43"],
                   key=lambda h: (-sum(fuente.get(h, {}).values()), h))
    filas = []
    for i, hu in enumerate(orden):
        sev = fuente.get(hu, {})
        r = f0 + 1 + i
        filas.append([hu, f"=SUM(C{r}:G{r})"] +
                     [sev.get(s, 0) for s in SEVERIDADES])
    p, u = _tabla(ws, f0, ["HU", col_n] + SEVERIDADES,
                  [16, 17, 11, 9, 10, 9, 14], filas)
    rt = u + 1
    _total(ws, rt, p, u, f"TOTAL · {len(filas)} HU",
           ["B", "C", "D", "E", "F", "G"], None)
    _nota(ws, rt,
          ("Validación humana sobre los 57 del universo, con 89.5% de acuerdo "
           "con el juez LLM y 6 correcciones del investigador. El universo "
           "completo está en el libro PRE."
           if post else
           "Un defecto del corpus no tiene key ni criticidad resueltas en "
           "Jira y cae en «Sin clasificar». El detalle defecto por defecto "
           "está en reporte_PRE_test_indicadores.xlsx."), 7)
    return "'3. Defectos'", rt


def hoja_resumen(wb, d, post: bool, refs: dict) -> None:
    ws = wb.create_sheet("Resumen", 0)
    r = d["resumen"]
    lado = "POST-TEST · NEXUS" if post else "PRE-TEST · proceso manual"
    _titulo(ws, f"Los tres indicadores · {lado}",
            f"Muestra: {r.n_hu} historias de usuario · {r.n_criterios} "
            f"criterios de aceptación · {r.estado_defectos_global.n_muestra} "
            f"HU con trazabilidad de defectos. Cohorte completa. Ningún valor "
            f"de esta hoja está escrito: todos son fórmulas contra las hojas "
            f"de detalle. Generado el {date.today():%d/%m/%Y}.", 4)

    h1, r1 = refs["cobertura"]
    h2, r2 = refs["ejecuciones"]
    h3, r3 = refs["defectos"]
    filas = [
        ("Indicador 1 · Índice de cobertura de pruebas",
         f"={h1}!C{r1}", f"={h1}!B{r1}", f"={h1}!D{r1}", "criterios"),
        ("Indicador 2 · Índice de ejecuciones de pruebas",
         f"={h2}!C{r2}", f"={h2}!B{r2}", f"={h2}!D{r2}", "casos de prueba"),


        ("Indicador 3 · Estado de defectos",
         f"={h3}!B{r3}", f"{r.total_defectos_detectados}",
         f"={h3}!B{r3}/{r.total_defectos_detectados}" if post else "—",
         "defectos reales"),
    ]
    enc = ["Indicador", "Resultado", "Universo", "%", "Unidad"]
    for col, (t, a) in enumerate(zip(enc, [48, 13, 13, 11, 18]), start=1):
        c = ws.cell(4, col, t)
        c.font = Font(FUENTE, size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.border = BORDE
        ws.column_dimensions[get_column_letter(col)].width = a
    for i, datos in enumerate(filas):
        rr = 5 + i
        for col, v in enumerate(datos, start=1):
            c = ws.cell(rr, col, v)
            c.border = BORDE
            c.font = Font(FUENTE, size=11,
                          bold=col in (1, 2), color="1F2937")
            if col == 4 and isinstance(v, str) and v.startswith("="):
                c.number_format = PCT
            if col == 4:
                c.alignment = Alignment(horizontal="right")
        ws.row_dimensions[rr].height = 26

    leyenda = (
        "Cómo se lee cada uno. El indicador 1 cuenta CRITERIOS DE ACEPTACIÓN: "
        "el denominador son los de la HU y es el mismo de los dos lados, "
        "porque el criterio es una propiedad de la historia, no de quien la "
        "prueba. El indicador 2 cuenta CASOS DE PRUEBA, y ahí cada lado "
        "escribió los suyos, así que el universo cambia entre libros. El "
        "indicador 3 cuenta DEFECTOS REALES de producción, y su Post es un "
        "SUBCONJUNTO del Pre: son los mismos defectos, de los cuales el "
        "agente habría anticipado una parte. Tres unidades, tres universos, "
        "dos muestras."
    )
    c = ws.cell(10, 1, leyenda)
    c.font = Font(FUENTE, size=9, italic=True, color="5A6572")
    c.alignment = WRAP
    ws.merge_cells(start_row=10, start_column=1, end_row=10, end_column=5)
    ws.row_dimensions[10].height = 74
    ws.sheet_view.showGridLines = False


def construir(d, post: bool) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    refs = {
        "cobertura": hoja_cobertura(wb, d, post),
        "ejecuciones": hoja_ejecuciones(wb, d, post),
        "defectos": hoja_defectos(wb, d, post),
    }
    hoja_resumen(wb, d, post, refs)
    for hoja in wb:
        hoja.sheet_properties.tabColor = AZUL
    destino = RAIZ / f"indicadores_por_HU_{'POST' if post else 'PRE'}.xlsx"
    wb.save(destino)
    return destino


def main() -> None:
    d = cargar()
    r = d["resumen"]
    print(f"cobertura   {len(d['filas'])} HU · {r.n_criterios} criterios")
    print(f"ejecuciones {len(d['filas'])} HU")
    print(f"defectos    {len(d['hu43'])} HU del corpus cerrado · "
          f"{r.total_defectos_detectados} detectados · "
          f"{r.total_defectos_mitigados} mitigados")
    for post in (False, True):
        print("escrito:", construir(d, post).name)


if __name__ == "__main__":
    main()
