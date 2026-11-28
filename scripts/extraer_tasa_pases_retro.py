"""
Tasa de pases del corpus Pre-Test (2026-09-07).

Qué es y por qué falta
----------------------
El cuarto indicador de Seguimiento --junto a índice de ejecución, cobertura y
estado de defectos-- es la **tasa de pases**: de los test runs que llegaron a
un estado final, cuántos pasaron.

    tasa de pases = PASSED / (PASSED + FAILED) × 100

`application/seguimiento/motor.py` ya lo calcula en vivo (`test_pass_rate_pct`),
pero nunca se corrió sobre el corpus del análisis retrospectivo, así que el dashboard
Pre-Test/Post-Test no lo tiene. Este script llena ese hueco.

Qué NO es
---------
No tiene lado Post-Test, y no se le va a inventar uno. La corrida exploratoria utilizó `RepositoryNulo`, sin publicar sus casos en
Xray; este corpus no aporta runs Post-Test que puedan pasar o fallar. No se
refiere a las ejecuciones humanas del flujo operativo. Es un indicador que **caracteriza la línea base manual**: dice qué tan
sana estaba la ejecución histórica contra la que se compara todo lo demás.

Vale la pena tenerlo igual, porque contextualiza el índice de ejecución. Un
98,9% de ejecución con una tasa de pases baja significa "se ejecutó casi todo
y falló mucho", que es una historia muy distinta de "se ejecutó casi todo y
pasó casi todo".

Reusa el motor, no lo reimplementa
-----------------------------------
La autenticación de Xray, la query de test plan, el criterio de estado final y
la resolución de IDs internos salen todos de `application/seguimiento/motor.py`.
Duplicar esa lógica acá sería una cuarta copia que se desincroniza, el mismo
problema que ya hubo con `contar_criterios()`.

**No usa LLM.** Solo Xray + Jira: sin costo de API de modelos.

Entrada (raíz del proyecto):
    retro_resultado_57hu.csv   -- corpus y test_plan_key de cada HU

Salida (raíz del proyecto):
    tasa_pases_retro.csv
        hu_key, test_plan_key, runs_total, runs_finalizados, runs_pass,
        runs_fail, tasa_pases_pct

Resumible: si se corta, correr de nuevo retoma donde quedó.

Uso (desde la raíz del proyecto, con el venv activado):

    python scripts\\extraer_tasa_pases_retro.py
    python scripts\\extraer_tasa_pases_retro.py --limite 3
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from application.seguimiento.motor import (
    _ESTADOS_FINALES,
    _autenticar_xray,
    _consultar_test_plan,
    _resolver_ids_internos,
)
from infrastructure.config import cargar_configuracion_jira, cargar_configuracion_xray

_ARCHIVO_ENTRADA = Path("retro_resultado_57hu.csv")
_ARCHIVO_SALIDA = Path("tasa_pases_retro.csv")
_COLUMNAS = ["hu_key", "test_plan_key", "runs_total", "runs_finalizados",
             "runs_pass", "runs_fail", "tasa_pases_pct"]
_ESPERA = 0.3


def _leer_corpus() -> list[tuple[str, str]]:
    if not _ARCHIVO_ENTRADA.exists():
        raise SystemExit(f"Falta {_ARCHIVO_ENTRADA.resolve()}.")
    with _ARCHIVO_ENTRADA.open("r", newline="", encoding="utf-8") as f:
        return [(x["hu_key"], (x.get("test_plan_key") or "").strip())
                for x in csv.DictReader(f)]


def _contar_runs(test_plan: dict) -> tuple[int, int, int, int]:
    """(total, finalizados, pass, fail) de todos los runs del test plan."""
    total = finalizados = pasados = fallados = 0
    for ejecucion in (test_plan.get("testExecutions") or {}).get("results", []) or []:
        for run in (ejecucion.get("testRuns") or {}).get("results", []) or []:
            total += 1
            estado = (run.get("status") or {}).get("name")
            if estado in _ESTADOS_FINALES:
                finalizados += 1
                if estado == "PASSED":
                    pasados += 1
                else:
                    fallados += 1
    return total, finalizados, pasados, fallados


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tasa de pases del corpus Pre-Test. Solo Xray/Jira, sin costo de LLM."
    )
    parser.add_argument("--limite", type=int, default=0,
                        help="Procesar solo las primeras N HU pendientes (para probar).")
    args = parser.parse_args()

    corpus = _leer_corpus()
    print(f"{len(corpus)} HU en el corpus. Solo Xray y Jira: sin costo de modelos.")

    ya: dict[str, list] = {}
    if _ARCHIVO_SALIDA.exists():
        with _ARCHIVO_SALIDA.open("r", newline="", encoding="utf-8") as f:
            lector = csv.reader(f)
            next(lector, None)
            for fila in lector:
                if fila:
                    ya[fila[0]] = fila
        print(f"Salida previa con {len(ya)} HU -- se retoma.")

    def _guardar() -> None:
        with _ARCHIVO_SALIDA.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(_COLUMNAS)
            for clave, _ in corpus:
                if clave in ya:
                    w.writerow(ya[clave])

    pendientes = [(h, tp) for h, tp in corpus if h not in ya]
    sin_plan = [h for h, tp in pendientes if not tp]
    if sin_plan:
        print(f"  {len(sin_plan)} HU sin test_plan_key: no se pueden consultar ({sin_plan}).")
    pendientes = [(h, tp) for h, tp in pendientes if tp]
    if args.limite:
        pendientes = pendientes[:args.limite]
        print(f"--limite {args.limite}: se procesan {len(pendientes)} HU en esta corrida.")
    if not pendientes:
        print("Nada pendiente.")
        _guardar()
        _resumen(ya)
        return

    cfg_jira = cargar_configuracion_jira()
    cfg_xray = cargar_configuracion_xray()
    errores: list[str] = []

    with httpx.Client(timeout=60.0, auth=(cfg_jira.email, cfg_jira.api_token)) as cliente_jira:
        ids = _resolver_ids_internos(
            cliente_jira, cfg_jira.base_url, [tp for _, tp in pendientes]
        )
    faltan_id = [tp for _, tp in pendientes if tp not in ids]
    if faltan_id:
        print(f"  {len(faltan_id)} test plan(s) sin ID interno resoluble: {faltan_id}")

    with httpx.Client(timeout=60.0) as cliente:
        token = _autenticar_xray(cliente, cfg_xray.client_id, cfg_xray.client_secret)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        for i, (clave, tp_key) in enumerate(pendientes, start=1):
            issue_id = ids.get(tp_key)
            if not issue_id:
                errores.append(clave)
                continue
            try:
                plan = _consultar_test_plan(cliente, headers, issue_id)
            except Exception as exc:
                print(f"  [{i}/{len(pendientes)}] {clave}: ERROR ({exc!r})")
                errores.append(clave)
                continue
            if not plan:
                print(f"  [{i}/{len(pendientes)}] {clave}: el test plan {tp_key} vino vacío.")
                errores.append(clave)
                continue

            total, fin, ok, mal = _contar_runs(plan)
            tasa = round(ok / fin * 100, 1) if fin else ""
            print(f"  [{i}/{len(pendientes)}] {clave:<14} {tp_key:<14} "
                  f"runs={total:>3} finalizados={fin:>3} pass={ok:>3} fail={mal:>3} "
                  f"tasa={tasa if tasa != '' else '—'}")
            ya[clave] = [clave, tp_key, total, fin, ok, mal, tasa]
            _guardar()
            time.sleep(_ESPERA)

    _guardar()
    print(f"\nListo. {_ARCHIVO_SALIDA.resolve()}")
    if errores:
        print(f"AVISO: {len(errores)} HU no se pudieron consultar: {errores}")
    _resumen(ya)


def _resumen(filas: dict[str, list]) -> None:
    if not filas:
        print("Todavía no hay ninguna HU calculada.")
        return
    fin = sum(int(f[3] or 0) for f in filas.values())
    ok = sum(int(f[4] or 0) for f in filas.values())
    mal = sum(int(f[5] or 0) for f in filas.values())
    total = sum(int(f[2] or 0) for f in filas.values())
    print(f"\n=== Tasa de pases ({len(filas)} HU) ===")
    print(f"  test runs totales      : {total}")
    print(f"  con estado final       : {fin}  ({fin / total * 100:.1f}% de los runs)"
          if total else "  con estado final       : 0")
    if not fin:
        print("  Sin runs finalizados: no hay tasa de pases que calcular.")
        return
    print(f"  PASSED                 : {ok}")
    print(f"  FAILED                 : {mal}")
    print(f"  TASA DE PASES          : {ok / fin * 100:.1f}%")
    con_fallos = [f[0] for f in filas.values() if int(f[5] or 0) > 0]
    print(f"  HU con al menos un FAILED: {len(con_fallos)} de {len(filas)}")
    if con_fallos:
        print(f"    {sorted(con_fallos)}")
    print(
        "\n  Cómo leerlo: esto describe la LÍNEA BASE MANUAL, no al agente. No tiene "
        "lado Post-Test y no se le inventa uno: los casos del agente nunca se "
        "ejecutaron en Xray. Sirve para contextualizar el índice de ejecución -- "
        "ejecutar casi todo y que pase casi todo es una historia distinta de "
        "ejecutar casi todo y que falle mucho."
    )


if __name__ == "__main__":
    main()
