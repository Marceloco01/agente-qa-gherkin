"""
Inventario de TODAS las HU vistas en el estudio, con qué insumo tiene cada una.

    python scripts/generar_inventario_hu.py   ->  inventario_HU.xlsx

Para qué sirve: decidir con los datos a la vista qué HU puede entrar a cada
indicador. Cada indicador necesita insumos distintos, y una HU puede servir
para uno y no para otro:

    Indicador 1 · Cobertura     necesita CRITERIOS DE ACEPTACIÓN extraídos,
                                más casos humanos (Pre) y casos de Gio (Post).
                                Sin criterios no hay denominador: el indicador
                                no da un número bajo, no da NINGÚN número.
    Indicador 2 · Ejecuciones   necesita el texto Gherkin de los casos.
    Indicador 3 · Defectos      necesita trazabilidad de incidentes en Jira.

La columna «Estado» dice por qué una HU quedó fuera. La mayoría no es una
decisión de muestreo: es que Vera --el Quality Gate del propio agente-- las
bloqueó, casi siempre por depender de imágenes que el agente no puede leer.
Para esas nunca se generó un caso, así que no existe lado Post-Test.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from adapters.tesis.csv_tesis_repository import CsvTesisRepository

F, AZUL, AZUL_CL, GRIS = "Arial", "1F3864", "D9E2F3", "F2F2F2"
VERDE, AMBAR, ROJO = "E8F5E9", "FFF7E6", "FDECEA"
_B = Side(style="thin", color="BFC7D2")
BORDE = Border(left=_B, right=_B, top=_B, bottom=_B)
WRAP = Alignment(wrap_text=True, vertical="top")


def _leer(nombre: str) -> list[dict]:
    ruta = RAIZ / nombre
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def recolectar() -> list[dict]:
    repo = CsvTesisRepository(RAIZ)
    corpus = repo.obtener_corpus()
    filas = {f.hu_key: f for f in corpus.filas}

    agente = {r["hu_key"]: r for r in _leer("resultado_agente_82hu.csv") if r.get("hu_key")}
    sept = {r["hu_key"]: r for r in _leer("resultado_septiembre.csv") if r.get("hu_key")}
    criterios = {r["hu_key"]: r for r in _leer("criterios_aceptacion_retro.csv")
                 if r.get("hu_key")}
    gherkin: dict[str, int] = defaultdict(int)
    for archivo in ("historico_gherkin_texto_57hu.csv",
                    "historico_gherkin_texto_septiembre.csv"):
        for r in _leer(archivo):
            if r.get("hu_key"):
                gherkin[r["hu_key"]] += 1
    defectos: dict[str, int] = defaultdict(int)
    for d in corpus.defectos:
        if d.hu_keys:
            defectos[d.hu_keys[0]] += 1
    corpus43 = {(r.get("hu_key") or "").strip()
                for r in _leer("retro/retro_resultado_57hu.csv")}

    todas = sorted((set(filas) | set(agente) | set(sept) | set(criterios)
                    | set(gherkin)) - {""})
    salida = []
    for hu in todas:
        f = filas.get(hu)
        r = sept.get(hu) or agente.get(hu) or {}
        aprobada = (r.get("vera_aprobada") or "").strip().lower()
        n_crit = int((criterios.get(hu, {}).get("num_criterios_identificados") or 0)
                     if hu in criterios else 0)
        if f:
            estado, motivo = "En el estudio", ""
            n_crit = f.criterios
            casos_hum, casos_gio = f.casos_pre, f.casos_post
        else:
            casos_hum = gherkin.get(hu, 0)
            casos_gio = int(r.get("num_test_cases_generados") or 0)
            if aprobada == "false":
                estado = "Bloqueada por Vera"
                motivo = (r.get("vera_motivo_bloqueo")
                          or r.get("vera_detalle") or "")[:180]
            elif casos_hum:
                estado, motivo = "Fuera · solo histórico", (
                    "Tiene casos humanos pero no se le extrajeron criterios "
                    "de aceptación ni se midió su cobertura.")
            else:
                estado, motivo = "Fuera · sin datos", (
                    "No tiene criterios, ni casos humanos cargados, ni casos "
                    "del agente.")
        salida.append({
            "hu": hu, "estado": estado, "criterios": n_crit,
            "casos_hum": casos_hum, "casos_gio": casos_gio,
            "defectos": defectos.get(hu, 0),
            "traza": "Sí" if hu in corpus43 else "No",
            "tests_plan": f.tests_plan if f else 0,
            "tests_ejec": f.tests_ejecutados if f else 0,


            "ind1": "Sí" if n_crit > 0 and casos_hum > 0 and casos_gio > 0 else "No",
            "ind2": "Sí" if casos_hum > 0 or casos_gio > 0 else "No",
            "ind3": "Sí" if hu in corpus43 else "No",
            "motivo": motivo,
        })
    return salida


def construir(datos: list[dict]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario de HU"

    n_est = sum(1 for d in datos if d["estado"] == "En el estudio")
    c = ws.cell(1, 1, "Inventario de todas las HU vistas en el estudio")
    c.font = Font(F, size=14, bold=True, color=AZUL)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=12)
    c = ws.cell(2, 1,
                f"{len(datos)} historias en total: {n_est} en el estudio y "
                f"{len(datos) - n_est} fuera. Las tres últimas columnas dicen "
                f"si cada indicador SE PUEDE CALCULAR sobre esa HU, que no es "
                f"lo mismo que si conviene incluirla: el indicador 1 necesita "
                f"criterios de aceptación extraídos y casos de los dos lados; "
                f"sin criterios no hay denominador. La columna «Motivo» "
                f"explica por qué una HU quedó fuera — en la mayoría de los "
                f"casos porque Vera la bloqueó y nunca se le generó un caso.")
    c.font = Font(F, size=9, italic=True, color="5A6572")
    c.alignment = WRAP
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=12)
    ws.row_dimensions[2].height = 56

    enc = ["HU", "Estado", "Criterios", "Casos humanos", "Casos de Gio",
           "Defectos", "Traza de defectos", "Tests plan.", "Tests ejec.",
           "Ind.1 Cobertura", "Ind.2 Ejecuciones", "Ind.3 Defectos", "Motivo"]
    anchos = [15, 22, 10, 13, 12, 10, 12, 11, 11, 13, 14, 12, 70]
    for col, (t, a) in enumerate(zip(enc, anchos), start=1):
        cc = ws.cell(4, col, t)
        cc.font = Font(F, size=9, bold=True, color="FFFFFF")
        cc.fill = PatternFill("solid", fgColor=AZUL)
        cc.alignment = Alignment(wrap_text=True, vertical="center",
                                 horizontal="center")
        cc.border = BORDE
        ws.column_dimensions[get_column_letter(col)].width = a
    ws.row_dimensions[4].height = 32


    def orden(d):
        rango = {"En el estudio": 0, "Fuera · solo histórico": 1,
                 "Bloqueada por Vera": 2, "Fuera · sin datos": 3}
        return (rango.get(d["estado"], 9), -d["criterios"], -d["casos_hum"], d["hu"])

    for i, d in enumerate(sorted(datos, key=orden)):
        r = 5 + i
        fondo = {"En el estudio": VERDE, "Fuera · solo histórico": AMBAR}.get(
            d["estado"], ROJO if d["estado"] == "Fuera · sin datos" else GRIS)
        valores = [d["hu"], d["estado"], d["criterios"], d["casos_hum"],
                   d["casos_gio"], d["defectos"], d["traza"], d["tests_plan"],
                   d["tests_ejec"], d["ind1"], d["ind2"], d["ind3"], d["motivo"]]
        for col, v in enumerate(valores, start=1):
            cc = ws.cell(r, col, v)
            cc.font = Font(F, size=9)
            cc.border = BORDE
            cc.fill = PatternFill("solid", fgColor=fondo)
            if col == 13:
                cc.alignment = WRAP
    ult = 4 + len(datos)
    ws.auto_filter.ref = f"A4:M{ult}"
    ws.freeze_panes = ws.cell(5, 2)

    rt = ult + 1
    for col in range(1, 14):
        cc = ws.cell(rt, col)
        cc.fill = PatternFill("solid", fgColor=AZUL_CL)
        cc.border = BORDE
    ws.cell(rt, 1, "TOTAL").font = Font(F, size=10, bold=True)
    ws.cell(rt, 2, f"{len(datos)} HU").font = Font(F, size=10, bold=True)
    for col, letra in ((3, "C"), (4, "D"), (5, "E"), (6, "F"), (8, "H"), (9, "I")):
        cc = ws.cell(rt, col, f"=SUM({letra}5:{letra}{ult})")
        cc.font = Font(F, size=10, bold=True)
    for col, letra in ((10, "J"), (11, "K"), (12, "L")):
        cc = ws.cell(rt, col, f'=COUNTIF({letra}5:{letra}{ult},"Sí")')
        cc.font = Font(F, size=10, bold=True, color="1E7A4C")

    nota = rt + 2
    c = ws.cell(nota, 1,
                "Verde = en el estudio. Ámbar = tiene casos humanos pero no "
                "se le extrajeron criterios de aceptación. Gris = Vera la "
                "bloqueó, así que no existe ningún caso generado y no hay lado "
                "Post-Test posible. Rojo = no tiene ningún insumo cargado. "
                "El indicador 1 se mide en criterios de aceptación: ninguna HU "
                "fuera del estudio tiene criterios extraídos, así que sobre "
                "ellas el indicador no da un número bajo — no da ninguno.")
    c.font = Font(F, size=9, italic=True, color="5A6572")
    c.alignment = WRAP
    ws.merge_cells(start_row=nota, start_column=1, end_row=nota, end_column=13)
    ws.row_dimensions[nota].height = 58
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = AZUL

    destino = RAIZ / "inventario_HU.xlsx"
    wb.save(destino)
    return destino


def main() -> None:
    datos = recolectar()
    from collections import Counter
    print(Counter(d["estado"] for d in datos))
    print("calculable ind.1:", sum(1 for d in datos if d["ind1"] == "Sí"))
    print("calculable ind.2:", sum(1 for d in datos if d["ind2"] == "Sí"))
    print("calculable ind.3:", sum(1 for d in datos if d["ind3"] == "Sí"))
    print("escrito:", construir(datos).name)


if __name__ == "__main__":
    main()
