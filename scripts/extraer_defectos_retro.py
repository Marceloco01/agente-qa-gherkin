"""
Análisis retrospectivo (tesis) — Estado de defectos históricos por HU.

Xray Cloud confirma que `TestRun.defects: LIST<String>` existe en esta
instancia desde la exploración real de la GraphQL API (ver
`explorar_xray_graphql.py` y la sección "Primeros datos reales de Xray
GraphQL" en la documentación del proyecto) -- pero ninguna extracción real
hecha hasta ahora (`verificar_test_plans_85hu.py`,
`extraer_gherkin_historico_pilot10.py`, `extraer_gherkin_historico_57hu.py`)
pidió ese campo: todas se quedaron en `testRuns { status { name } }`. Este
script agrega `defects` a la misma query ya verificada, para las 43 HU que
quedaron dentro del análisis final del análisis retrospectivo (no las 57 -- no tiene
sentido gastar llamadas en HU ya excluidas del corpus).

Mismo patrón ya verificado en el resto del proyecto: autenticación real
contra Xray Cloud, resolución de IDs internos de Jira en un solo lote,
reintento con espera creciente ante 429/502/503/504, escritura incremental y
resumible.

Entrada (ya generada por corridas reales previas, en la carpeta actual):
    retro_resultado_57hu.csv -- trae hu_key + test_plan_key de las 43 HU.

Salida (en la carpeta actual):
    defectos_historico_retro.csv
        Una fila por HU: hu_key, test_plan_key, num_test_runs,
        num_runs_con_defecto, indice_defectos_pct (runs con >=1 defecto
        sobre el total de runs), defectos_unicos (keys de defecto separadas
        por ";", vacío si ninguno).

Uso (desde la raíz del proyecto, con el venv activado):

    python scripts\\extraer_defectos_retro.py

Si se corta por rate-limit a mitad de camino, correr de nuevo el mismo
comando retoma donde quedó.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from infrastructure.config import cargar_configuracion_jira, cargar_configuracion_xray

_MAX_REINTENTOS = 6
_ESPERA_INICIAL_SEGUNDOS = 3.0
_ESPERA_ENTRE_LLAMADAS_SEGUNDOS = 0.8

_URL_AUTENTICACION = "https://xray.cloud.getxray.app/api/v2/authenticate"
_URL_GRAPHQL = "https://xray.cloud.getxray.app/api/v2/graphql"

_ARCHIVO_ENTRADA = Path("retro_resultado_57hu.csv")
_ARCHIVO_SALIDA = Path("defectos_historico_retro.csv")

_COLUMNAS_SALIDA = [
    "hu_key", "test_plan_key", "num_test_runs", "num_runs_con_defecto",
    "indice_defectos_pct", "defectos_unicos",
]

_QUERY_TEST_PLAN_DEFECTOS = """
query($issueId: String) {
  getTestPlan(issueId: $issueId) {
    issueId
    testExecutions(limit: 100) {
      results {
        issueId
        testRuns(limit: 100) {
          results {
            status { name }
            defects
          }
        }
      }
    }
  }
}
"""


def _autenticar(cliente: httpx.Client, client_id: str, client_secret: str) -> str:
    resp = cliente.post(_URL_AUTENTICACION, json={"client_id": client_id, "client_secret": client_secret})
    resp.raise_for_status()
    return resp.json()


def _post_con_reintentos(cliente: httpx.Client, url: str, **kwargs) -> httpx.Response:
    espera = _ESPERA_INICIAL_SEGUNDOS
    for intento in range(1, _MAX_REINTENTOS + 1):
        resp = cliente.post(url, **kwargs)
        if resp.status_code not in (429, 502, 503, 504):
            return resp
        retry_after = resp.headers.get("Retry-After")
        segundos_espera = float(retry_after) if retry_after else espera
        print(
            f"    Xray respondió {resp.status_code}. Esperando {segundos_espera:.1f}s "
            f"antes de reintentar (intento {intento}/{_MAX_REINTENTOS})..."
        )
        time.sleep(segundos_espera)
        espera *= 2
    return resp


def _resolver_ids_internos(keys_test_plan: list[str]) -> dict[str, str]:
    config = cargar_configuracion_jira()
    resultado: dict[str, str] = {}
    for i in range(0, len(keys_test_plan), 40):
        lote = keys_test_plan[i:i + 40]
        jql = "key in (" + ", ".join(lote) + ")"
        with httpx.Client(auth=(config.email, config.api_token), timeout=60.0, headers={"Accept": "application/json"}) as cliente:
            resp = cliente.post(
                f"{config.base_url}/rest/api/3/search/jql",
                json={"jql": jql, "maxResults": 100, "fields": []},
            )
            resp.raise_for_status()
            data = resp.json()
        for issue in data.get("issues", []):
            resultado[issue["key"]] = issue["id"]
    return resultado


def _leer_entrada() -> list[tuple[str, str]]:
    if not _ARCHIVO_ENTRADA.exists():
        raise SystemExit(
            f"No se encontró {_ARCHIVO_ENTRADA.resolve()} -- copiá ahí el CSV "
            "entregado (retro_resultado_57hu.csv) antes de correr este script."
        )
    with _ARCHIVO_ENTRADA.open("r", newline="", encoding="utf-8") as f:
        return [(fila["hu_key"], fila["test_plan_key"]) for fila in csv.DictReader(f)]


def main() -> None:
    config_xray = cargar_configuracion_xray()
    pares_hu_test_plan = _leer_entrada()
    print(f"{len(pares_hu_test_plan)} HU a procesar (leídas de {_ARCHIVO_ENTRADA}).")

    ya_resueltas: dict[str, list] = {}
    if _ARCHIVO_SALIDA.exists():
        with _ARCHIVO_SALIDA.open("r", newline="", encoding="utf-8") as f:
            lector = csv.reader(f)
            next(lector, None)
            for fila in lector:
                if fila:
                    ya_resueltas[fila[0]] = fila
        print(f"Se encontró una salida previa con {len(ya_resueltas)} HU ya procesadas -- se retoma.")

    def _guardar() -> None:
        with _ARCHIVO_SALIDA.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_COLUMNAS_SALIDA)
            for hu_key, _ in pares_hu_test_plan:
                if hu_key in ya_resueltas:
                    writer.writerow(ya_resueltas[hu_key])

    pendientes = [(hu, tp) for hu, tp in pares_hu_test_plan if hu not in ya_resueltas]
    if not pendientes:
        print("Nada pendiente -- todas las HU ya tienen defectos extraídos.")
        _guardar()
        return

    keys_test_plan_unicas = sorted({tp for _, tp in pendientes})

    with httpx.Client(timeout=60.0) as cliente:
        print("\nAutenticando contra Xray Cloud...")
        token = _autenticar(cliente, config_xray.client_id, config_xray.client_secret)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        print(f"\nResolviendo IDs internos de Jira de {len(keys_test_plan_unicas)} Test Plan...")
        mapa_ids_internos = _resolver_ids_internos(keys_test_plan_unicas)
        faltantes = set(keys_test_plan_unicas) - set(mapa_ids_internos.keys())
        if faltantes:
            print(f"  AVISO: no se resolvió el ID interno de: {sorted(faltantes)}")

        for i, (hu_key, tp_key) in enumerate(pendientes, start=1):
            id_interno = mapa_ids_internos.get(tp_key)
            if id_interno is None:
                ya_resueltas[hu_key] = [hu_key, tp_key, "ERROR", "ERROR", "", "sin ID interno"]
                _guardar()
                continue

            print(f"  [{i}/{len(pendientes)}] {hu_key} -> Test Plan {tp_key} (id interno {id_interno})...")
            resp = _post_con_reintentos(
                cliente, _URL_GRAPHQL, headers=headers,
                json={"query": _QUERY_TEST_PLAN_DEFECTOS, "variables": {"issueId": id_interno}},
            )
            if resp.status_code >= 400:
                print(f"    ERROR HTTP {resp.status_code} persistente: {resp.text[:300]}")
                ya_resueltas[hu_key] = [hu_key, tp_key, "ERROR", "ERROR", "", f"HTTP {resp.status_code}"]
                _guardar()
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
                continue

            datos = resp.json()
            if "errors" in datos:
                print(f"    ERROR de GraphQL: {datos['errors']}")
                ya_resueltas[hu_key] = [hu_key, tp_key, "ERROR", "ERROR", "", str(datos["errors"])[:200]]
                _guardar()
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
                continue

            test_plan = datos["data"]["getTestPlan"]
            if test_plan is None:
                ya_resueltas[hu_key] = [hu_key, tp_key, "ERROR", "ERROR", "", "getTestPlan devolvió null"]
                _guardar()
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
                continue

            runs_totales = 0
            runs_con_defecto = 0
            defectos_unicos: set[str] = set()
            for ejecucion in test_plan.get("testExecutions", {}).get("results", []) or []:
                for run in ejecucion.get("testRuns", {}).get("results", []) or []:
                    runs_totales += 1
                    defectos_run = run.get("defects") or []
                    if defectos_run:
                        runs_con_defecto += 1
                        defectos_unicos.update(defectos_run)

            indice_defectos = round(runs_con_defecto / runs_totales * 100, 1) if runs_totales else 0.0
            ya_resueltas[hu_key] = [
                hu_key, tp_key, runs_totales, runs_con_defecto,
                indice_defectos, ";".join(sorted(defectos_unicos)),
            ]
            _guardar()
            time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)

    print(f"\nListo. {_ARCHIVO_SALIDA.resolve()}")
    con_defectos = sum(1 for fila in ya_resueltas.values() if fila[3] not in ("ERROR", 0, "0") and int(fila[3] or 0) > 0)
    print(f"{con_defectos} de {len(ya_resueltas)} HU tuvieron al menos un Test Run con defecto registrado.")


if __name__ == "__main__":
    main()
