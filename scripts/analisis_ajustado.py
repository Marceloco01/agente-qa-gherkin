"""
Análisis complementarios de la revisión (v1.0.2), a partir de la Hoja de datos 1.

    python scripts/analisis_ajustado.py --hoja datos/hoja_datos_1.csv
    python scripts/analisis_ajustado.py --hoja datos/hoja_datos_1.csv --analisis B
    python scripts/analisis_ajustado.py --plantilla-kappa criterios.csv --salida plantilla_kappa.csv
    python scripts/analisis_ajustado.py --kappa plantilla_kappa_completada.csv

- Modelos ajustados (ver application/tesis/modelos_ajustados.py): cobertura
  ajustada por log(casos especificados), ejecuciones y defectos por caso.
- --plantilla-kappa: recibe un CSV con columnas ciclo, criterio (texto del
  criterio de aceptación) y escribe una plantilla con el orden de los ciclos
  BARAJADO y sin la columna de periodo, para que un segundo analista marque
  1/0 en `evaluador_2` sin saber de qué periodo es cada ciclo. El primer
  evaluador completa `evaluador_1` con sus juicios originales.
- --kappa: calcula el kappa de Cohen sobre la plantilla completada.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from dataclasses import asdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from application.tesis.hoja_datos import leer_hoja
from application.tesis.modelos_ajustados import (
    leer_hoja_kappa,
    modelo_cobertura,
    modelo_defectos,
    modelo_ejecuciones,
)


def _p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def _linea(m, termino: str, etiqueta: str) -> str:
    c = m.coef(termino)
    return (f"| {m.indicador} | {m.familia} | {m.n_ciclos} | {etiqueta} | "
            f"{c.exp_estimado:.2f} ({c.ic_inferior:.2f} a {c.ic_superior:.2f}) | "
            f"{_p(c.p)} | {m.dispersion:.2f} |")


def modelos(hoja: Path, analisis: str | None) -> dict:
    ciclos = leer_hoja(hoja)
    if analisis:
        ciclos = [c for c in ciclos if not c.excluido_en(analisis)]
    mc, me, md = modelo_cobertura(ciclos), modelo_ejecuciones(ciclos), modelo_defectos(ciclos)
    print(f"\n## Modelos ajustados ({'análisis ' + analisis if analisis else 'análisis principal'})\n")
    print("| Indicador | Modelo | Ciclos | Término | OR / RT (IC 95 %) | p | Dispersión |")
    print("|---|---|---|---|---|---|---|")
    print(_linea(mc, "post_test", "post-test (OR)"))
    print(_linea(mc, "log_casos", "log casos (OR)"))
    print(_linea(me, "post_test", "post-test (OR)"))
    print(_linea(md, "post_test", "post-test (razón de tasas por caso)"))
    return {m.indicador: asdict(m) for m in (mc, me, md)}


def plantilla_kappa(entrada: Path, salida: Path, semilla: int = 2026) -> None:
    with entrada.open(encoding="utf-8-sig", newline="") as f:
        filas = [{"ciclo": r["ciclo"], "criterio": r["criterio"]} for r in csv.DictReader(f)]
    ciclos = sorted({r["ciclo"] for r in filas})
    random.Random(semilla).shuffle(ciclos)
    alias = {c: f"C{i + 1:03d}" for i, c in enumerate(ciclos)}
    orden = {c: i for i, c in enumerate(ciclos)}
    filas.sort(key=lambda r: orden[r["ciclo"]])
    with salida.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["codigo_ciego", "criterio", "evaluador_1", "evaluador_2"])
        for r in filas:
            w.writerow([alias[r["ciclo"]], r["criterio"], "", ""])
    clave = salida.with_name(salida.stem + "_CLAVE_no_entregar.csv")
    with clave.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["codigo_ciego", "ciclo"])
        for c in ciclos:
            w.writerow([alias[c], c])
    print(f"Plantilla: {salida}\nClave (no entregar al segundo evaluador): {clave}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hoja", type=Path)
    ap.add_argument("--analisis", choices=["A", "B", "C"])
    ap.add_argument("--json", type=Path, help="guardar los modelos en JSON")
    ap.add_argument("--plantilla-kappa", type=Path)
    ap.add_argument("--salida", type=Path, default=Path("plantilla_kappa.csv"))
    ap.add_argument("--kappa", type=Path)
    a = ap.parse_args()
    if a.plantilla_kappa:
        plantilla_kappa(a.plantilla_kappa, a.salida)
        return 0
    if a.kappa:
        k = leer_hoja_kappa(a.kappa)
        print(f"n = {k.n}; acuerdo = {100 * k.acuerdo_observado:.1f} %; "
              f"kappa = {k.kappa:.2f} (IC 95 %: {k.ic_inferior:.2f} a {k.ic_superior:.2f})")
        return 0
    if not a.hoja:
        ap.error("indica --hoja, --plantilla-kappa o --kappa")
    res = modelos(a.hoja, a.analisis)
    if a.json:
        a.json.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
