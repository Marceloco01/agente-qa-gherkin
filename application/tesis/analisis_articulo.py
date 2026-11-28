"""
Caso de uso: todos los resultados estadísticos del artículo, desde la Hoja de
datos 1.

Reproduce las Tablas 4 a 7 y las cifras del texto:

- Tabla 4: índice del periodo (suma de numeradores / suma de denominadores),
  media y DE por ciclo, mediana y cuartiles (bisagras de Tukey), ciclos al
  100 %, con la diferencia de proporciones (Newcombe) y Fisher exacta.
- Tabla 5: U de Mann-Whitney para muestras independientes (rangos promedio,
  U, Z, p, r) en los tres indicadores y tres variables de apoyo.
- Tabla 6: defectos detectados y corregidos por severidad.
- Tabla 7: análisis principal y de sensibilidad A, B y C, con Bonferroni.

Los índices por ciclo con denominador 0 no se imputan: quedan fuera del
indicador (por eso el estado de defectos solo usa ciclos con defectos).
"""

from __future__ import annotations

from dataclasses import asdict

from application.tesis.estadistica import (
    describir,
    fisher_exacta,
    mann_whitney,
    newcombe,
    shapiro_wilk,
)
from application.tesis.hoja_datos import ANALISIS, ETIQUETA_SEVERIDAD, SEVERIDADES, Ciclo

ALFA = 0.05
N_INDICADORES = 3
ALFA_BONFERRONI = ALFA / N_INDICADORES

INDICADORES = {
    "ejecuciones": ("casos_ejecutados", "casos_especificados", "indice_ejecuciones"),
    "cobertura": ("situaciones_cubiertas", "situaciones_identificadas", "indice_cobertura"),
    "estado_defectos": ("defectos_corregidos", "defectos_detectados", "estado_defectos"),
}
VARIABLES_APOYO = ("defectos_detectados", "situaciones_identificadas", "casos_especificados")


def _es_100(v: float) -> bool:
    return abs(v - 100.0) < 1e-9


def _resumen_periodo(ciclos: list[Ciclo], indicador: str) -> dict:
    num_attr, den_attr, idx_attr = INDICADORES[indicador]
    valores = [getattr(c, idx_attr) for c in ciclos]
    valores = [v for v in valores if v is not None]
    num = sum(getattr(c, num_attr) for c in ciclos)
    den = sum(getattr(c, den_attr) for c in ciclos)
    salida = {
        "ciclos": len(ciclos),
        "ciclos_con_indice": len(valores),
        "numerador": num,
        "denominador": den,
        "indice": 100 * num / den if den else None,
        "ciclos_al_100": sum(1 for v in valores if _es_100(v)),
    }
    if valores:
        d = describir(valores)
        salida.update(media=d.media, de=d.de, mediana=d.mediana, q1=d.q1, q3=d.q3,
                      minimo=d.minimo, maximo=d.maximo,
                      pct_ciclos_al_100=100 * salida["ciclos_al_100"] / len(valores))
        sw = shapiro_wilk(valores)
        salida["shapiro_wilk"] = None if sw is None else {"w": sw[0], "p": sw[1]}
    return salida


def _comparar(pre: list[Ciclo], post: list[Ciclo], indicador: str) -> dict:
    idx_attr = INDICADORES[indicador][2]
    a = [v for v in (getattr(c, idx_attr) for c in pre) if v is not None]
    b = [v for v in (getattr(c, idx_attr) for c in post) if v is not None]
    resultado = {
        "pre": _resumen_periodo(pre, indicador),
        "post": _resumen_periodo(post, indicador),
    }
    if a and b:
        mw = mann_whitney(a, b)
        resultado["mann_whitney"] = asdict(mw)
        resultado["significativo_bonferroni"] = mw.p < ALFA_BONFERRONI
    if indicador != "estado_defectos" and a and b:
        x_pre = sum(1 for v in a if _es_100(v))
        x_post = sum(1 for v in b if _es_100(v))
        dif, li, ls = newcombe(x_post, len(b), x_pre, len(a))
        resultado["ciclos_al_100"] = {
            "pre": x_pre, "n_pre": len(a), "post": x_post, "n_post": len(b),
            "diferencia_pp": 100 * dif, "ic95_inf_pp": 100 * li, "ic95_sup_pp": 100 * ls,
            "p_fisher": fisher_exacta(x_post, len(b) - x_post, x_pre, len(a) - x_pre),
        }
    return resultado


def _subconjunto(ciclos: list[Ciclo], analisis: str | None) -> tuple[list[Ciclo], list[Ciclo]]:
    pre = [c for c in ciclos if c.periodo == "pre"]
    post = [c for c in ciclos if c.periodo == "post"]
    if analisis is not None:
        pre = [c for c in pre if not c.excluido_en(analisis)]
        post = [c for c in post if not c.excluido_en(analisis)]
    return pre, post


def _severidad(ciclos: list[Ciclo]) -> list[dict]:
    filas = []
    for s in SEVERIDADES + ("total",):
        fila = {"severidad": "Total" if s == "total" else ETIQUETA_SEVERIDAD[s]}
        for periodo in ("pre", "post"):
            grupo = [c for c in ciclos if c.periodo == periodo]
            if s == "total":
                det = sum(c.defectos_detectados for c in grupo)
                corr = sum(c.defectos_corregidos for c in grupo)
            else:
                det = sum(c.detectados_por_severidad.get(s, 0) for c in grupo)
                corr = sum(c.corregidos_por_severidad.get(s, 0) for c in grupo)
            fila[f"detectados_{periodo}"] = det
            fila[f"corregidos_{periodo}"] = corr
            fila[f"estado_{periodo}"] = 100 * corr / det if det else None
        filas.append(fila)
    return filas


def calcular(ciclos: list[Ciclo]) -> dict:
    pre, post = _subconjunto(ciclos, None)
    resultados: dict = {
        "diseno": "muestras independientes (ciclos distintos en cada periodo)",
        "alfa": ALFA,
        "alfa_bonferroni": ALFA_BONFERRONI,
        "principal": {ind: _comparar(pre, post, ind) for ind in INDICADORES},
        "variables_apoyo": {},
        "severidad": _severidad(ciclos),
        "sensibilidad": {},
        "exclusiones": {},
    }
    for var in VARIABLES_APOYO:
        a = [float(getattr(c, var)) for c in pre]
        b = [float(getattr(c, var)) for c in post]
        resultados["variables_apoyo"][var] = {
            "media_pre": sum(a) / len(a), "media_post": sum(b) / len(b),
            "total_pre": sum(a), "total_post": sum(b),
            "mann_whitney": asdict(mann_whitney(a, b)),
        }
    for nombre in ANALISIS:
        sub_pre, sub_post = _subconjunto(ciclos, nombre)
        excluidos = [c.ciclo for c in ciclos if c.excluido_en(nombre)]
        resultados["exclusiones"][nombre] = excluidos
        resultados["sensibilidad"][nombre] = {
            "ciclos_pre": len(sub_pre), "ciclos_post": len(sub_post),
            **{ind: _comparar(sub_pre, sub_post, ind) for ind in INDICADORES},


            "excluidos_con_defectos": sum(
                1 for c in ciclos if c.excluido_en(nombre) and c.defectos_detectados > 0),
        }
    return resultados
