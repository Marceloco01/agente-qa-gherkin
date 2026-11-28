"""
Reproduce todos los resultados estadísticos del artículo desde la Hoja de
datos 1 y, con --verificar, los compara contra las cifras publicadas.

    python scripts/analisis_estadistico.py --hoja datos/hoja_datos_1.csv
    python scripts/analisis_estadistico.py --hoja datos/hoja_datos_1.csv --verificar

Salidas (en la carpeta de la hoja, salvo que se indique otra):

- resultados_estadisticos.json: todos los valores, sin redondear.
- resultados_estadisticos.md: las Tablas 4 a 7 en el formato del artículo.

--verificar usa scripts/valores_articulo.json: cada cifra publicada se compara
con el cálculo redondeado a los mismos decimales. Termina con código 1 si
alguna no coincide, e indica cuál.

Pruebas: U de Mann-Whitney para muestras independientes (como SPSS: sin
corrección por continuidad y con corrección por empates), r = |Z|/√N, Fisher
exacta bilateral, IC 95 % de Newcombe y Bonferroni (α = 0.05/3). Shapiro-Wilk
se calcula solo si scipy está instalado.

Los p de la U de Mann-Whitney se muestran y se verifican como los publica el
artículo: calculados con el Z redondeado a tres decimales que muestra SPSS
(`p_articulo`). El JSON de salida guarda también `p`, con el Z completo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from application.tesis.analisis_articulo import (
    ALFA_BONFERRONI,
    INDICADORES,
    calcular,
)
from application.tesis.hoja_datos import leer_hoja, validar

NOMBRES = {"ejecuciones": "Ejecuciones", "cobertura": "Cobertura",
           "estado_defectos": "Estado de defectos"}
APOYO = {"defectos_detectados": "Defectos detectados por ciclo",
         "situaciones_identificadas": "Situaciones identificadas por ciclo",
         "casos_especificados": "Casos especificados por ciclo"}


def _f(v, d=2) -> str:
    return "-" if v is None else f"{v:.{d}f}"


def _p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def _p_texto(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def _indice(per: dict) -> str:
    return f"{_f(per['indice'])} % ({per['numerador']} / {per['denominador']})"


def markdown(r: dict) -> str:
    L: list[str] = ["# Resultados estadísticos (reproducción del artículo)", "",
                    f"Diseño: {r['diseno']}. α = {r['alfa']}; Bonferroni α = "
                    f"{ALFA_BONFERRONI:.3f}.", ""]
    L += ["## Tabla 4. Índices de ejecuciones y de cobertura por periodo", "",
          "| Indicador y periodo | Ciclos | Num. / den. | Índice | Media (DE) | "
          "Mediana [Q1-Q3] | Ciclos al 100 % |", "|---|---|---|---|---|---|---|"]
    for ind in ("ejecuciones", "cobertura"):
        for per in ("pre", "post"):
            x = r["principal"][ind][per]
            L.append(f"| {NOMBRES[ind]}, {per}-test | {x['ciclos']} | {x['numerador']} / "
                     f"{x['denominador']} | {_f(x['indice'])} % | {_f(x['media'])} "
                     f"({_f(x['de'])}) | {_f(x['mediana'])} [{_f(x['q1'])}-{_f(x['q3'])}] | "
                     f"{x['ciclos_al_100']} ({_f(x['pct_ciclos_al_100'], 1)} %) |")
    for ind in ("ejecuciones", "cobertura"):
        c = r["principal"][ind]["ciclos_al_100"]
        L.append(f"\n{NOMBRES[ind]}: diferencia de ciclos al 100 % = "
                 f"{_f(c['diferencia_pp'], 1)} pp (IC 95 % Newcombe: "
                 f"{_f(c['ic95_inf_pp'], 1)} a {_f(c['ic95_sup_pp'], 1)}); Fisher, "
                 f"{_p_texto(c['p_fisher'])}.")
    L += ["", "Normalidad (Shapiro-Wilk):", ""]
    for ind in INDICADORES:
        for per in ("pre", "post"):
            sw = r["principal"][ind][per].get("shapiro_wilk")
            texto = "no disponible (instale scipy)" if sw is None else \
                f"W = {sw['w']:.3f}; {_p_texto(sw['p'])}"
            L.append(f"- {NOMBRES[ind]}, {per}-test: {texto}")

    L += ["", "## Tabla 5. Comparación entre periodos (U de Mann-Whitney)", "",
          "| Variable (ciclos pre y post) | Rango prom. pre | Rango prom. post | U | Z | p | r |",
          "|---|---|---|---|---|---|---|"]
    filas = [(f"Índice de {NOMBRES[i].lower()}", r["principal"][i]) for i in INDICADORES]
    filas += [(APOYO[v], r["variables_apoyo"][v]) for v in APOYO]
    for nombre, x in filas:
        mw = x["mann_whitney"]
        L.append(f"| {nombre} ({mw['n1']} y {mw['n2']}) | {_f(mw['rango_promedio_1'])} | "
                 f"{_f(mw['rango_promedio_2'])} | {_f(mw['u'], 1)} | {_f(mw['z'])} | "
                 f"{_p(mw['p_articulo'])} | {_f(mw['r'])} |")

    L += ["", "## Tabla 6. Estado de defectos por severidad y periodo", "",
          "| Severidad | Det. pre | Corr. pre | Estado pre | Det. post | Corr. post | Estado post |",
          "|---|---|---|---|---|---|---|"]
    for s in r["severidad"]:
        L.append(f"| {s['severidad']} | {s['detectados_pre']} | {s['corregidos_pre']} | "
                 f"{_f(s['estado_pre'])} | {s['detectados_post']} | {s['corregidos_post']} | "
                 f"{_f(s['estado_post'])} |")

    L += ["", "## Tabla 7. Análisis principal y de sensibilidad", "",
          "| Indicador y análisis | Ciclos pre | Pre-test | Post-test | p | r | "
          "Ciclos al 100 % pre / post (p de Fisher) |", "|---|---|---|---|---|---|---|"]
    for ind in INDICADORES:
        bloques = [("principal", r["principal"][ind])]
        bloques += [(f"análisis {a}", r["sensibilidad"][a][ind]) for a in r["sensibilidad"]]
        for etiqueta, x in bloques:
            mw = x.get("mann_whitney")
            c = x.get("ciclos_al_100")
            fisher = "-" if not c else (
                f"{c['pre']} ({_f(100 * c['pre'] / c['n_pre'], 1)} %) / {c['post']} "
                f"({_f(100 * c['post'] / c['n_post'], 1)} %) ({_p(c['p_fisher'])})")
            n_pre = x["pre"]["ciclos_con_indice"] if ind == "estado_defectos" else x["pre"]["ciclos"]
            L.append(f"| {NOMBRES[ind]}, {etiqueta} | {n_pre} | {_indice(x['pre'])} | "
                     f"{_indice(x['post'])} | {_p(mw['p_articulo']) if mw else '-'} | "
                     f"{_f(mw['r']) if mw else '-'} | {fisher} |")
    L += ["", "Ciclos excluidos en cada análisis:", ""]
    for a, lista in r["exclusiones"].items():
        con_def = r["sensibilidad"][a]["excluidos_con_defectos"]
        L.append(f"- {a} ({len(lista)}): {', '.join(lista) or '-'}; con defectos: {con_def}")
    return "\n".join(L) + "\n"


def _obtener(resultados: dict, ruta: str):
    actual = resultados
    for parte in ruta.split("."):
        actual = actual[int(parte)] if isinstance(actual, list) else actual[parte]
    return actual


def verificar(resultados: dict, esperados: list[dict]) -> list[str]:
    fallas: list[str] = []
    for e in esperados:
        try:
            v = _obtener(resultados, e["ruta"])
        except (KeyError, IndexError, TypeError):
            fallas.append(f"{e['ruta']}: no se pudo calcular")
            continue
        if "menor_que" in e:
            if not (v is not None and v < e["menor_que"]):
                fallas.append(f"{e['ruta']}: publicado < {e['menor_que']}, calculado {v}")
            continue
        d = e.get("decimales", 0)
        if v is None or round(float(v), d) != round(float(e["valor"]), d):
            fallas.append(f"{e['ruta']}: publicado {e['valor']}, calculado "
                          f"{'-' if v is None else round(float(v), d + 2)}")
    return fallas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hoja", type=Path, required=True, help="Hoja de datos 1 (CSV largo)")
    ap.add_argument("--salida", type=Path, help="Carpeta de salida (por defecto, la de la hoja)")
    ap.add_argument("--verificar", action="store_true",
                    help="Comparar contra scripts/valores_articulo.json")
    ap.add_argument("--valores", type=Path, default=RAIZ / "scripts" / "valores_articulo.json")
    ap.add_argument("--ciclos-por-periodo", type=int, default=60)
    args = ap.parse_args(argv)

    ciclos = leer_hoja(args.hoja)
    errores = validar(ciclos, args.ciclos_por_periodo)
    if errores:
        print("La Hoja de datos 1 no es consistente; corra construir_hoja_datos.py:")
        for e in errores:
            print(f"  - {e}")
        return 1

    resultados = calcular(ciclos)
    salida = args.salida or args.hoja.parent
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "resultados_estadisticos.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    md = markdown(resultados)
    (salida / "resultados_estadisticos.md").write_text(md, encoding="utf-8")
    print(md)

    if args.verificar:
        esperados = json.loads(args.valores.read_text(encoding="utf-8"))["valores"]
        fallas = verificar(resultados, esperados)
        if fallas:
            print(f"VERIFICACIÓN: {len(fallas)} de {len(esperados)} cifras NO coinciden:")
            for f in fallas:
                print(f"  - {f}")
            return 1
        print(f"VERIFICACIÓN: las {len(esperados)} cifras publicadas coinciden con el cálculo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
