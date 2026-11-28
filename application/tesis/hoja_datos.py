"""
Hoja de datos 1: la tabla por ciclo que sustenta el artículo.

Formato LARGO, una fila por ciclo y periodo. Es deliberado: el pre-test
(CP1..CP60) y el post-test (PT1..PT60) son ciclos distintos, y una tabla ancha
con "la fila N del pre al lado de la fila N del post" sugiere un emparejamiento
que no existe.

Columnas (en este orden):

    periodo                      pre | post
    ciclo                        CP1..CP60 / PT1..PT60
    situaciones_identificadas    denominador del índice de cobertura
    situaciones_cubiertas        numerador del índice de cobertura
    casos_especificados          denominador del índice de ejecuciones
    casos_ejecutados             numerador del índice de ejecuciones
    defectos_detectados          denominador del estado de defectos
    defectos_corregidos          numerador del estado de defectos
    det_bajo, det_medio, det_alto, det_critico     detectados por severidad
    corr_bajo, corr_medio, corr_alto, corr_critico corregidos por severidad
    marcas                       códigos separados por ';' (ver MARCAS)
    excluido_A, excluido_B, excluido_C             1 si el análisis lo excluye

Los análisis de sensibilidad se definen SOLO a partir de las marcas, en
ANALISIS. Así, quien lea la hoja puede rehacer cada análisis con un filtro.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

SEVERIDADES = ("bajo", "medio", "alto", "critico")
ETIQUETA_SEVERIDAD = {"bajo": "Bajo", "medio": "Medio", "alto": "Alto",
                      "critico": "Crítico"}


MARCAS = {
    "sin_ejecuciones": "Pre-test: ejecuciones creadas en Xray pero vacías "
                       "(pruebas documentadas fuera de Xray).",
    "certificado_en_post": "Pre-test: certificación registrada dentro del "
                           "periodo del post-test.",
    "ejecuciones_no_vinculadas": "Pre-test: parte de las pruebas se ejecutó en "
                                 "ejecuciones no vinculadas al plan de la historia.",
    "umbral_vera_reducido": "Post-test: ingresó con el umbral de Vera reducido "
                            "temporalmente a 35.",
    "patrones_ampliados": "Post-test: ingresó tras ampliar los patrones de "
                          "reconocimiento de criterios de aceptación.",
}


ANALISIS = {
    "A": ("pre", {"sin_ejecuciones", "certificado_en_post"}),
    "B": ("pre", {"sin_ejecuciones", "certificado_en_post",
                  "ejecuciones_no_vinculadas"}),
    "C": ("post", {"umbral_vera_reducido", "patrones_ampliados"}),
}

COLUMNAS = (
    ["periodo", "ciclo",
     "situaciones_identificadas", "situaciones_cubiertas",
     "casos_especificados", "casos_ejecutados",
     "defectos_detectados", "defectos_corregidos"]
    + [f"det_{s}" for s in SEVERIDADES]
    + [f"corr_{s}" for s in SEVERIDADES]
    + ["marcas", "excluido_A", "excluido_B", "excluido_C"]
)

_PATRON_ID = {"pre": re.compile(r"^CP\d+$"), "post": re.compile(r"^PT\d+$")}


@dataclass(frozen=True)
class Ciclo:
    periodo: str
    ciclo: str
    situaciones_identificadas: int
    situaciones_cubiertas: int
    casos_especificados: int
    casos_ejecutados: int
    defectos_detectados: int
    defectos_corregidos: int
    detectados_por_severidad: dict[str, int]
    corregidos_por_severidad: dict[str, int]
    marcas: frozenset[str] = field(default_factory=frozenset)


    @property
    def indice_ejecuciones(self) -> float | None:
        return (100 * self.casos_ejecutados / self.casos_especificados
                if self.casos_especificados else None)

    @property
    def indice_cobertura(self) -> float | None:
        return (100 * self.situaciones_cubiertas / self.situaciones_identificadas
                if self.situaciones_identificadas else None)

    @property
    def estado_defectos(self) -> float | None:
        return (100 * self.defectos_corregidos / self.defectos_detectados
                if self.defectos_detectados else None)

    def excluido_en(self, analisis: str) -> bool:
        periodo, motivos = ANALISIS[analisis]
        return self.periodo == periodo and bool(self.marcas & motivos)

    def como_fila(self) -> dict[str, object]:
        fila: dict[str, object] = {
            "periodo": self.periodo, "ciclo": self.ciclo,
            "situaciones_identificadas": self.situaciones_identificadas,
            "situaciones_cubiertas": self.situaciones_cubiertas,
            "casos_especificados": self.casos_especificados,
            "casos_ejecutados": self.casos_ejecutados,
            "defectos_detectados": self.defectos_detectados,
            "defectos_corregidos": self.defectos_corregidos,
        }
        for s in SEVERIDADES:
            fila[f"det_{s}"] = self.detectados_por_severidad.get(s, 0)
        for s in SEVERIDADES:
            fila[f"corr_{s}"] = self.corregidos_por_severidad.get(s, 0)
        fila["marcas"] = ";".join(sorted(self.marcas))
        for a in ANALISIS:
            fila[f"excluido_{a}"] = int(self.excluido_en(a))
        return fila


def validar(ciclos: list[Ciclo], esperado_por_periodo: int | None = 60) -> list[str]:
    """Errores de consistencia. Una lista vacía significa que la hoja es válida."""
    errores: list[str] = []
    vistos: set[tuple[str, str]] = set()
    for c in ciclos:
        ref = f"{c.periodo}/{c.ciclo}"
        if c.periodo not in _PATRON_ID:
            errores.append(f"{ref}: periodo desconocido (use 'pre' o 'post').")
            continue
        if not _PATRON_ID[c.periodo].match(c.ciclo):
            errores.append(f"{ref}: el código no es anónimo "
                           f"({'CPn' if c.periodo == 'pre' else 'PTn'}).")
        if (c.periodo, c.ciclo) in vistos:
            errores.append(f"{ref}: ciclo repetido.")
        vistos.add((c.periodo, c.ciclo))
        for num, den, nombre in (
            (c.situaciones_cubiertas, c.situaciones_identificadas, "situaciones"),
            (c.casos_ejecutados, c.casos_especificados, "casos"),
            (c.defectos_corregidos, c.defectos_detectados, "defectos"),
        ):
            if min(num, den) < 0:
                errores.append(f"{ref}: valores negativos en {nombre}.")
            if num > den:
                errores.append(f"{ref}: {nombre}: numerador {num} > denominador {den}.")
        if sum(c.detectados_por_severidad.values()) != c.defectos_detectados:
            errores.append(f"{ref}: los detectados por severidad no suman "
                           f"{c.defectos_detectados}.")
        if sum(c.corregidos_por_severidad.values()) != c.defectos_corregidos:
            errores.append(f"{ref}: los corregidos por severidad no suman "
                           f"{c.defectos_corregidos}.")
        for s in SEVERIDADES:
            if c.corregidos_por_severidad.get(s, 0) > c.detectados_por_severidad.get(s, 0):
                errores.append(f"{ref}: severidad {s}: corregidos > detectados.")
        desconocidas = c.marcas - set(MARCAS)
        if desconocidas:
            errores.append(f"{ref}: marcas desconocidas {sorted(desconocidas)}.")
        for m in c.marcas & set(MARCAS):
            esperado = "pre" if m in ANALISIS["B"][1] else "post"
            if c.periodo != esperado:
                errores.append(f"{ref}: la marca '{m}' corresponde al {esperado}-test.")
    if esperado_por_periodo is not None:
        for periodo in ("pre", "post"):
            n = sum(1 for c in ciclos if c.periodo == periodo)
            if n != esperado_por_periodo:
                errores.append(f"{periodo}: {n} ciclos (se esperaban "
                               f"{esperado_por_periodo}).")
    return errores


def _entero(fila: dict[str, str], clave: str) -> int:
    valor = (fila.get(clave) or "").strip()
    return int(float(valor)) if valor else 0


def _marcas(texto: str) -> frozenset[str]:
    return frozenset(m.strip() for m in (texto or "").split(";") if m.strip())


def leer_hoja(ruta: Path) -> list[Ciclo]:
    with Path(ruta).open(encoding="utf-8-sig", newline="") as fh:
        filas = [f for f in csv.DictReader(fh) if (f.get("ciclo") or "").strip()]
    return [
        Ciclo(
            periodo=f["periodo"].strip().lower(),
            ciclo=f["ciclo"].strip(),
            situaciones_identificadas=_entero(f, "situaciones_identificadas"),
            situaciones_cubiertas=_entero(f, "situaciones_cubiertas"),
            casos_especificados=_entero(f, "casos_especificados"),
            casos_ejecutados=_entero(f, "casos_ejecutados"),
            defectos_detectados=_entero(f, "defectos_detectados"),
            defectos_corregidos=_entero(f, "defectos_corregidos"),
            detectados_por_severidad={s: _entero(f, f"det_{s}") for s in SEVERIDADES},
            corregidos_por_severidad={s: _entero(f, f"corr_{s}") for s in SEVERIDADES},
            marcas=_marcas(f.get("marcas", "")),
        )
        for f in filas
    ]


def escribir_hoja(ciclos: list[Ciclo], ruta: Path) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS)
        w.writeheader()
        for c in sorted(ciclos, key=lambda c: (c.periodo != "pre",
                                                int(c.ciclo[2:]) if c.ciclo[2:].isdigit() else 0)):
            w.writerow(c.como_fila())


def leer_marcas(ruta: Path) -> dict[tuple[str, str], frozenset[str]]:
    """Lee marcas_sensibilidad.csv: columnas periodo, ciclo, marca (una por fila;
    un ciclo puede repetirse con varias marcas)."""
    salida: dict[tuple[str, str], set[str]] = {}
    with Path(ruta).open(encoding="utf-8-sig", newline="") as fh:
        for f in csv.DictReader(fh):
            ciclo = (f.get("ciclo") or "").strip()
            if not ciclo:
                continue
            clave = ((f.get("periodo") or "").strip().lower(), ciclo)
            salida.setdefault(clave, set()).add((f.get("marca") or "").strip())
    return {k: frozenset(v) for k, v in salida.items()}


def marcas_sin_ciclo(marcas: dict[tuple[str, str], frozenset[str]],
                     ciclos: list[Ciclo]) -> list[str]:
    """Marcas que apuntan a un ciclo que no existe (p. ej. 'PT?' sin completar).
    Si no se detectan, el análisis de sensibilidad excluiría menos ciclos de
    los declarados sin avisar."""
    existentes = {(c.periodo, c.ciclo) for c in ciclos}
    return [f"{p}/{c}: la marca apunta a un ciclo inexistente ({', '.join(sorted(m))})."
            for (p, c), m in sorted(marcas.items()) if (p, c) not in existentes]


def desde_tabla_ancha(ruta_ancha: Path,
                      marcas: dict[tuple[str, str], frozenset[str]]) -> list[Ciclo]:
    """Convierte la exportación ancha de 'Datos pre' / 'Datos post'
    (resultados_documento_60ciclos.csv) al formato largo.

    El número de fila N se usa solo para nombrar CPN y PTN; las dos filas NO se
    tratan como un par.
    """
    with Path(ruta_ancha).open(encoding="utf-8-sig", newline="") as fh:
        filas = [f for f in csv.DictReader(fh) if (f.get("ciclo") or "").strip()]
    ciclos: list[Ciclo] = []
    for f in filas:
        n = _entero(f, "ciclo")
        for periodo, prefijo in (("pre", "CP"), ("post", "PT")):


            original = (f.get(f"id_{periodo}") or "").strip().upper()
            codigo = original if _PATRON_ID[periodo].match(original) else f"{prefijo}{n}"
            ciclos.append(Ciclo(
                periodo=periodo, ciclo=codigo,
                situaciones_identificadas=_entero(f, f"situaciones_identificadas_{periodo}"),
                situaciones_cubiertas=_entero(f, f"situaciones_cubiertas_{periodo}"),
                casos_especificados=_entero(f, f"casos_especificados_{periodo}"),
                casos_ejecutados=_entero(f, f"casos_ejecutados_{periodo}"),
                defectos_detectados=_entero(f, f"defectos_detectados_{periodo}"),
                defectos_corregidos=_entero(f, f"defectos_corregidos_{periodo}"),
                detectados_por_severidad={s: _entero(f, f"det_{s}_{periodo}")
                                          for s in SEVERIDADES},
                corregidos_por_severidad={s: _entero(f, f"corr_{s}_{periodo}")
                                          for s in SEVERIDADES},
                marcas=marcas.get((periodo, codigo), frozenset()),
            ))
    return ciclos
