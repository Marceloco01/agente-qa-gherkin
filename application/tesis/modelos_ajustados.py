"""
Análisis complementarios de la v1.0.2 (revisión del artículo).

1. Modelos lineales generalizados por ciclo, ajustados por el número de
   casos especificados, para responder a la objeción de que la cobertura
   sube "porque hay más casos":

   - Cobertura: situaciones cubiertas de las identificadas, binomial con
     sobredispersión (cuasi-binomial), con periodo + log(casos especificados).
   - Ejecuciones: casos ejecutados de los especificados, cuasi-binomial, con
     periodo.
   - Defectos detectados: cuasi-Poisson con *offset* log(casos especificados),
     es decir, una razón de tasas de defectos por caso.

   El ajuste es por mínimos cuadrados reponderados iterativamente (IRLS) con
   numpy, sin statsmodels, para no sumar dependencias. Los errores estándar
   se escalan por la dispersión de Pearson (cuasi-verosimilitud). Los
   intervalos son de Wald al 95 %.

2. Concordancia entre dos evaluadores de cobertura (kappa de Cohen), para la
   segunda evaluación ciega que pide la revisión. La plantilla la genera
   `scripts/analisis_ajustado.py --plantilla-kappa`.

Nada de esto cambia los análisis principales del artículo (Tablas 4 a 7).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from application.tesis.hoja_datos import Ciclo

Z95 = 1.959963984540054


def _norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


@dataclass(frozen=True)
class Coeficiente:
    nombre: str
    estimado: float
    error_estandar: float
    z: float
    p: float
    exp_estimado: float
    ic_inferior: float
    ic_superior: float


@dataclass(frozen=True)
class ModeloAjustado:
    indicador: str
    familia: str
    n_ciclos: int
    dispersion: float
    coeficientes: tuple[Coeficiente, ...]

    def coef(self, nombre: str) -> Coeficiente:
        return next(c for c in self.coeficientes if c.nombre == nombre)


def _irls(X, y, n, familia: str, offset=None, max_iter: int = 100, tol: float = 1e-10):
    """GLM por IRLS. binomial: y = éxitos, n = ensayos. poisson: y = conteos."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    off = np.zeros(len(y)) if offset is None else np.asarray(offset, float)
    beta = np.zeros(X.shape[1])
    if familia == "binomial":
        n = np.asarray(n, float)
        p0 = np.clip((y + 0.5) / (n + 1.0), 1e-6, 1 - 1e-6)
        eta = np.log(p0 / (1 - p0))
    else:
        eta = np.log(y + 0.5)
    for _ in range(max_iter):
        if familia == "binomial":
            mu = 1 / (1 + np.exp(-eta))
            mu = np.clip(mu, 1e-10, 1 - 1e-10)
            w = n * mu * (1 - mu)
            zt = eta - off + (y - n * mu) / w
        else:
            mu = np.exp(eta)
            w = mu
            zt = eta - off + (y - mu) / mu
        WX = X * w[:, None]
        nuevo = np.linalg.solve(X.T @ WX, WX.T @ zt)
        eta = X @ nuevo + off
        if np.max(np.abs(nuevo - beta)) < tol:
            beta = nuevo
            break
        beta = nuevo
    if familia == "binomial":
        mu = 1 / (1 + np.exp(-eta))
        var = n * mu * (1 - mu)
        resid = (y - n * mu) / np.sqrt(np.maximum(var, 1e-12))
    else:
        mu = np.exp(eta)
        var = mu
        resid = (y - mu) / np.sqrt(np.maximum(var, 1e-12))
    gl = max(len(y) - X.shape[1], 1)
    dispersion = max(float(np.sum(resid**2) / gl), 1.0)
    WX = X * var[:, None]
    cov = np.linalg.inv(X.T @ WX) * dispersion
    return beta, np.sqrt(np.diag(cov)), dispersion


def _coeficientes(nombres, beta, se) -> tuple[Coeficiente, ...]:
    out = []
    for nm, b, s in zip(nombres, beta, se):
        z = b / s if s > 0 else float("nan")
        out.append(Coeficiente(
            nombre=nm, estimado=float(b), error_estandar=float(s), z=float(z),
            p=float(2 * _norm_sf(abs(z))), exp_estimado=float(math.exp(b)),
            ic_inferior=float(math.exp(b - Z95 * s)),
            ic_superior=float(math.exp(b + Z95 * s)),
        ))
    return tuple(out)


def _post(c: Ciclo) -> float:
    return 1.0 if c.periodo == "post" else 0.0


def modelo_cobertura(ciclos: list[Ciclo]) -> ModeloAjustado:
    cs = [c for c in ciclos if c.situaciones_identificadas > 0 and c.casos_especificados > 0]
    X = [[1.0, _post(c), math.log(c.casos_especificados)] for c in cs]
    beta, se, disp = _irls(X, [c.situaciones_cubiertas for c in cs],
                           [c.situaciones_identificadas for c in cs], "binomial")
    return ModeloAjustado("cobertura", "cuasi-binomial", len(cs), disp,
                          _coeficientes(["intercepto", "post_test", "log_casos"], beta, se))


def modelo_ejecuciones(ciclos: list[Ciclo]) -> ModeloAjustado:
    cs = [c for c in ciclos if c.casos_especificados > 0]
    X = [[1.0, _post(c)] for c in cs]
    beta, se, disp = _irls(X, [c.casos_ejecutados for c in cs],
                           [c.casos_especificados for c in cs], "binomial")
    return ModeloAjustado("ejecuciones", "cuasi-binomial", len(cs), disp,
                          _coeficientes(["intercepto", "post_test"], beta, se))


def modelo_defectos(ciclos: list[Ciclo]) -> ModeloAjustado:
    cs = [c for c in ciclos if c.casos_especificados > 0]
    X = [[1.0, _post(c)] for c in cs]
    off = [math.log(c.casos_especificados) for c in cs]
    beta, se, disp = _irls(X, [c.defectos_detectados for c in cs], None,
                           "poisson", offset=off)
    return ModeloAjustado("defectos_por_caso", "cuasi-Poisson (offset log casos)",
                          len(cs), disp,
                          _coeficientes(["intercepto", "post_test"], beta, se))


@dataclass(frozen=True)
class Concordancia:
    n: int
    acuerdo_observado: float
    kappa: float
    ic_inferior: float
    ic_superior: float


def kappa_cohen(evaluador_1: list[int], evaluador_2: list[int]) -> Concordancia:
    """Kappa de Cohen para juicios binarios (1 = cubierto, 0 = no cubierto),
    con IC 95 % por la aproximación de error estándar de Fleiss et al."""
    if len(evaluador_1) != len(evaluador_2) or not evaluador_1:
        raise ValueError("Se necesitan dos listas no vacías del mismo largo.")
    a = np.asarray(evaluador_1, int)
    b = np.asarray(evaluador_2, int)
    n = len(a)
    po = float(np.mean(a == b))
    p1a, p1b = a.mean(), b.mean()
    pe = float(p1a * p1b + (1 - p1a) * (1 - p1b))
    if pe >= 1:
        return Concordancia(n, po, 1.0, 1.0, 1.0)
    k = (po - pe) / (1 - pe)
    se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
    return Concordancia(n, po, k, k - Z95 * se, k + Z95 * se)


def leer_hoja_kappa(ruta: Path) -> Concordancia:
    """Lee la plantilla completada (columnas evaluador_1, evaluador_2 con 0/1)."""
    e1, e2 = [], []
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            v1, v2 = fila.get("evaluador_1", "").strip(), fila.get("evaluador_2", "").strip()
            if v1 in {"0", "1"} and v2 in {"0", "1"}:
                e1.append(int(v1))
                e2.append(int(v2))
    return kappa_cohen(e1, e2)
