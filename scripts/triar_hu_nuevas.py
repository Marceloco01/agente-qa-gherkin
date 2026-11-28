"""
Triaje de HU nuevas para ampliar el corpus (NEXUS, 2026-09-14).

Por qué existe
--------------
Cerraron HU nuevas y se quiere saber cuáles sirven para ampliar el corpus de
la tesis. La tentación es mirar el Excel que exporta Jira ("Reporte HU
demanda") y decidir desde ahí. **No sirve**: ese export aplana la descripción
a una sola línea, sin saltos ni viñetas, y el detector de criterios trabaja
sobre la estructura de líneas. Resultado: da CERO criterios en todas las HU,
incluso en las que claramente los tienen.

Se comprobó (2026-09-14): sobre las 25 HU del export, el detector encuentra 0
criterios. Reinsertando saltos de línea a mano con una heurística cruda,
encuentra 21. La conclusión no es "estas HU no sirven", es "el export no es la
fuente". Este script va a Jira, que devuelve ADF y conserva la estructura.

Qué hace
--------
Para cada HU: la trae de Jira, cuenta criterios con el MISMO detector que usa
el motor de Seguimiento, aplica el chequeo de dependencia visual de Vera (el
regex, gratis) y busca si tiene Test Plan vinculado. Con eso clasifica cada HU
en uno de cuatro cajones y escribe un CSV.

**No usa LLM: cero costo.** Solo Jira. Vera sí usa LLM en el flujo real, pero
acá se aplica únicamente su primer chequeo, que es código puro.

Los cajones
-----------
  LISTA          criterios detectados y Test Plan: entra al corpus sin más.
  SIN_TEST_PLAN  tiene criterios pero no hay Test Plan: sirve para cobertura
                 del agente, no para comparar contra casos históricos.
  REVISAR_QA     no se detectaron criterios, pero el texto tiene marcas de que
                 los hay. Es el cajón que el tesista pidió mirar: con un QA al
                 lado se entiende la HU y se puede rescatar.
  DESCARTAR      texto demasiado corto o sin nada que parezca criterio.

Aparte, marca `depende_de_imagen`: Vera bloquearía esas HU en el flujo real.
No las descarta —el QA puede reescribir el criterio— pero hay que saberlo
antes de contarlas como corpus.

Uso:
    python scripts/triar_hu_nuevas.py --excel "Reporte_HU_demanda.xlsx"
    python scripts/triar_hu_nuevas.py --keys HU-312 HU-313
    python scripts/triar_hu_nuevas.py --excel r.xlsx --salida triaje.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import Counter
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from adapters.issue_tracker.jira_cloud_adapter import JiraCloudAdapter
from application.seguimiento.patrones_criterios_v2 import contar_criterios
from application.validar_hu import _PATRON_DEPENDENCIA_VISUAL
from infrastructure.config import cargar_configuracion_jira

_ESPERA = 0.4
_SALIDA = "triaje_hu_nuevas.csv"
_COLUMNAS = [
    "hu_key", "titulo", "cajon", "criterios", "patron", "depende_de_imagen",
    "marca_visual", "test_plan_key", "largo_descripcion", "criterios_texto", "error",
]


import re

_MARCAS = {
    "C-n": re.compile(r"\bC\d+\s*[:.\)]", re.I),
    "CA-n": re.compile(r"\bCA\s*\d+", re.I),
    "RN-n": re.compile(r"\bRN\s*\d+", re.I),
    "titulo-CA": re.compile(r"criterios?\s+de\s+aceptaci", re.I),
    "escenario": re.compile(r"\bescenario\s*\d*\s*:", re.I),
    "gherkin": re.compile(r"\b(dado que|cuando el|entonces se)\b", re.I),
    "numerado": re.compile(r"(?:^|\n)\s*\d+[\.\)]\s+\S"),
}
_LARGO_MINIMO_UTIL = 200


def _marcas(texto: str) -> list[str]:
    return [k for k, p in _MARCAS.items() if p.search(texto or "")]


def _clasificar(criterios: int, marcas: list[str], largo: int, test_plan) -> str:
    if criterios > 0:
        return "LISTA" if test_plan else "SIN_TEST_PLAN"
    if largo < _LARGO_MINIMO_UTIL or not marcas:
        return "DESCARTAR"
    return "REVISAR_QA"


def _keys_del_excel(ruta: Path) -> list[tuple[str, str]]:
    """Devuelve (key, titulo) leyendo el export de Jira. Solo para sacar las keys."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.exit("Falta openpyxl. Instalalo o pasá las keys con --keys.")
    wb = load_workbook(ruta, data_only=True, read_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        filas = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not filas:
        return []
    cab = [str(c or "").strip().lower() for c in filas[0]]
    try:
        i_key = next(i for i, c in enumerate(cab) if c == "key")
    except StopIteration:
        sys.exit("El Excel no tiene una columna 'Key'.")
    i_sum = next((i for i, c in enumerate(cab) if c in ("summary", "resumen")), None)
    out = []
    for f in filas[1:]:
        k = f[i_key] if i_key < len(f) else None
        if not k:
            continue
        titulo = str(f[i_sum] or "").strip() if i_sum is not None and i_sum < len(f) else ""
        out.append((str(k).strip(), titulo))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Triaje de HU nuevas para ampliar el corpus.")
    p.add_argument("--excel", help="Export de Jira ('Reporte HU demanda'): solo se le sacan las keys.")
    p.add_argument("--keys", nargs="*", help="Keys de HU, si no querés pasar un Excel.")
    p.add_argument("--salida", default=_SALIDA)
    p.add_argument("--sin-test-plan", action="store_true",
                   help="No consultar Test Plans (más rápido, una llamada menos por HU).")
    args = p.parse_args()

    pares: list[tuple[str, str]] = []
    if args.excel:
        pares += _keys_del_excel(Path(args.excel))
    if args.keys:
        pares += [(k, "") for k in args.keys]
    if not pares:
        sys.exit("Pasá --excel o --keys.")

    vistas: set[str] = set()
    unicas = [(k, t) for k, t in pares if not (k in vistas or vistas.add(k))]
    if len(unicas) != len(pares):
        print(f"Se quitaron {len(pares) - len(unicas)} keys repetidas.")

    ya_en_corpus = _keys_ya_en_corpus()
    nuevas = [(k, t) for k, t in unicas if k not in ya_en_corpus]
    if len(nuevas) != len(unicas):
        print(f"{len(unicas) - len(nuevas)} ya estaban en el corpus: se omiten.")
    if not nuevas:
        sys.exit("No queda ninguna HU nueva por triar.")

    print(f"Triando {len(nuevas)} HU contra Jira (sin LLM, costo cero)...\n")
    config = cargar_configuracion_jira()
    adapter = JiraCloudAdapter(config.base_url, config.email, config.api_token)
    filas: list[dict] = []
    try:
        for i, (key, titulo_excel) in enumerate(nuevas, start=1):
            fila = {c: "" for c in _COLUMNAS}
            fila["hu_key"] = key
            fila["titulo"] = titulo_excel
            try:
                hu = adapter.obtener_hu(key)
            except Exception as exc:
                fila.update(cajon="ERROR", error=str(exc)[:200])
                filas.append(fila)
                print(f"  [{i}/{len(nuevas)}] {key}: ERROR — {str(exc)[:80]}")
                time.sleep(_ESPERA)
                continue

            desc = hu.descripcion or ""
            patron, criterios = contar_criterios(desc)
            visual = _PATRON_DEPENDENCIA_VISUAL.search(desc)
            marcas = _marcas(desc)

            test_plan = None
            if not args.sin_test_plan:
                try:
                    encontrados = adapter.detectar_test_plan(key)
                    test_plan = encontrados[0].key if encontrados else None
                except Exception as exc:
                    fila["error"] = f"test plan: {str(exc)[:100]}"

            fila.update(
                titulo=hu.titulo or titulo_excel,
                cajon=_clasificar(len(criterios), marcas, len(desc), test_plan),
                criterios=len(criterios),
                patron=patron,
                depende_de_imagen="SI" if visual else "",
                marca_visual=visual.group(0) if visual else "",
                test_plan_key=test_plan or "",
                largo_descripcion=len(desc),
                criterios_texto=" || ".join(criterios),
            )
            filas.append(fila)
            print(f"  [{i}/{len(nuevas)}] {key}: {fila['cajon']:<14} "
                  f"{fila['criterios']} criterios ({patron})"
                  + ("  [imagen]" if visual else ""))
            time.sleep(_ESPERA)
    finally:
        adapter.cerrar()

    salida = _RAIZ / args.salida
    with salida.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNAS)
        w.writeheader()
        w.writerows(filas)

    print(f"\nEscrito: {salida}")
    _resumen(filas)


def _keys_ya_en_corpus() -> set[str]:
    """Lo que ya está medido no se vuelve a triar."""
    claves: set[str] = set()
    for nombre in ("cobertura_real_retro.csv", "retro/retro_resultado_57hu.csv"):
        ruta = _RAIZ / nombre
        if not ruta.exists():
            continue
        with ruta.open(encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                if fila.get("hu_key"):
                    claves.add(fila["hu_key"].strip())
    return claves


def _resumen(filas: list[dict]) -> None:
    cajones = Counter(f["cajon"] for f in filas)
    print("\n" + "=" * 62)
    print("TRIAJE")
    etiquetas = {
        "LISTA": "entran al corpus tal cual",
        "SIN_TEST_PLAN": "tienen criterios pero sin Test Plan histórico",
        "REVISAR_QA": "hay que mirarlas con el QA: el texto sugiere criterios",
        "DESCARTAR": "sin criterios ni señales de que los tengan",
        "ERROR": "no se pudieron traer de Jira",
    }
    for cajon, explicacion in etiquetas.items():
        n = cajones.get(cajon, 0)
        if n:
            print(f"  {cajon:<14} {n:>3}  {explicacion}")

    visuales = [f["hu_key"] for f in filas if f["depende_de_imagen"] == "SI"]
    if visuales:
        print(f"\n  Vera bloquearía {len(visuales)} de estas por depender de una imagen:")
        print(f"    {', '.join(visuales)}")
        print("  No están descartadas: el QA puede reescribir ese criterio en texto.")

    listas = cajones.get("LISTA", 0)
    crits = sum(int(f["criterios"] or 0) for f in filas if f["cajon"] == "LISTA")
    if listas:
        print(f"\n  Ampliación inmediata: +{listas} HU, +{crits} criterios.")
    if cajones.get("REVISAR_QA"):
        print(f"  Con revisión de QA podrían sumarse hasta {cajones['REVISAR_QA']} HU más.")
    print("=" * 62)


if __name__ == "__main__":
    main()
