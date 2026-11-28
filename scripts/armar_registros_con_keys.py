"""
Script auxiliar de análisis exploratorio retrospectivo. No forma parte del flujo operativo de Vera y Gio.

Registro Pre-Test / Post-Test con los 60 HU REALES. Sin filas simuladas.

Qué cambia respecto de la versión anterior
------------------------------------------
Aquella completaba la muestra con 13 filas inventadas (marcadas como SIM-xx)
porque solo había 47 HU medidas. Ya no hace falta: las 60 son reales, medidas
con el mismo pipeline. Este libro no contiene un solo número inventado.

Identificación
--------------
Esta variante va con las KEYS REALES de Jira (análisis retrospectivo,
2026-09-20). La versión anonimizada --HU1..HU60, H1..H43/TP1..TP43,
DF1..DF57-- sigue existiendo en `registros_pretest_60hu.xlsx` y es la que
conviene compartir fuera de la organización: estos son datos de producción. Las dos se
generan del mismo CSV y sus totales son idénticos; lo único que cambia es la
primera columna de cada hoja.

Las tres decisiones que toma este archivo, y por qué
----------------------------------------------------
1. **Cobertura sobre 60 HU.** Es el corpus medido completo.

2. **Ejecución sobre 43 HU (el corpus cerrado), NO sobre 63.** Las 20 HU de
   septiembre tienen datos de ejecución (323 runs, 269 ejecutados = 83,3%),
   pero cerraron entre el 10/08 y el 11/09: sus test runs todavía se están
   corriendo. Mezclarlas bajaría el índice de 98,9% a 93,0% por una razón que
   no es "el proceso ejecuta menos", sino "estas HU son más nuevas". El dato
   de septiembre va igual, en su propia fila, para que la decisión esté a la
   vista y se pueda revisar más adelante.

3. **Defectos sin cambios: 57.** Para las HU de septiembre no se recolectaron
   defectos, así que no hay nada que sumar. Inventar ceros sería peor.
"""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

import sys

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


ANON = "--anon" in sys.argv
SALIDA = RAIZ / ("registros_pretest_60hu.xlsx" if ANON
                 else "registros_pretest_60hu_con_keys.xlsx")

from adapters.tesis.csv_tesis_repository import CsvTesisRepository
from application.tesis.calcular_metricas_tesis import (
    CalcularMetricasTesis,
)


_RESUMEN = CalcularMetricasTesis(CsvTesisRepository(RAIZ)).ejecutar("completa")
_FILAS = {f.hu_key: f for f in CsvTesisRepository(RAIZ).obtener_corpus().filas}
UMBRAL_PRODUCCION = 62

TINTA, AZUL, AZUL_CL = "1F2937", "1F4E79", "DCE6F1"
GRIS, BORDE, VERDE, ROJO = "F2F4F7", "BFC7D2", "1E7A4C", "B02418"
AMBAR, AMBAR_F = "FFF3D6", "9A6510"
F = "Arial"

h1 = Font(name=F, size=14, bold=True, color=AZUL)
h2 = Font(name=F, size=10, italic=True, color="5A6572")
cab = Font(name=F, size=9, bold=True, color="FFFFFF")
txt = Font(name=F, size=10, color=TINTA)
mono = Font(name=F, size=9, color=TINTA)
tot = Font(name=F, size=10, bold=True, color=TINTA)
sub = Font(name=F, size=9, bold=True, color="5A6572")
peq = Font(name=F, size=9, color="5A6572")
red_f = Font(name=F, size=9, italic=True, color=AMBAR_F)

fill_cab = PatternFill("solid", fgColor=AZUL)
fill_tot = PatternFill("solid", fgColor=AZUL_CL)
fill_alt = PatternFill("solid", fgColor=GRIS)
fill_red = PatternFill("solid", fgColor=AMBAR)

lado = Side(style="thin", color=BORDE)
caja = Border(left=lado, right=lado, top=lado, bottom=lado)
arriba = Border(top=Side(style="medium", color=AZUL))
CENTRO = Alignment(horizontal="center", vertical="center")
IZQ = Alignment(horizontal="left", vertical="center")
WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)
PCT, PTS, ENT = "0.0%", "+0.0;-0.0;0.0", "#,##0"


def leer(n: str) -> list[dict]:
    with (RAIZ / n).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def encabezado(ws, titulo, subtexto, ancho) -> int:
    ws["A1"] = titulo
    ws["A1"].font = h1
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ancho)
    ws["A2"] = subtexto
    ws["A2"].font = h2
    ws["A2"].alignment = WRAP
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ancho)
    ws.row_dimensions[1].height = 20
    ws.row_dimensions[2].height = 40
    return 4


def cabecera(ws, fila, cols, izq=2) -> None:
    for i, c in enumerate(cols, start=1):
        cel = ws.cell(row=fila, column=i, value=c)
        cel.font, cel.fill, cel.border = cab, fill_cab, caja
        cel.alignment = IZQ if i <= izq else CENTRO
    ws.row_dimensions[fila].height = 28
    ws.freeze_panes = ws.cell(row=fila + 1, column=1)


def anchos(ws, m: dict) -> None:
    for c, w in m.items():
        ws.column_dimensions[c].width = w


def pintar(ws, r, n, izq_hasta, alt=False, marcada=False) -> None:
    for c in range(1, n + 1):
        cel = ws.cell(row=r, column=c)
        cel.border = caja
        cel.alignment = IZQ if c <= izq_hasta else CENTRO
        if marcada:
            cel.fill = fill_red
        elif alt:
            cel.fill = fill_alt


cobertura = leer("cobertura_real_retro.csv")
corpus = leer("retro/retro_resultado_57hu.csv")
sept_agente = leer("resultado_septiembre.csv")
sept_runs = leer("historico_test_plan_resumen_septiembre.csv")
evit = leer("evitabilidad_defectos_retro.csv")

CLAVES_CORPUS = {f["hu_key"] for f in corpus}
SCORES = {}
for f in sept_agente:
    if (f.get("vera_aprobada") or "").strip().lower() in ("true", "1", "si", "sí"):
        try:
            SCORES[f["hu_key"]] = int(float(f.get("vera_score") or ""))
        except ValueError:
            pass
REDUCIDAS = {k for k, v in SCORES.items() if v < UMBRAL_PRODUCCION}


def etapa(hu: str) -> tuple[int, str]:
    if hu in CLAVES_CORPUS:
        return 0, "Corpus cerrado"
    if hu not in SCORES:
        return 1, "Ampliación recuperada"
    return (3, "Septiembre · umbral reducido") if hu in REDUCIDAS \
        else (2, "Septiembre · umbral 62")


cobertura.sort(key=lambda f: (etapa(f["hu_key"])[0], f["hu_key"]))
corpus.sort(key=lambda f: f["hu_key"])
evit.sort(key=lambda f: (f["criticidad"], f["defecto_key"]))

wb = Workbook()


ws = wb.active
ws.title = "1. Cobertura"
f0 = encabezado(
    ws,
    "Indicador 1 · Cobertura de criterios de aceptación",
    "Un criterio cuenta como cubierto si algún caso de prueba lo verifica. El juez es un LLM que "
    "compara TEXTO de casos contra TEXTO de criterios, ciego a cuál lado es humano y cuál del "
    "agente. Pre-Test = casos históricos del Test Plan · Post-Test = casos generados por el agente "
    "y aprobados en revisión humana. Las 60 HU son reales: este libro no tiene filas simuladas. "
    "Las filas en ámbar entraron con el umbral de Vera reducido a 35.",
    9,
)
cabecera(ws, f0, ["HU", "Etapa", "Umbral Vera", "Criterios", "Cubiertos sin IA",
                  "% sin IA (Pre)", "Cubiertos con IA", "% con IA (Post)", "Δ (puntos)"], izq=3)

fila = f0 + 1
corte_produccion = 0
for i, f in enumerate(cobertura):
    r = fila + i
    hu = f["hu_key"]
    _, nombre_etapa = etapa(hu)
    reducida = hu in REDUCIDAS
    if not reducida:
        corte_produccion = i + 1
    ws.cell(row=r, column=1, value=f"HU{i + 1}" if ANON else hu).font = mono
    ws.cell(row=r, column=2, value=nombre_etapa).font = red_f if reducida else peq
    ws.cell(row=r, column=3,
            value=("—" if hu not in SCORES else str(SCORES[hu]))).font = red_f if reducida else peq
    ws.cell(row=r, column=4, value=int(f["criterios_total"])).font = txt
    ws.cell(row=r, column=5, value=int(f["cubiertos_sin_ia"])).font = txt
    ws.cell(row=r, column=6, value=f"=IFERROR(E{r}/D{r},0)").number_format = PCT
    ws.cell(row=r, column=7, value=int(f["cubiertos_con_ia"])).font = txt
    ws.cell(row=r, column=8, value=f"=IFERROR(G{r}/D{r},0)").number_format = PCT
    ws.cell(row=r, column=9, value=f"=(H{r}-F{r})*100").number_format = PTS
    for c in (6, 8, 9):
        ws.cell(row=r, column=c).font = txt
    pintar(ws, r, 9, 3, alt=i % 2, marcada=reducida)

ult_cob = fila + len(cobertura) - 1
fila_prod = fila + corte_produccion - 1

rt = ult_cob + 1
for c in range(1, 10):
    cel = ws.cell(row=rt, column=c)
    cel.fill, cel.border = fill_tot, caja
    cel.alignment = IZQ if c <= 3 else CENTRO
ws.cell(row=rt, column=1, value="TOTAL").font = tot
ws.cell(row=rt, column=2, value=f"{len(cobertura)} HU reales").font = tot
for col, letra in ((4, "D"), (5, "E"), (7, "G")):
    ws.cell(row=rt, column=col, value=f"=SUM({letra}{fila}:{letra}{ult_cob})").font = tot
ws.cell(row=rt, column=6, value=f"=E{rt}/D{rt}").number_format = PCT
ws.cell(row=rt, column=8, value=f"=G{rt}/D{rt}").number_format = PCT
ws.cell(row=rt, column=9, value=f"=(H{rt}-F{rt})*100").number_format = PTS
ws.cell(row=rt, column=6).font = tot
ws.cell(row=rt, column=8).font = tot
ws.cell(row=rt, column=9).font = Font(name=F, size=10, bold=True, color=VERDE)


rs = rt + 1
for c in range(1, 10):
    cel = ws.cell(row=rs, column=c)
    cel.fill, cel.border = fill_red, caja
    cel.alignment = IZQ if c <= 3 else CENTRO
ws.cell(row=rs, column=1, value="SIN reducidas").font = Font(name=F, size=10, bold=True, color=AMBAR_F)
ws.cell(row=rs, column=2, value=f"{corte_produccion} HU · umbral {UMBRAL_PRODUCCION}").font = red_f
for col, letra in ((4, "D"), (5, "E"), (7, "G")):
    ws.cell(row=rs, column=col,
            value=f"=SUM({letra}{fila}:{letra}{fila_prod})").font = Font(
        name=F, size=10, bold=True, color=AMBAR_F)
ws.cell(row=rs, column=6, value=f"=E{rs}/D{rs}").number_format = PCT
ws.cell(row=rs, column=8, value=f"=G{rs}/D{rs}").number_format = PCT
ws.cell(row=rs, column=9, value=f"=(H{rs}-F{rs})*100").number_format = PTS
for c in (6, 8, 9):
    ws.cell(row=rs, column=c).font = Font(name=F, size=10, bold=True, color=AMBAR_F)

nota = rs + 2
ws.cell(row=nota, column=1,
        value=f"Las HU van ordenadas por etapa de incorporación, así que las primeras "
              f"{corte_produccion} son el corpus que pasa el umbral de producción y las últimas "
              f"{len(REDUCIDAS)} las que entraron con umbral 35. Comparar las dos filas de total "
              "ES el análisis de sensibilidad: si el Δ es parecido, el resultado no depende de "
              "esa decisión. El total es ponderado por criterios, no es el promedio de la columna "
              "de %. Fuente: cobertura_real_retro.csv · juez LLM.").font = peq
ws.merge_cells(start_row=nota, start_column=1, end_row=nota, end_column=9)
ws.cell(row=nota, column=1).alignment = WRAP
ws.row_dimensions[nota].height = 46
anchos(ws, {"A": 9, "B": 27, "C": 12, "D": 10, "E": 15, "F": 14, "G": 15, "H": 15, "I": 11})


ws = wb.create_sheet("2. Ejecución")
_ind2 = _RESUMEN.indice_ejecutabilidad_estructural
f0 = encabezado(
    ws,
    f"Indicador 2 · {_ind2.nombre}",
    "Qué proporción de los casos de prueba está escrita de forma que un QA que "
    "no los escribió pueda ejecutarlos sin volver a diseñarlos: el guion existe "
    "y declara acción (When) y resultado verificable (Then). Verificación "
    "sintáctica determinista, sin LLM, con el MISMO criterio a los dos lados. "
    "Solo casos funcionales: las verificaciones normativas de gobierno quedan "
    "fuera porque el agente no genera ninguna. Mide el DISEÑO del caso, no su "
    "corrida en ambiente de test.",
    8,
)
cabecera(ws, f0, ["HU", "Etapa", "Casos sin IA", "Ejecutables sin IA",
                  "% sin IA (Pre)", "Casos con IA", "Ejecutables con IA",
                  "% con IA (Post)"], izq=2)

fila = f0 + 1
for i, f in enumerate(cobertura):
    r = fila + i
    hu = f["hu_key"]
    d = _FILAS[hu]
    _, nombre_etapa = etapa(hu)
    ws.cell(row=r, column=1, value=f"HU{i + 1}" if ANON else hu).font = mono
    ws.cell(row=r, column=2, value=nombre_etapa).font = peq
    ws.cell(row=r, column=3, value=d.casos_pre).font = txt
    ws.cell(row=r, column=4, value=d.casos_pre_ejecutables).font = txt
    ws.cell(row=r, column=5, value=f'=IFERROR(D{r}/C{r},"")').number_format = PCT
    ws.cell(row=r, column=5).font = txt
    ws.cell(row=r, column=6, value=d.casos_post).font = txt
    ws.cell(row=r, column=7, value=d.casos_post_ejecutables).font = txt
    ws.cell(row=r, column=8, value=f'=IFERROR(G{r}/F{r},"")').number_format = PCT
    ws.cell(row=r, column=8).font = txt
    pintar(ws, r, 8, 2, alt=i % 2)

ult_eje = fila + len(cobertura) - 1
rt = ult_eje + 1
for c in range(1, 9):
    cel = ws.cell(row=rt, column=c)
    cel.fill, cel.border = fill_tot, caja
    cel.alignment = IZQ if c <= 2 else CENTRO
ws.cell(row=rt, column=1, value="TOTAL").font = tot
ws.cell(row=rt, column=2, value=f"{len(cobertura)} HU reales").font = tot
for col, letra in ((3, "C"), (4, "D"), (6, "F"), (7, "G")):
    ws.cell(row=rt, column=col, value=f"=SUM({letra}{fila}:{letra}{ult_eje})").font = tot
ws.cell(row=rt, column=5, value=f"=D{rt}/C{rt}").number_format = PCT
ws.cell(row=rt, column=5).font = Font(name=F, size=10, bold=True, color=VERDE)
ws.cell(row=rt, column=8, value=f"=G{rt}/F{rt}").number_format = PCT
ws.cell(row=rt, column=8).font = Font(name=F, size=10, bold=True, color=VERDE)


_vo = _RESUMEN.viabilidad_operativa_control
rv = rt + 2
ws.cell(row=rv, column=1, value="Métrica secundaria · Viabilidad operativa de ejecución").font = sub
ws.merge_cells(start_row=rv, start_column=1, end_row=rv, end_column=8)
rv += 1
cabecera(ws, rv, ["", "Concepto", "Tests planificados", "Tests ejecutados",
                  "% ejecución", "", "", ""], izq=2)
for j, (concepto, plan, ejec, pct) in enumerate((
        ("Histórico humano · 60 HU",
         sum(x.tests_plan for x in _FILAS.values()),
         sum(x.tests_ejecutados for x in _FILAS.values()),
         _vo.valor_pre / 100),
)):
    r = rv + 1 + j
    ws.cell(row=r, column=2, value=concepto).font = txt
    ws.cell(row=r, column=3, value=plan).font = txt
    ws.cell(row=r, column=4, value=ejec).font = txt
    ws.cell(row=r, column=5, value=f'=IFERROR(D{r}/C{r},"")').number_format = PCT
    ws.cell(row=r, column=5).font = txt
    pintar(ws, r, 5, 2, alt=j % 2)
    ult_vo = r

nota = ult_vo + 2
ws.cell(row=nota, column=1,
        value=("Esta hoja cambió respecto de la primera versión del libro, y "
               "conviene saber por qué. Antes medía 'runs ejecutados sobre runs "
               "planificados' (98.9% sobre 43 HU) y no tenía lado Post-Test, "
               "porque la corrida exploratoria no publicó sus casos en Xray. Ese "
               "número responde si el equipo corre lo que planifica, que es una "
               "pregunta de capacidad, no la del indicador. El indicador mide "
               "si el caso está ESCRITO de forma ejecutable, se aplica igual a "
               "los dos lados y usa las mismas 60 HU que cobertura. Los runs "
               "reales siguen abajo, como métrica secundaria. Fuente: el mismo "
               "caso de uso que alimenta el dashboard "
               "(CalcularMetricasTesis), no una cuenta propia de este "
               "archivo.")).font = peq
ws.merge_cells(start_row=nota, start_column=1, end_row=nota, end_column=8)
ws.cell(row=nota, column=1).alignment = WRAP
ws.row_dimensions[nota].height = 66
anchos(ws, {"A": 15, "B": 27, "C": 13, "D": 17, "E": 14, "F": 13, "G": 17, "H": 15})


ws = wb.create_sheet("3. Defectos")
f0 = encabezado(
    ws,
    "Indicador 3 · Defectos reales y evitabilidad",
    "Pre-Test = los defectos que realmente ocurrieron en las 43 HU del corpus cerrado. Post-Test "
    "NO es un conteo de defectos del agente (no existen: nunca se ejecutó nada): es el conteo real "
    "MENOS los clasificados como Evitable. Los 'Parcialmente evitable' se siguen contando a "
    "propósito — es la categoría de la duda, y descontarla inflaría la mejora justo donde el "
    "método es más débil. Para las HU de septiembre no se recolectaron defectos.",
    9,
)
CRIT = [("Critico", 2, 14), ("Alto", 2, 3), ("Medio", 8, 18), ("Bajo", 0, 8),
        ("Sin clasificar", 0, 2)]
cabecera(ws, f0, ["Criticidad", "Abiertos", "Cerrados", "Total", "", "", "", "", ""], izq=1)
fila = f0 + 1
for i, (n, ab, ce) in enumerate(CRIT):
    r = fila + i
    ws.cell(row=r, column=1, value=n).font = txt
    ws.cell(row=r, column=2, value=ab).font = txt
    ws.cell(row=r, column=3, value=ce).font = txt
    ws.cell(row=r, column=4, value=f"=B{r}+C{r}").font = tot
    pintar(ws, r, 4, 1, alt=i % 2)
ult_c = fila + len(CRIT) - 1
rt = ult_c + 1
for c in range(1, 5):
    cel = ws.cell(row=rt, column=c)
    cel.fill, cel.border = fill_tot, caja
    cel.alignment = IZQ if c == 1 else CENTRO
ws.cell(row=rt, column=1, value="TOTAL DEFECTOS").font = tot
for col, letra in ((2, "B"), (3, "C"), (4, "D")):
    ws.cell(row=rt, column=col, value=f"=SUM({letra}{fila}:{letra}{ult_c})").font = tot

ws.cell(row=rt + 2, column=1, value="Detalle defecto por defecto").font = Font(
    name=F, size=11, bold=True, color=AZUL)
ws.merge_cells(start_row=rt + 2, start_column=1, end_row=rt + 2, end_column=6)
ws.cell(row=rt + 2, column=1).border = arriba

fcab = rt + 3
cabecera(ws, fcab, ["Defecto", "Criticidad", "Estado", "Veredicto final",
                    "¿Mitigado?", ""], izq=1)
ws.freeze_panes = None
fila = fcab + 1
for i, f in enumerate(evit):
    r = fila + i
    final = (f.get("validacion_humana") or "").strip() or f.get("veredicto", "")


    _k = (f.get("defecto_key") or "").strip() or \
         f'ID Jira {(f.get("defecto_id") or "s/d").strip()}'
    ws.cell(row=r, column=1, value=f"DF{i + 1}" if ANON else _k).font = mono
    ws.cell(row=r, column=2, value=f["criticidad"]).font = txt
    ws.cell(row=r, column=3, value=f["abierto_cerrado"]).font = txt
    ws.cell(row=r, column=4, value=final).font = txt


    ws.cell(row=r, column=5, value=f'=IF(D{r}="Evitable",1,0)').font = txt
    pintar(ws, r, 5, 1, alt=i % 2)
ult_d = fila + len(evit) - 1
rt2 = ult_d + 1
for c in range(1, 6):
    cel = ws.cell(row=rt2, column=c)
    cel.fill, cel.border = fill_tot, caja
    cel.alignment = IZQ if c == 1 else CENTRO
ws.cell(row=rt2, column=1, value="TOTAL").font = tot
ws.cell(row=rt2, column=2, value=f"=COUNT(E{fila}:E{ult_d})").font = tot
ws.cell(row=rt2, column=4, value=f'=COUNTIF(D{fila}:D{ult_d},"Evitable")').font = Font(
    name=F, size=10, bold=True, color=ROJO)
ws.cell(row=rt2, column=5, value=f"=SUM(E{fila}:E{ult_d})").font = Font(
    name=F, size=10, bold=True, color=VERDE)

nota = rt2 + 2
ws.cell(row=nota, column=1,
        value="Veredicto final = la validación humana cuando existe; si no, la del LLM. "
              "Fuente: evitabilidad_defectos_retro.csv, columna "
              "validacion_humana revisada por el tesista. Los 2 SIN_CLASIFICAR no tienen "
              "severidad en Jira y se cuentan igual en el total.").font = peq
ws.merge_cells(start_row=nota, start_column=1, end_row=nota, end_column=6)
ws.cell(row=nota, column=1).alignment = WRAP
ws.row_dimensions[nota].height = 32
anchos(ws, {"A": 12, "B": 15, "C": 12, "D": 22, "E": 15, "F": 4})


ws = wb.create_sheet("Resumen", 0)
ws["A1"] = "Registros Pre-Test / Post-Test · Agente QA"
ws["A1"].font = Font(name=F, size=16, bold=True, color=AZUL)
ws.merge_cells("A1:G1")
ws["A2"] = ("Los tres indicadores del estudio con el registro que los sostiene. "
            "60 HU reales, medidas con el mismo pipeline: este libro no contiene "
            "ninguna fila simulada. Cada número es una fórmula que apunta al detalle.")
ws["A2"].font = h2
ws["A2"].alignment = WRAP
ws.merge_cells("A2:G2")
ws.row_dimensions[2].height = 30

cabecera(ws, 4, ["#", "Indicador", "Muestra", "Pre-Test (sin IA)",
                 "Post-Test (con IA)", "Diferencia", ""], izq=2)
filas_res = [
    ("1", "Cobertura de criterios de aceptación", f"{len(cobertura)} HU",
     f"='1. Cobertura'!F{ult_cob + 1}", f"='1. Cobertura'!H{ult_cob + 1}",
     f"='1. Cobertura'!I{ult_cob + 1}", PCT, PTS),
    ("2", _RESUMEN.indice_ejecutabilidad_estructural.nombre, f"{len(cobertura)} HU",
     f"='2. Ejecución'!E{ult_eje + 1}", f"='2. Ejecución'!H{ult_eje + 1}",
     f"=('2. Ejecución'!H{ult_eje + 1}-'2. Ejecución'!E{ult_eje + 1})*100", PCT, PTS),


    ("3", "Defectos: llegados a producción → mitigados por NEXUS",
     f"{_RESUMEN.estado_defectos_global.n_muestra} HU",
     f"='3. Defectos'!B{rt2}", f"='3. Defectos'!E{rt2}",
     f"='3. Defectos'!E{rt2}/'3. Defectos'!B{rt2}", ENT, "0.0%"),
]
for i, (num, nombre, n, pre, post, dif, fmt, fmtd) in enumerate(filas_res):
    r = 5 + i
    ws.cell(row=r, column=1, value=num).font = Font(name=F, size=11, bold=True, color=AZUL)
    ws.cell(row=r, column=2, value=nombre).font = Font(name=F, size=11, bold=True, color=TINTA)
    ws.cell(row=r, column=3, value=n).font = txt
    ws.cell(row=r, column=4, value=pre).font = Font(name=F, size=12, bold=True, color=TINTA)
    ws.cell(row=r, column=5, value=post).font = Font(
        name=F, size=12, bold=True, color=TINTA if post.startswith("=") else "8A6A2B")
    ws.cell(row=r, column=6, value=dif).font = Font(
        name=F, size=12, bold=True, color=VERDE if dif.startswith("=") else "5A6572")
    ws.cell(row=r, column=4).number_format = fmt
    if post.startswith("="):
        ws.cell(row=r, column=5).number_format = fmt
    ws.cell(row=r, column=6).number_format = fmtd
    ws.row_dimensions[r].height = 30
    pintar(ws, r, 7, 2, alt=i % 2)

r = 9
ws.cell(row=r, column=1, value="Análisis de sensibilidad: el umbral de Vera").font = Font(
    name=F, size=11, bold=True, color=AMBAR_F)
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
ws.cell(row=r, column=1).border = arriba
cabecera(ws, r + 1, ["", "Corpus de cobertura", "HU", "Sin IA", "Con IA", "Δ (puntos)", ""], izq=2)

rs_cob = ult_cob + 2
comp = [
    (f"Solo umbral de producción ({UMBRAL_PRODUCCION})", corte_produccion,
     f"='1. Cobertura'!F{rs_cob}", f"='1. Cobertura'!H{rs_cob}", f"='1. Cobertura'!I{rs_cob}"),
    ("Corpus completo (incluye umbral 35)", len(cobertura),
     f"='1. Cobertura'!F{ult_cob + 1}", f"='1. Cobertura'!H{ult_cob + 1}",
     f"='1. Cobertura'!I{ult_cob + 1}"),
]
for i, (nombre, n, pre, post, dif) in enumerate(comp):
    rr = r + 2 + i
    ws.cell(row=rr, column=2, value=nombre).font = txt
    ws.cell(row=rr, column=3, value=n).font = txt
    ws.cell(row=rr, column=4, value=pre).number_format = PCT
    ws.cell(row=rr, column=5, value=post).number_format = PCT
    ws.cell(row=rr, column=6, value=dif).number_format = PTS
    for c in (4, 5, 6):
        ws.cell(row=rr, column=c).font = tot
    pintar(ws, r + 2 + i, 7, 2, marcada=(i == 1))
rr = r + 4
ws.cell(row=rr, column=2,
        value=f"10 de las {len(cobertura)} HU entraron con el umbral de Vera reducido a 35 en vez "
              f"de {UMBRAL_PRODUCCION}. Las dos filas de arriba son el mismo cálculo con y sin "
              "ellas: si el Δ es parecido, el resultado no depende de esa decisión.").font = peq
ws.merge_cells(start_row=rr, start_column=2, end_row=rr, end_column=7)
ws.cell(row=rr, column=2).alignment = WRAP
ws.row_dimensions[rr].height = 30

r = 15
ws.cell(row=r, column=1, value="Lo que este archivo NO dice").font = Font(
    name=F, size=11, bold=True, color=ROJO)
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
ws.cell(row=r, column=1).border = arriba
limites = [
    f"Las muestras son distintas y está declarado: cobertura sobre {len(cobertura)} HU, "
    f"ejecución y defectos sobre las {len(corpus)} del corpus cerrado. No se mezclan.",
    "El indicador 2 mide si el caso está ESCRITO de forma ejecutable, no si se corrió. "
    "Ninguna ejecución real entra en esa cuenta: los runs van aparte, como métrica "
    "secundaria de capacidad, al pie de la hoja 2.",
    "El juez de cobertura es un LLM. No sabe cuál lado es humano y cuál del agente, pero sigue "
    "siendo una sola opinión: falta una segunda lectura independiente.",
    "La evitabilidad la validó el propio tesista: es validación humana, no validación ciega de "
    "un tercero, y eso limita cuánto se puede afirmar.",
]
for i, t in enumerate(limites):
    rr = r + 1 + i
    ws.cell(row=rr, column=1, value="•").font = Font(name=F, size=10, color=ROJO)
    ws.cell(row=rr, column=1).alignment = CENTRO
    ws.cell(row=rr, column=2, value=t).font = peq
    ws.merge_cells(start_row=rr, start_column=2, end_row=rr, end_column=7)
    ws.cell(row=rr, column=2).alignment = WRAP
    ws.row_dimensions[rr].height = 28

ws.cell(row=21, column=1,
        value="Generado el 2026-09-14 desde los CSV del proyecto. Claves anonimizadas "
              "(HU1..HU60, DF1..DF57) por tratarse de datos de producción de una institución financiera. "
              "Fórmulas del dashboard: infrastructure/reportes/pretest_posttest.py").font = Font(
    name=F, size=8, italic=True, color="8A929E")
ws.merge_cells("A21:G21")
anchos(ws, {"A": 5, "B": 40, "C": 13, "D": 18, "E": 19, "F": 15, "G": 4})
ws.sheet_view.showGridLines = False

for hoja in wb:
    hoja.sheet_properties.tabColor = AZUL

SALIDA.parent.mkdir(parents=True, exist_ok=True)
wb.save(SALIDA)
print("escrito:", SALIDA, "(anonimizada)" if ANON else "(keys reales)")
print(f"cobertura {len(cobertura)} HU | umbral produccion {corte_produccion} | "
      f"reducidas {len(REDUCIDAS)}")
_i2 = _RESUMEN.indice_ejecutabilidad_estructural
print(f"ejecutabilidad {len(cobertura)} HU | {_i2.detalle_pre} -> {_i2.detalle_post} "
      f"| {_i2.valor_pre:.1f}% -> {_i2.valor_post:.1f}%")
print(f"defectos {len(evit)}")
