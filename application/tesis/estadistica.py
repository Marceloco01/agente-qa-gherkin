"""
Estadística del estudio, sin dependencias externas.

Todo lo que el artículo reporta se calcula acá con la librería estándar:
U de Mann-Whitney con corrección por empates (como SPSS), tamaño del efecto
r = |Z|/√N, prueba exacta de Fisher bilateral, intervalo de Newcombe para la
diferencia de proporciones y cuartiles con las bisagras de Tukey.

Por qué sin scipy: el resultado tiene que poder auditarse línea por línea y
reproducirse en cualquier instalación del proyecto. Shapiro-Wilk es la única
excepción: su algoritmo (AS R94) no se reimplementa; si scipy está instalado
se usa, y si no, el valor se informa como no disponible.

Diseño: los dos periodos son ciclos DISTINTOS (muestras independientes). Nada
en este módulo empareja la fila N del pre-test con la fila N del post-test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, median, stdev

Z_95 = 1.959963984540054


def bisagras_tukey(valores: list[float]) -> tuple[float, float, float]:
    """Q1, mediana y Q3 con las bisagras de Tukey (las de SPSS en Explorar).

    La bisagra inferior es la mediana de la mitad inferior de los datos
    ordenados; si n es impar, la mediana entra en las dos mitades.
    """
    if not valores:
        raise ValueError("No hay valores para calcular cuartiles.")
    x = sorted(valores)
    n = len(x)
    mitad = (n + 1) // 2
    return median(x[:mitad]), median(x), median(x[n - mitad:])


@dataclass(frozen=True)
class Descriptivos:
    n: int
    media: float
    de: float
    mediana: float
    q1: float
    q3: float
    minimo: float
    maximo: float


def describir(valores: list[float]) -> Descriptivos:
    q1, med, q3 = bisagras_tukey(valores)
    return Descriptivos(
        n=len(valores),
        media=mean(valores),
        de=stdev(valores) if len(valores) > 1 else 0.0,
        mediana=med, q1=q1, q3=q3,
        minimo=min(valores), maximo=max(valores),
    )


@dataclass(frozen=True)
class ResultadoMannWhitney:
    n1: int
    n2: int
    rango_promedio_1: float
    rango_promedio_2: float
    u: float
    w: float
    z: float
    p: float
    p_articulo: float
    r: float


def _rangos(valores: list[float]) -> tuple[list[float], list[int]]:
    """Rangos promedio (empates) y tamaños de cada grupo de empates."""
    orden = sorted(range(len(valores)), key=lambda i: valores[i])
    rangos = [0.0] * len(valores)
    empates: list[int] = []
    i = 0
    while i < len(orden):
        j = i
        while j + 1 < len(orden) and valores[orden[j + 1]] == valores[orden[i]]:
            j += 1
        promedio = (i + j) / 2 + 1
        for k in range(i, j + 1):
            rangos[orden[k]] = promedio
        empates.append(j - i + 1)
        i = j + 1
    return rangos, empates


def p_desde_z_publicado(z: float) -> float:
    """p bilateral calculado a partir de Z redondeado a tres decimales.

    Así se obtuvieron los p que publica el artículo: a partir del Z con tres
    decimales que muestra la tabla de SPSS. En casi todas las pruebas da el
    mismo p que el Z completo; en el estado de defectos del análisis A,
    Z = -0.6274 da p = 0.53038 con el Z completo y 0.53066 (0.531, la cifra
    publicada) con Z = -0.627. `ResultadoMannWhitney.p` conserva el valor con
    el Z completo.
    """
    return math.erfc(round(abs(z), 3) / math.sqrt(2))


def mann_whitney(grupo1: list[float], grupo2: list[float]) -> ResultadoMannWhitney:
    """U de Mann-Whitney para dos muestras independientes (asintótica, sin
    corrección por continuidad y con corrección por empates, igual que SPSS)."""
    n1, n2 = len(grupo1), len(grupo2)
    if n1 == 0 or n2 == 0:
        raise ValueError("Los dos grupos deben tener al menos un valor.")
    rangos, empates = _rangos(list(grupo1) + list(grupo2))
    r1 = sum(rangos[:n1])
    r2 = sum(rangos[n1:])
    u1 = r1 - n1 * (n1 + 1) / 2
    u2 = n1 * n2 - u1
    u = min(u1, u2)
    w = r1 if u1 <= u2 else r2
    n = n1 + n2
    mu = n1 * n2 / 2
    correccion = sum(t ** 3 - t for t in empates) / (n * (n - 1))
    varianza = n1 * n2 / 12 * ((n + 1) - correccion)
    if varianza <= 0:
        z, p = 0.0, 1.0
    else:
        z = (u - mu) / math.sqrt(varianza)
        p = math.erfc(abs(z) / math.sqrt(2))
    return ResultadoMannWhitney(
        n1=n1, n2=n2,
        rango_promedio_1=r1 / n1, rango_promedio_2=r2 / n2,
        u=u, w=w, z=z, p=min(1.0, p), p_articulo=min(1.0, p_desde_z_publicado(z)),
        r=abs(z) / math.sqrt(n),
    )


def fisher_exacta(a: int, b: int, c: int, d: int) -> float:
    """p bilateral de la prueba exacta de Fisher para la tabla [[a, b], [c, d]].

    Suma las probabilidades hipergeométricas de todas las tablas con los mismos
    márgenes que no son más probables que la observada (criterio de SPSS/R).
    """
    fila1, col1, n = a + b, a + c, a + b + c + d
    total = math.comb(n, col1)

    def prob(x: int) -> float:
        return math.comb(fila1, x) * math.comb(n - fila1, col1 - x) / total

    observada = prob(a)
    bajo, alto = max(0, col1 - (n - fila1)), min(fila1, col1)
    p = sum(prob(x) for x in range(bajo, alto + 1)
            if prob(x) <= observada * (1 + 1e-7))
    return min(1.0, p)


def wilson(exitos: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Intervalo de Wilson (score) para una proporción."""
    if n == 0:
        raise ValueError("n debe ser positivo.")
    p = exitos / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    radio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centro - radio, centro + radio


def newcombe(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float, float]:
    """Diferencia p1 - p2 con su IC 95 % de Newcombe (método híbrido de score,
    método 10 de Newcombe, 1998). Devuelve (diferencia, límite inf., límite sup.)."""
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = wilson(x1, n1)
    l2, u2 = wilson(x2, n2)
    d = p1 - p2
    inferior = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    superior = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, inferior, superior


def shapiro_wilk(valores: list[float]) -> tuple[float, float] | None:
    """(W, p) de Shapiro-Wilk si scipy está disponible; None si no lo está
    o si los datos son constantes (la prueba no está definida)."""
    try:
        from scipy.stats import shapiro
    except ImportError:
        return None
    if len(set(valores)) < 2 or len(valores) < 3:
        return None
    resultado = shapiro(valores)
    return float(resultado.statistic), float(resultado.pvalue)
