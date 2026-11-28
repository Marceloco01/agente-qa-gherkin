"""
Hoja de validación CIEGA de evitabilidad, para un segundo evaluador (2026-09-07).

Por qué hace falta
------------------
Hoy el análisis de evitabilidad de defectos descansa en un solo par de ojos:
el LLM propuso un veredicto y **una sola persona** (el autor de la tesis) lo
validó. El acuerdo entre esos dos es 89,5% con kappa 0,801, que es un número
lindo pero mide algo limitado: que el humano y el LLM coinciden. No dice nada
sobre si ese humano --que además es quien defiende que el agente funciona--
está siendo consistente o benévolo.

Un segundo evaluador de QA, **sin ver ningún veredicto previo**, es lo que
convierte eso en evidencia. Si un colega que no tiene nada invertido en el
resultado llega a los mismos veredictos, el número se sostiene solo.

Qué garantiza el ciego
----------------------
La hoja que se le entrega al colega **no contiene**: el veredicto del LLM, el
veredicto del autor, la justificación del LLM, ni la palabra "agente" o "IA"
en ninguna parte. Los casos de prueba se presentan como "casos candidatos", el
mismo encuadre neutral que usó el prompt del LLM. Si el evaluador supiera que
los casos los generó una IA, su juicio dejaría de ser independiente.

Los veredictos que se ocultan se guardan aparte, en
`validacion_ciega_clave.csv`, que **NO se le manda al colega**:
`scripts/comparar_validacion_ciega.py` lo usa después para medir el acuerdo.

Cómo se arma la muestra
-----------------------
Dos bloques, mezclados entre sí para que el evaluador no pueda distinguirlos:

  A. Una muestra al azar **estratificada por criticidad**, con semilla fija
     (reproducible: la misma semilla da siempre la misma muestra).
  B. **Todos los defectos donde el LLM y el autor no coincidieron.** Son los
     casos disputados y por eso son los que más valor tienen resueltos por un
     tercero.

Se reportan por separado al comparar: el acuerdo sobre la muestra al azar es
la medida limpia; el bloque disputado se lee aparte, porque incluirlo en el
promedio sesgaría el resultado hacia abajo a propósito.

**No usa LLM ni red.** Solo lee CSV locales: cero costo.

Entradas (raíz del proyecto):
    defectos_severidad_detalle_retro.csv       el defecto y su descripción
    defectos_caso_detector_retro.csv           el caso que lo detectó de verdad
    test_cases_*.csv                             los casos candidatos
    evitabilidad_defectos_retro__*.csv         SOLO para ocultar y para el bloque B

Salidas (raíz del proyecto):
    Validacion_Ciega_Evitabilidad.xlsx   <- esto se le manda al colega
    validacion_ciega_clave.csv           <- esto NO se le manda

Uso (desde la raíz del proyecto, con el venv activado):

    python scripts\\generar_hoja_validacion_ciega.py
    python scripts\\generar_hoja_validacion_ciega.py --muestra 20 --semilla 7
"""

from __future__ import annotations

import argparse
import csv
import glob
import random
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

_ARCHIVO_DETALLE = Path("defectos_severidad_detalle_retro.csv")
_ARCHIVO_DETECTOR = Path("defectos_caso_detector_retro.csv")
_PATRON_CASOS = "test_cases_*.csv"
_PATRON_EVITABILIDAD = "evitabilidad_defectos_retro__*.csv"
_SALIDA_XLSX = Path("Validacion_Ciega_Evitabilidad.xlsx")
_SALIDA_CLAVE = Path("validacion_ciega_clave.csv")
_SALIDA_XLSX_RE = Path("Reevaluacion_Ciega_Evitabilidad.xlsx")
_SALIDA_CLAVE_RE = Path("reevaluacion_ciega_clave.csv")

_VEREDICTOS = ["Evitable", "Parcialmente evitable", "No evitable"]

_FUENTE = "Arial"
_AZUL = "1F4E79"
_GRIS = "F2F2F2"
_AMARILLO = "FFF2CC"
_BORDE = Border(*[Side(style="thin", color="BFBFBF")] * 4)


def _leer(nombre: Path) -> list[dict]:
    if not nombre.exists():
        raise SystemExit(f"Falta {nombre.resolve()}.")
    with nombre.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _casos_por_hu() -> dict[str, list[dict]]:
    """Mismo criterio que el clasificador: une todos los test_cases_*.csv."""
    por_hu: dict[str, list[dict]] = defaultdict(list)
    vistos: set[tuple[str, str]] = set()
    archivos = sorted(glob.glob(_PATRON_CASOS))
    if not archivos:
        raise SystemExit(f"No se encontró ningún {_PATRON_CASOS} en {Path.cwd()}.")
    for ruta in archivos:
        with open(ruta, newline="", encoding="utf-8") as f:
            lector = csv.DictReader(f)
            if not lector.fieldnames or "hu_key" not in lector.fieldnames:
                continue
            for fila in lector:
                hu = (fila.get("hu_key") or "").strip()
                titulo = (fila.get("titulo") or "").strip()
                if not hu or (hu, titulo) in vistos:
                    continue
                vistos.add((hu, titulo))
                por_hu[hu].append(fila)
    return dict(por_hu)


def _veredictos_ocultos() -> dict[str, dict]:
    archivos = sorted(glob.glob(_PATRON_EVITABILIDAD))
    if not archivos:
        return {}

    mejor, mejor_n = None, -1
    for ruta in archivos:
        filas = list(csv.DictReader(open(ruta, newline="", encoding="utf-8")))
        n = sum(1 for f in filas if (f.get("validacion_humana") or "").strip())
        if n > mejor_n:
            mejor, mejor_n = filas, n
    return {f["defecto_id"]: f for f in (mejor or [])}


def _muestra(defectos: list[dict], ocultos: dict[str, dict],
             tamano: int, semilla: int) -> tuple[list[dict], set[str]]:
    """(defectos elegidos y mezclados, ids del bloque de disputados)."""
    rnd = random.Random(semilla)

    disputados = {
        d["defecto_id"] for d in defectos
        if (o := ocultos.get(d["defecto_id"]))
        and (o.get("validacion_humana") or "").strip()
        and o.get("veredicto") != o.get("validacion_humana")
    }

    por_crit: dict[str, list[dict]] = defaultdict(list)
    for d in defectos:
        if d["defecto_id"] not in disputados:
            por_crit[d.get("criticidad") or "SIN_CLASIFICAR"].append(d)

    total = sum(len(v) for v in por_crit.values())
    elegidos: list[dict] = []
    for crit, grupo in sorted(por_crit.items()):
        cuota = max(1, round(tamano * len(grupo) / total)) if total else 0
        elegidos.extend(rnd.sample(grupo, min(cuota, len(grupo))))

    elegidos.extend(d for d in defectos if d["defecto_id"] in disputados)
    rnd.shuffle(elegidos)
    return elegidos, disputados


def _encabezado(hoja, fila: int, textos: list[str], anchos: list[int]) -> None:
    for col, (texto, ancho) in enumerate(zip(textos, anchos), start=1):
        celda = hoja.cell(row=fila, column=col, value=texto)
        celda.font = Font(name=_FUENTE, bold=True, color="FFFFFF", size=10)
        celda.fill = PatternFill("solid", fgColor=_AZUL)
        celda.alignment = Alignment(vertical="center", wrap_text=True)
        celda.border = _BORDE
        hoja.column_dimensions[get_column_letter(col)].width = ancho
    hoja.row_dimensions[fila].height = 30


def _hoja_leeme(wb: Workbook, n_defectos: int, n_casos: int,
                reevaluacion: bool = False) -> None:
    hoja = wb.active
    hoja.title = "Léeme"
    hoja.column_dimensions["A"].width = 118
    titulo = ("Re-evaluación a ciegas de cobertura de casos de prueba"
              if reevaluacion else
              "Validación independiente de cobertura de casos de prueba")
    lineas = [
        (titulo, True, 14),
        ("", False, 11),
        ("QUÉ SE TE PIDE", True, 11),
        (f"Para cada uno de los {n_defectos} defectos de la hoja «Validación», decidir si alguno de "
         "los casos de prueba candidatos lo habría detectado.", False, 11),
        ("", False, 11),
        ("CÓMO RESPONDER — usá exactamente una de estas tres opciones:", True, 11),
        ("  • Evitable  →  hay UN caso candidato concreto que ejercita la misma funcionalidad por el "
         "mismo camino. Tenés que poder señalarlo por su título.", False, 11),
        ("  • Parcialmente evitable  →  algún caso toca la misma área, pero no valida exactamente la "
         "condición que falla.", False, 11),
        ("  • No evitable  →  ningún caso se acerca, o el defecto nace de algo que un caso de prueba "
         "funcional no puede ver (datos, configuración, infraestructura).", False, 11),
        ("", False, 11),
        ("Regla de desempate: si dudás entre dos, elegí la MENOS favorable. Es preferible subestimar "
         "la cobertura que inflarla.", False, 11),
        ("", False, 11),
        ("LA COLUMNA «POR QUÉ» NO ES OPCIONAL", True, 11),
        ("Una línea alcanza, pero tiene que estar. Un veredicto sin motivo escrito no se puede "
         "auditar después, y el objetivo de esta hoja es justamente que el resultado sea auditable.", False, 11),
        ("", False, 11),
        ("QUÉ COMPLETAR Y QUÉ NO", True, 11),
        ("Solo las celdas con fondo amarillo de la hoja «Validación»: VEREDICTO, CASO QUE LO "
         "DETECTARÍA y POR QUÉ. Nada más se toca.", False, 11),
        ("La fila 3 de esa hoja es un EJEMPLO ya completado para mostrar el formato esperado. "
         "Borrala o dejala, no se usa.", False, 11),
        ("", False, 11),
        (f"Los casos candidatos están en la hoja «Casos candidatos» ({n_casos} en total), "
         "agrupados por defecto. Buscá ahí el ID del defecto que estés evaluando.", False, 11),
        ("", False, 11),
        ("POR QUÉ NO VES NINGÚN VEREDICTO PREVIO", True, 11),
        (("Es a propósito, y acá está la única regla que importa de verdad: NO abras el archivo con "
          "tus respuestas anteriores hasta terminar. Esto mide si evaluás igual la segunda vez que "
          "la primera; si mirás lo de antes, no mide nada. Dejá pasar unos días desde la primera "
          "evaluación antes de llenar esta hoja: si la hacés el mismo día vas a estar recordando, "
          "no re-evaluando.")
         if reevaluacion else
         ("Es a propósito. Ya existe una evaluación de estos mismos defectos y se está midiendo si un "
          "segundo evaluador llega a lo mismo. Si vieras la evaluación anterior, tu juicio dejaría de "
          "ser independiente y la medición no serviría."), False, 11),
        ("Por eso tampoco se dice de dónde salieron los casos candidatos: evaluá los casos por lo "
         "que dicen, no por su origen.", False, 11),
    ]
    for i, (texto, negrita, tam) in enumerate(lineas, start=1):
        celda = hoja.cell(row=i, column=1, value=texto)
        celda.font = Font(name=_FUENTE, bold=negrita, size=tam,
                          color=_AZUL if negrita and tam > 11 else "000000")
        celda.alignment = Alignment(wrap_text=True, vertical="top")


def _candidatos_de(d: dict, casos_por_hu: dict[str, list[dict]]) -> list[dict]:
    """Los casos candidatos de un defecto = los de todas sus HU, sin repetir."""
    salida: list[dict] = []
    vistos: set[str] = set()
    for hu in (d.get("hu_keys") or "").split("|"):
        for caso in casos_por_hu.get(hu.strip(), []):
            titulo = (caso.get("titulo") or "").strip()
            if titulo in vistos:
                continue
            vistos.add(titulo)
            salida.append(caso)
    return salida


def _hoja_validacion(wb: Workbook, elegidos: list[dict],
                     casos_por_hu: dict[str, list[dict]]) -> None:
    hoja = wb.create_sheet("Validación")
    cols = ["#", "ID defecto", "Defecto (título)", "Descripción", "Criticidad",
            "Casos candidatos", "VEREDICTO", "CASO QUE LO DETECTARÍA", "POR QUÉ"]
    anchos = [5, 12, 46, 52, 13, 11, 22, 36, 52]
    hoja.cell(row=1, column=1,
              value="Completá solo las columnas amarillas. La fila 3 es un ejemplo del formato.")
    hoja.cell(row=1, column=1).font = Font(name=_FUENTE, italic=True, size=10, color="7F7F7F")
    _encabezado(hoja, 2, cols, anchos)
    hoja.freeze_panes = "A4"

    ejemplo = ["—", "EJEMPLO", "Al guardar sin monto, la app muestra la pantalla en blanco",
               "Ocurre solo si el campo monto queda vacío", "Alto", 4,
               "Parcialmente evitable",
               "Validar mensaje de error al guardar sin completar campos obligatorios",
               "El caso valida campos obligatorios en general, pero no el caso puntual del monto vacío."]
    for col, valor in enumerate(ejemplo, start=1):
        celda = hoja.cell(row=3, column=col, value=valor)
        celda.font = Font(name=_FUENTE, italic=True, size=9, color="7F7F7F")
        celda.alignment = Alignment(wrap_text=True, vertical="top")
        celda.border = _BORDE

    validacion = DataValidation(type="list", formula1='"' + ",".join(_VEREDICTOS) + '"',
                                allow_blank=True, showDropDown=False)
    hoja.add_data_validation(validacion)

    for i, d in enumerate(elegidos, start=1):
        fila = i + 3
        valores = [
            i,
            d.get("defecto_key") or d["defecto_id"],
            (d.get("defecto_titulo") or "(sin título en Jira)").strip(),
            (d.get("defecto_descripcion") or "(sin descripción en Jira)").strip()[:900],
            d.get("criticidad") or "sin clasificar",
            len(_candidatos_de(d, casos_por_hu)),
        ]
        for col, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=fila, column=col, value=valor)
            celda.font = Font(name=_FUENTE, size=10)
            celda.alignment = Alignment(wrap_text=True, vertical="top")
            celda.border = _BORDE
        for col in (7, 8, 9):
            celda = hoja.cell(row=fila, column=col)
            celda.fill = PatternFill("solid", fgColor=_AMARILLO)
            celda.font = Font(name=_FUENTE, size=10)
            celda.alignment = Alignment(wrap_text=True, vertical="top")
            celda.border = _BORDE
        validacion.add(hoja.cell(row=fila, column=7))
        hoja.row_dimensions[fila].height = 58


def _hoja_casos(wb: Workbook, elegidos: list[dict],
                casos_por_hu: dict[str, list[dict]]) -> None:
    hoja = wb.create_sheet("Casos candidatos")
    cols = ["ID defecto", "#", "Título del caso candidato", "Pasos (Gherkin)"]
    _encabezado(hoja, 1, cols, [12, 5, 56, 92])
    hoja.freeze_panes = "A2"

    fila = 2
    for d in elegidos:
        etiqueta = d.get("defecto_key") or d["defecto_id"]
        casos = _candidatos_de(d, casos_por_hu)
        if not casos:
            celda = hoja.cell(row=fila, column=1, value=etiqueta)
            celda.font = Font(name=_FUENTE, size=10, bold=True)
            hoja.cell(row=fila, column=3,
                      value="(no hay casos candidatos para este defecto)").font = Font(
                          name=_FUENTE, size=10, italic=True, color="7F7F7F")
            fila += 1
            continue
        for i, caso in enumerate(casos, start=1):
            valores = [etiqueta if i == 1 else "", i,
                       (caso.get("titulo") or "").strip(),
                       (caso.get("gherkin") or "(sin contenido)").strip()]
            for col, valor in enumerate(valores, start=1):
                celda = hoja.cell(row=fila, column=col, value=valor)
                celda.font = Font(name=_FUENTE, size=9,
                                  bold=(col == 1 and i == 1))
                celda.alignment = Alignment(wrap_text=True, vertical="top")
                celda.border = _BORDE
            fila += 1
        fila += 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hoja de validación ciega para un segundo evaluador. Sin LLM, sin red."
    )
    parser.add_argument("--muestra", type=int, default=15,
                        help="Tamaño de la muestra al azar (default 15). Los defectos "
                             "disputados se agregan aparte, siempre todos.")
    parser.add_argument("--semilla", type=int, default=20260907,
                        help="Semilla de la muestra: la misma semilla da la misma muestra.")
    parser.add_argument("--reevaluacion", action="store_true",
                        help="Hoja para que la re-evalúe a ciegas la MISMA persona que ya "
                             "validó, en vez de un segundo evaluador. Mide consistencia "
                             "intra-evaluador. Escribe archivos con otro nombre para no "
                             "pisar la versión del colega.")
    args = parser.parse_args()
    salida_xlsx = _SALIDA_XLSX_RE if args.reevaluacion else _SALIDA_XLSX
    salida_clave = _SALIDA_CLAVE_RE if args.reevaluacion else _SALIDA_CLAVE

    defectos = _leer(_ARCHIVO_DETALLE)
    detectores: dict[str, list[dict]] = defaultdict(list)
    for f in _leer(_ARCHIVO_DETECTOR):
        detectores[f["defecto_id"]].append(f)
    casos_por_hu = _casos_por_hu()
    ocultos = _veredictos_ocultos()

    elegidos, disputados = _muestra(defectos, ocultos, args.muestra, args.semilla)
    n_disp = sum(1 for d in elegidos if d["defecto_id"] in disputados)
    print(f"{len(defectos)} defectos en total. Muestra: {len(elegidos)} "
          f"({len(elegidos) - n_disp} al azar estratificados + {n_disp} disputados), "
          f"semilla {args.semilla}.")
    if not ocultos:
        print("  AVISO: no se encontró ningún archivo de evitabilidad. La hoja se genera "
              "igual, pero sin bloque de disputados y sin clave para comparar después.")

    n_casos = sum(len(_candidatos_de(d, casos_por_hu)) for d in elegidos)
    sin_candidatos = [d.get("defecto_key") or d["defecto_id"]
                      for d in elegidos if not _candidatos_de(d, casos_por_hu)]

    wb = Workbook()
    _hoja_leeme(wb, len(elegidos), n_casos, args.reevaluacion)
    _hoja_validacion(wb, elegidos, casos_por_hu)
    _hoja_casos(wb, elegidos, casos_por_hu)
    wb.save(salida_xlsx)

    with salida_clave.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["orden", "defecto_id", "defecto_key", "criticidad", "bloque",
                    "veredicto_llm", "validacion_autor"])
        for i, d in enumerate(elegidos, start=1):
            o = ocultos.get(d["defecto_id"], {})
            w.writerow([i, d["defecto_id"], d.get("defecto_key", ""),
                        d.get("criticidad", ""),
                        "disputado" if d["defecto_id"] in disputados else "azar",
                        o.get("veredicto", ""), o.get("validacion_humana", "")])

    if args.reevaluacion:
        print(f"\nPara re-evaluar : {salida_xlsx.resolve()}")
        print(f"NO la abras     : {salida_clave.resolve()}  <- tiene tus veredictos anteriores")
    else:
        print(f"\nPara el colega : {salida_xlsx.resolve()}")
        print(f"NO se le manda : {salida_clave.resolve()}  <- tiene los veredictos ocultos")
    print(f"{n_casos} casos candidatos incluidos en la hoja de detalle.")
    if sin_candidatos:
        print(f"  OJO: {len(sin_candidatos)} defecto(s) de la muestra no tienen ningún "
              f"caso candidato ({sin_candidatos}). Para esos, la única respuesta "
              "posible es 'No evitable' -- si son muchos, la muestra no sirve.")
    if args.reevaluacion:
        print(
            "\nDejá pasar unos días antes de llenarla, y no abras el CSV de veredictos "
            "anteriores hasta terminar. Si la llenás recordando en vez de re-evaluando, "
            "el número que salga no mide nada."
        )
        print("Cuando la termines: python scripts\\comparar_validacion_ciega.py --reevaluacion")
    else:
        print(
            "\nAntes de mandarla, abrila y confirmá dos cosas: que no aparezca ningún "
            "veredicto previo, y que en ninguna parte diga que los casos los generó una IA. "
            "Si el evaluador lo sabe, su juicio deja de ser independiente y la medición no sirve."
        )
        print("Cuando te la devuelva: python scripts\\comparar_validacion_ciega.py")


if __name__ == "__main__":
    main()
