"""
Índice de cobertura REAL de criterios de aceptación, Sin IA vs Con IA
(NEXUS Pre-Test/Post-Test, la celda que faltaba — 2026-09-06).

Qué calcula y por qué es distinto de lo que ya había
-----------------------------------------------------
`retro_resultado_57hu.csv` trae `indice_cobertura_*_pct`, pero eso es
`casos / criterios × 100` — **densidad**, no cobertura: llega a 600% y no dice
qué criterios quedaron cubiertos. Este script calcula la cobertura de verdad:

    criterios cubiertos por al menos un test / criterios identificados × 100

acotada a 0–100, con la lista de los criterios que quedaron sin cubrir. Usa
`LLMProvider.clasificar_cobertura_criterios()`, la misma pieza que ya usa
Seguimiento (`application/seguimiento/motor.py`) para su
`indice_cobertura_real_pct`. No se inventa métrica ni prompt: se reusa la
lógica ya validada del proyecto, aplicada por primera vez al corpus del
análisis retrospectivo y, sobre todo, **a los dos lados**.

Los dos lados
-------------
- **Sin IA**: los test cases históricos reales, con su Gherkin, de
  `historico_gherkin_texto_57hu.csv`.
- **Con IA**: los casos del agente que **sobrevivieron a la revisión humana**
  (`estado_final == "aprobado"` en `revision_manual_retrospectiva_test_cases.csv`),
  usando `gherkin_final`.

Por qué solo los aprobados: contar los 51 rechazados sería acreditarle al
agente cobertura que un humano descartó. Sobre los aprobados el número es más
chico y es defendible. Dato relevante: en esa revisión hubo 0 casos editados,
así que `gherkin_final` de un aprobado es la salida del agente sin retocar —
la comparación no se contamina con correcciones humanas.

Por qué la comparación es justa aunque el juez sea un LLM
----------------------------------------------------------
El prompt de `clasificar_cobertura_criterios()` recibe "criterios" y "test
cases existentes" y **nada más**: no sabe, ni puede saber, si los tests que
está evaluando los escribió una persona o un agente. Los dos lados se juzgan
con el mismo modelo, el mismo prompt y el mismo criterio de estrictez. Si el
juez tuviera un sesgo, lo aplicaría por igual a ambos: el número absoluto
podría correrse, pero **la comparación se sostiene**. El modelo usado queda
registrado en la salida.

Costo
-----
2 llamadas por HU (una por lado). El corpus tiene 40 HU con las tres piezas
completas → **80 llamadas**. Se puede probar con pocas primero: `--limite 3`.
Resumible: si se corta, correr de nuevo retoma sin repetir lo ya calculado.

Manejo de errores (lección cara del 2026-09-06)
------------------------------------------------
Reintentar a ciegas cuesta dinero: cada reintento es una llamada facturada.
Acá los fallos se clasifican — saldo agotado o credenciales **abortan la
corrida entera** al primer intento; un fallo de parseo se saltea sin repetir
la llamada; solo rate-limit y cortes de red se reintentan con espera.

Entradas (raíz del proyecto):
    criterios_aceptacion_retro.csv             criterios por HU
    historico_gherkin_texto_57hu.csv             casos del humano
    revision_manual_retrospectiva_test_cases.csv casos del agente + veredicto

Salida (raíz del proyecto):
    cobertura_real_retro.csv

Uso (desde la raíz del proyecto, con el venv activado):

    python scripts\\calcular_cobertura_real_retro.py --limite 3   # prueba
    python scripts\\calcular_cobertura_real_retro.py              # completo
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from application.seguimiento.corpus_retro import ampliar
from infrastructure.config import obtener_logger
from infrastructure.fabrica_llm import crear_llm_provider

_log = obtener_logger(__name__)

_ARCHIVO_CRITERIOS = Path("criterios_aceptacion_retro.csv")
_ARCHIVO_HISTORICO = Path("historico_gherkin_texto_57hu.csv")


_ARCHIVOS_HISTORICO_EXTRA = [Path("historico_gherkin_texto_septiembre.csv")]
_ARCHIVO_AGENTE = Path("revision_manual_retrospectiva_test_cases.csv")
_ARCHIVO_CORPUS = Path("retro") / "retro_resultado_57hu.csv"
_ARCHIVO_SALIDA = Path("cobertura_real_retro.csv")

_SEPARADOR_CRITERIOS = "||"
_MAX_REINTENTOS = 3
_ESPERA_INICIAL_SEGUNDOS = 3.0
_ESPERA_ENTRE_LLAMADAS_SEGUNDOS = 0.5

_COLUMNAS = [
    "hu_key", "criterios_total",
    "casos_sin_ia", "cubiertos_sin_ia", "cobertura_sin_ia_pct", "no_cubiertos_sin_ia",
    "casos_con_ia", "cubiertos_con_ia", "cobertura_con_ia_pct", "no_cubiertos_con_ia",
    "delta_pts", "modelo_juez",
]


class AbortarCorrida(Exception):
    """Saldo agotado / credenciales: seguir es gastar sin poder obtener nada."""


def _leer(nombre: Path) -> list[dict]:
    if not nombre.exists():
        raise SystemExit(f"Falta {nombre.resolve()}.")
    with nombre.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _criterios_por_hu() -> dict[str, list[str]]:
    salida: dict[str, list[str]] = {}
    for fila in _leer(_ARCHIVO_CRITERIOS):
        crudos = (fila.get("criterios_texto") or "").split(_SEPARADOR_CRITERIOS)
        criterios = [c.strip() for c in crudos if c.strip()]
        if criterios:
            salida[fila["hu_key"]] = criterios
    return salida


def _casos_humano() -> dict[str, list[dict]]:
    por_hu: dict[str, list[dict]] = defaultdict(list)
    filas = list(_leer(_ARCHIVO_HISTORICO))
    for extra in _ARCHIVOS_HISTORICO_EXTRA:
        if extra.exists():
            with extra.open("r", newline="", encoding="utf-8") as f:
                nuevas = list(csv.DictReader(f))
            print(f"  + {len(nuevas)} filas de {extra.name}")
            filas += nuevas
    for fila in filas:
        titulo = (fila.get("test_summary") or "").strip()
        if not titulo:
            continue
        por_hu[fila["hu_key"]].append(
            {"titulo": titulo, "gherkin": (fila.get("gherkin_texto") or "").strip()}
        )
    return dict(por_hu)


def _casos_agente() -> dict[str, list[dict]]:
    """Solo los APROBADOS en la revisión humana (ver docstring del módulo)."""
    por_hu: dict[str, list[dict]] = defaultdict(list)
    for fila in _leer(_ARCHIVO_AGENTE):
        if (fila.get("estado_final") or "").strip().lower() != "aprobado":
            continue
        titulo = (fila.get("titulo") or "").strip()
        if not titulo:
            continue
        por_hu[fila["hu_key"]].append(
            {"titulo": titulo, "gherkin": (fila.get("gherkin_final") or "").strip()}
        )
    return dict(por_hu)


def _clasificar_error(exc: Exception) -> str:
    nombre = type(exc).__name__
    mensaje = str(exc).lower()
    if "credit balance" in mensaje or "billing" in mensaje:
        return "abortar"
    if nombre in ("AuthenticationError", "PermissionDeniedError", "NotFoundError", "BadRequestError"):
        return "abortar"
    if nombre in ("AttributeError", "TypeError", "KeyError", "IndexError", "ValueError"):
        return "saltear"
    return "reintentar"


def _cobertura(provider, criterios: list[str], tests: list[dict]) -> tuple[int, list[str]]:
    """Devuelve (cuántos criterios quedaron cubiertos, lista de los no cubiertos)."""
    espera = _ESPERA_INICIAL_SEGUNDOS
    ultimo: Exception | None = None
    for intento in range(1, _MAX_REINTENTOS + 1):
        try:
            clasificacion = provider.clasificar_cobertura_criterios(criterios, tests)
            cubiertos = sum(1 for c in clasificacion if c.get("cubierto"))
            no_cubiertos = [c.get("criterio", "") for c in clasificacion if not c.get("cubierto")]
            return cubiertos, no_cubiertos
        except Exception as exc:
            ultimo = exc
            accion = _clasificar_error(exc)
            if accion == "abortar":
                raise AbortarCorrida(f"{type(exc).__name__}: {exc}") from exc
            if accion == "saltear":
                print(f"      fallo no reintentable ({exc!r}) -- se saltea sin repetir la llamada.")
                break
            print(f"      fallo transitorio (intento {intento}/{_MAX_REINTENTOS}): {exc!r}")
            if intento < _MAX_REINTENTOS:
                time.sleep(espera)
                espera *= 2
    raise RuntimeError(f"cobertura no calculada: {ultimo!r}") from ultimo


def _guardar(filas: dict[str, list], orden: list[str]) -> None:
    with _ARCHIVO_SALIDA.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_COLUMNAS)
        for hu in orden:
            if hu in filas:
                writer.writerow(filas[hu])


def main() -> None:
    parser = argparse.ArgumentParser(description="Cobertura real de criterios, Sin IA vs Con IA.")
    parser.add_argument("--limite", type=int, default=0,
                        help="Procesar solo las primeras N HU pendientes (para probar barato).")
    args = parser.parse_args()

    criterios_por_hu = _criterios_por_hu()
    humano = _casos_humano()
    agente = _casos_agente()


    corpus = ampliar([f["hu_key"] for f in _leer(_ARCHIVO_CORPUS)])

    comparables = [
        hu for hu in corpus
        if criterios_por_hu.get(hu) and humano.get(hu) and agente.get(hu)
    ]
    print(f"Corpus: {len(corpus)} HU. Con criterios + casos de AMBOS lados: {len(comparables)}.")
    sin_datos = [hu for hu in corpus if hu not in comparables]
    if sin_datos:
        print(f"  Quedan fuera (falta alguna de las tres piezas): {sin_datos}")

    ya: dict[str, list] = {}
    if _ARCHIVO_SALIDA.exists():
        with _ARCHIVO_SALIDA.open("r", newline="", encoding="utf-8") as f:
            lector = csv.reader(f)
            next(lector, None)
            for fila in lector:
                if fila and len(fila) >= len(_COLUMNAS):
                    ya[fila[0]] = fila
        if ya:
            print(f"Salida previa con {len(ya)} HU ya calculadas -- se retoma.")


    fuera = [hu for hu in ya if hu not in comparables]
    for hu in fuera:
        del ya[hu]
    if fuera:
        print(f"  {len(fuera)} HU dejaron de ser comparables y salen del cálculo: {fuera}")


    idx = {c: _COLUMNAS.index(c) for c in ("criterios_total", "casos_sin_ia", "casos_con_ia")}
    def _actual(hu: str) -> tuple[int, int, int]:
        return (len(criterios_por_hu[hu]), len(humano[hu]), len(agente[hu]))
    def _guardado(fila: list) -> tuple[int, int, int]:
        return tuple(int(fila[idx[c]]) for c in
                     ("criterios_total", "casos_sin_ia", "casos_con_ia"))
    desactualizadas = [hu for hu, fila in ya.items() if _guardado(fila) != _actual(hu)]
    for hu in desactualizadas:
        del ya[hu]
    if desactualizadas:
        print(f"  {len(desactualizadas)} HU cambiaron de entradas (criterios o casos) "
              f"desde que se calcularon -- se recalculan: {desactualizadas}")

    pendientes = [hu for hu in comparables if hu not in ya]
    if args.limite:
        pendientes = pendientes[:args.limite]
        print(f"--limite {args.limite}: se procesan solo {len(pendientes)} HU en esta corrida.")
    if not pendientes:
        print("Nada pendiente.")
    else:
        print(f"{len(pendientes)} HU pendientes = {len(pendientes) * 2} llamadas al LLM.\n")

    provider = crear_llm_provider() if pendientes else None
    modelo = getattr(provider, "_modelo", "") or ""

    for i, hu in enumerate(pendientes, start=1):
        criterios = criterios_por_hu[hu]
        tests_h = humano[hu]
        tests_a = agente[hu]
        print(f"  [{i}/{len(pendientes)}] {hu}: {len(criterios)} criterios | "
              f"{len(tests_h)} casos humano, {len(tests_a)} casos agente")
        try:
            cub_h, no_h = _cobertura(provider, criterios, tests_h)
            time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
            cub_a, no_a = _cobertura(provider, criterios, tests_a)
        except AbortarCorrida as exc:
            print(
                f"\n*** CORRIDA ABORTADA: {exc}\n"
                "    No se hace ni una llamada más. Lo ya calculado quedó guardado y "
                "la próxima corrida retoma desde ahí."
            )
            break
        except RuntimeError as exc:
            print(f"      se deja pendiente: {exc}")
            continue

        total = len(criterios)
        pct_h = round(cub_h / total * 100, 1)
        pct_a = round(cub_a / total * 100, 1)
        print(f"      Sin IA {pct_h}%  |  Con IA {pct_a}%  |  Δ {pct_a - pct_h:+.1f} pts")
        ya[hu] = [
            hu, total,
            len(tests_h), cub_h, pct_h, " || ".join(no_h),
            len(tests_a), cub_a, pct_a, " || ".join(no_a),
            round(pct_a - pct_h, 1), modelo,
        ]
        _guardar(ya, comparables)
        time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)

    _guardar(ya, comparables)
    print(f"\nListo. {_ARCHIVO_SALIDA.resolve()}")
    _resumen(ya, len(comparables))


def _resumen(filas: dict[str, list], total_comparables: int) -> None:
    if not filas:
        print("Todavía no hay ninguna HU calculada.")
        return
    idx_tot = _COLUMNAS.index("criterios_total")
    idx_ch = _COLUMNAS.index("cubiertos_sin_ia")
    idx_ca = _COLUMNAS.index("cubiertos_con_ia")

    criterios = sum(int(f[idx_tot]) for f in filas.values())
    cub_h = sum(int(f[idx_ch]) for f in filas.values())
    cub_a = sum(int(f[idx_ca]) for f in filas.values())

    print(f"\n=== Índice de cobertura de pruebas ({len(filas)} de {total_comparables} HU) ===")
    print(f"  criterios de aceptación evaluados: {criterios}")
    print(f"  Sin IA: {cub_h}/{criterios} = {cub_h / criterios * 100:.1f}%")
    print(f"  Con IA: {cub_a}/{criterios} = {cub_a / criterios * 100:.1f}%")
    print(f"  Δ: {(cub_a - cub_h) / criterios * 100:+.1f} pts")

    idx_delta = _COLUMNAS.index("delta_pts")
    idx_casos_h = _COLUMNAS.index("casos_sin_ia")
    idx_pct_h = _COLUMNAS.index("cobertura_sin_ia_pct")

    mejor = sum(1 for f in filas.values() if float(f[idx_delta]) > 0)
    igual = sum(1 for f in filas.values() if float(f[idx_delta]) == 0)
    print(f"  HU donde el agente cubre más: {mejor} | igual: {igual} | menos: {len(filas) - mejor - igual}")


    techo = [f for f in filas.values() if float(f[idx_pct_h]) >= 100.0]
    if techo:
        empatan = sum(1 for f in techo if float(f[idx_delta]) == 0)
        print(
            f"\n  HU donde el humano YA cubría el 100%: {len(techo)} "
            f"(el agente no puede mejorarlas; empata en {empatan})"
        )

    flacas = [f for f in filas.values() if int(f[idx_casos_h]) <= 2]
    gruesas = [f for f in filas.values() if int(f[idx_casos_h]) > 2]
    print("\n  Ganancia según cuántos casos había escrito el humano:")
    for etiqueta, grupo in (("<= 2 casos", flacas), ("> 2 casos", gruesas)):
        if not grupo:
            continue
        crit = sum(int(f[idx_tot]) for f in grupo)
        ch = sum(int(f[idx_ch]) for f in grupo)
        ca = sum(int(f[idx_ca]) for f in grupo)
        print(
            f"    {etiqueta:<12} n={len(grupo):<3} Sin IA {ch / crit * 100:5.1f}%  "
            f"Con IA {ca / crit * 100:5.1f}%  Δ {(ca - ch) / crit * 100:+6.1f} pts"
        )
    print(
        "    ^ Si la ganancia se concentra en el primer grupo, lo honesto es decir "
        "que el agente\n      es sistemático donde el proceso manual fue escaso, no "
        "que entiende mejor los criterios."
    )

    if len(filas) < total_comparables:
        print(
            f"\n  PARCIAL: faltan {total_comparables - len(filas)} HU. "
            "El número final sale con el corpus completo."
        )
    print(
        "\n  Recordatorio: los dos lados se juzgaron con el mismo modelo y el mismo "
        "prompt, que NO sabe cuál lado está evaluando. Validá a mano unas cuantas "
        "HU (sobre todo las de mayor Δ) antes de citar el número."
    )


if __name__ == "__main__":
    main()
