"""
NEXUS Pre-Test/Post-Test — qué caso de prueba manual detectó cada defecto
(2026-09-06).

Por qué existe
--------------
`extraer_defectos_retro.py` recorre `getTestPlan -> testExecutions ->
testRuns` y se queda solo con el AGREGADO por HU (cuántos runs, cuántos con
defecto, y el set de IDs de defecto). En el camino tira la información más
valiosa que ya venía en la misma respuesta: **de qué Test Run salió cada
defecto**, y por lo tanto **qué caso de prueba manual lo detectó**.

Ese dato es el que hace falta para el análisis de evitabilidad acordado con
el usuario (2026-09-06): por cada defecto real, decidir si un caso generado
por el agente lo habría detectado o si se iba a dar igual. Juzgar eso solo
con el título del defecto es débil -- saber los pasos exactos que lo
dispararon (el caso manual que lo encontró) hace el juicio mucho más
confiable. Por eso este script re-recorre los mismos Test Plans, pero
conservando el enlace `defecto -> test run -> test case`.

No reemplaza a `extraer_defectos_retro.py`: aquel produce el índice de
defectos por HU (ya cerrado y usado en la tesis) y este produce el detalle
por defecto. Se pueden correr de forma independiente.

Qué se pide y por qué se introspecta primero
--------------------------------------------
La query es la misma ya verificada contra la instancia real del proyecto
(`getTestPlan(issueId:) { testExecutions { results { testRuns { results {
... } } } } }`), más dos cosas por Test Run: `defects` (ya verificado en
`extraer_defectos_retro.py`) y `test { ... }` con
`jira(fields: ["key", "summary"])` (la misma forma de `jira(fields: [...])`
que ya usa `extraer_gherkin_historico_57hu.py`).

Lo único NO verificado todavía en esta instancia es que `TestRun` exponga el
sub-campo `test`. Siguiendo el patrón que ya usa
`extraer_gherkin_historico_57hu.py`, no se asume: se introspecta el tipo
`TestRun` antes de armar la query y, si `test` no existe, el script lo dice
y corta -- en vez de mandar una query inválida y fallar con un error de
GraphQL difícil de leer. El campo de contenido del caso (gherkin /
unstructured / steps) también se descubre por introspección, igual que allá,
porque no todas las instancias exponen los mismos.

Entrada (en la carpeta actual, ya generada por corridas reales previas):
    retro/retro_resultado_57hu.csv -- trae hu_key + test_plan_key.

Salida (en la carpeta actual):
    defectos_caso_detector_retro.csv
        Una fila por (defecto, caso de prueba que lo detectó). Un mismo
        defecto puede aparecer en más de una fila si lo reportaron desde
        varios Test Runs -- eso NO es un error, es información: significa
        que más de un caso lo destapó.
        Columnas: defecto_id, hu_key, test_plan_key, test_key, test_titulo,
        test_contenido, run_estado.

Uso (desde la raíz del proyecto, con el venv activado):

    python scripts\\extraer_caso_detector_defectos.py

Resumible por HU: si se corta a mitad de camino, correr de nuevo el mismo
comando retoma donde quedó. Una HU que ya se consultó no se vuelve a pedir,
aunque no haya dado ningún defecto (por eso se lleva un archivo aparte de
HU ya visitadas: "cero defectos" es un resultado válido, no un pendiente).
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

_ARCHIVO_ENTRADA = Path("retro") / "retro_resultado_57hu.csv"
_ARCHIVO_SALIDA = Path("defectos_caso_detector_retro.csv")
_ARCHIVO_VISITADAS = Path("defectos_caso_detector_retro.hu_visitadas.txt")

_COLUMNAS_SALIDA = [
    "defecto_id", "hu_key", "test_plan_key", "test_key", "test_titulo",
    "test_contenido", "run_estado",
]

_CANDIDATOS_CAMPO_CONTENIDO = ["gherkin", "unstructured", "steps"]

_QUERY_INTROSPECCION_TIPO = """
query($nombre: String!) {
  __type(name: $nombre) {
    name
    fields { name }
  }
}
"""


def _autenticar(cliente: httpx.Client, client_id: str, client_secret: str) -> str:
    resp = cliente.post(
        _URL_AUTENTICACION, json={"client_id": client_id, "client_secret": client_secret}
    )
    resp.raise_for_status()
    return resp.json()


def _post_con_reintentos(cliente: httpx.Client, url: str, **kwargs) -> httpx.Response:
    espera = _ESPERA_INICIAL_SEGUNDOS
    resp = None
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


def _introspectar_campos(cliente: httpx.Client, headers: dict, nombre_tipo: str) -> list[str]:
    resp = _post_con_reintentos(
        cliente, _URL_GRAPHQL, headers=headers,
        json={"query": _QUERY_INTROSPECCION_TIPO, "variables": {"nombre": nombre_tipo}},
    )
    resp.raise_for_status()
    datos = resp.json()
    if "errors" in datos or datos.get("data", {}).get("__type") is None:
        return []
    return [campo["name"] for campo in datos["data"]["__type"].get("fields", [])]


def _resolver_ids_internos(keys_test_plan: list[str]) -> dict[str, str]:
    """Mismo lote key -> ID interno ya usado en el resto del proyecto."""
    config = cargar_configuracion_jira()
    resultado: dict[str, str] = {}
    for i in range(0, len(keys_test_plan), 40):
        lote = keys_test_plan[i:i + 40]
        jql = "key in (" + ", ".join(lote) + ")"
        with httpx.Client(
            auth=(config.email, config.api_token), timeout=60.0,
            headers={"Accept": "application/json"},
        ) as cliente:
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
            f"No se encontró {_ARCHIVO_ENTRADA.resolve()} -- corré primero las "
            "extracciones del análisis retrospectivo antes de este script."
        )
    with _ARCHIVO_ENTRADA.open("r", newline="", encoding="utf-8") as f:
        return [
            (fila["hu_key"], (fila.get("test_plan_key") or "").strip())
            for fila in csv.DictReader(f)
        ]


def _texto_de_contenido(test: dict, campos_contenido: list[str]) -> str:
    """
    Devuelve el contenido del caso como texto, sea cual sea la forma en que
    esta instancia lo guarde (Gherkin, texto libre o pasos estructurados).
    """
    for campo in campos_contenido:
        valor = test.get(campo)
        if not valor:
            continue
        if campo == "steps":
            lineas = []
            for paso in valor:
                accion = (paso.get("action") or "").strip()
                dato = (paso.get("data") or "").strip()
                esperado = (paso.get("result") or "").strip()
                partes = [p for p in (accion, dato, esperado) if p]
                if partes:
                    lineas.append(" | ".join(partes))
            if lineas:
                return "\n".join(lineas)
        elif isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def _construir_query(campos_contenido: list[str]) -> str:
    sub_campos = ["issueId", 'jira(fields: ["key", "summary"])']
    for campo in campos_contenido:
        if campo == "steps":
            sub_campos.append("steps { action data result }")
        else:
            sub_campos.append(campo)
    fragmento_test = "{ " + " ".join(sub_campos) + " }"
    return f"""
    query($issueId: String) {{
      getTestPlan(issueId: $issueId) {{
        issueId
        testExecutions(limit: 100) {{
          results {{
            issueId
            testRuns(limit: 100) {{
              results {{
                status {{ name }}
                defects
                test {fragmento_test}
              }}
            }}
          }}
        }}
      }}
    }}
    """


def _filas_de_test_plan(test_plan: dict, hu_key: str, tp_key: str,
                        campos_contenido: list[str]) -> list[list[str]]:
    filas: list[list[str]] = []
    for ejecucion in (test_plan.get("testExecutions") or {}).get("results") or []:
        for run in (ejecucion.get("testRuns") or {}).get("results") or []:
            defectos = run.get("defects") or []
            if not defectos:
                continue
            test = run.get("test") or {}
            jira_test = test.get("jira") or {}
            test_key = jira_test.get("key", "") or ""
            test_titulo = jira_test.get("summary", "") or ""
            contenido = _texto_de_contenido(test, campos_contenido)
            estado = (run.get("status") or {}).get("name", "") or ""
            for defecto_id in defectos:
                filas.append([
                    defecto_id, hu_key, tp_key, test_key, test_titulo, contenido, estado,
                ])
    return filas


def _leer_visitadas() -> set[str]:
    if not _ARCHIVO_VISITADAS.exists():
        return set()
    return {
        linea.strip()
        for linea in _ARCHIVO_VISITADAS.read_text(encoding="utf-8").splitlines()
        if linea.strip()
    }


def _guardar(filas_por_hu: dict[str, list[list[str]]], orden_hu: list[str],
             visitadas: set[str]) -> None:
    with _ARCHIVO_SALIDA.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_COLUMNAS_SALIDA)
        for hu_key in orden_hu:
            for fila in filas_por_hu.get(hu_key, []):
                writer.writerow(fila)
    _ARCHIVO_VISITADAS.write_text(
        "\n".join(sorted(visitadas)) + "\n", encoding="utf-8"
    )


def main() -> None:
    config_xray = cargar_configuracion_xray()
    pares = _leer_entrada()
    orden_hu = [hu for hu, _ in pares]
    print(f"{len(pares)} HU leídas de {_ARCHIVO_ENTRADA}.")

    visitadas = _leer_visitadas()
    filas_por_hu: dict[str, list[list[str]]] = {}
    if _ARCHIVO_SALIDA.exists():
        with _ARCHIVO_SALIDA.open("r", newline="", encoding="utf-8") as f:
            lector = csv.reader(f)
            next(lector, None)
            for fila in lector:
                if fila:
                    filas_por_hu.setdefault(fila[1], []).append(fila)
    if visitadas:
        print(f"Salida previa encontrada: {len(visitadas)} HU ya consultadas -- se retoma.")

    pendientes = [(hu, tp) for hu, tp in pares if hu not in visitadas]
    if not pendientes:
        print("Nada pendiente -- todas las HU ya fueron consultadas.")
        _guardar(filas_por_hu, orden_hu, visitadas)
        _resumen_final(filas_por_hu)
        return

    sin_test_plan = [hu for hu, tp in pendientes if not tp]
    for hu in sin_test_plan:
        visitadas.add(hu)
    if sin_test_plan:
        print(f"{len(sin_test_plan)} HU sin Test Plan -- se marcan como visitadas sin consultar.")
    pendientes = [(hu, tp) for hu, tp in pendientes if tp]

    with httpx.Client(timeout=60.0) as cliente:
        print("\nAutenticando contra Xray Cloud...")
        token = _autenticar(cliente, config_xray.client_id, config_xray.client_secret)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        print("\nIntrospectando el tipo TestRun...")
        campos_test_run = _introspectar_campos(cliente, headers, "TestRun")
        print(f"  Campos reales de TestRun: {campos_test_run}")
        if "test" not in campos_test_run:
            raise SystemExit(
                "El tipo TestRun de esta instancia de Xray NO expone el sub-campo "
                "`test`, así que no hay forma de saber qué caso de prueba detectó "
                "cada defecto por esta vía. No se manda la query.\n"
                f"Campos disponibles: {campos_test_run}"
            )
        if "defects" not in campos_test_run:
            raise SystemExit(
                "El tipo TestRun de esta instancia NO expone `defects` -- revisá "
                "extraer_defectos_retro.py, que sí lo usaba.\n"
                f"Campos disponibles: {campos_test_run}"
            )

        print("\nIntrospectando el tipo Test para el campo de contenido...")
        campos_test = _introspectar_campos(cliente, headers, "Test")
        campos_contenido = [c for c in _CANDIDATOS_CAMPO_CONTENIDO if c in campos_test]
        print(f"  Campos de contenido confirmados: {campos_contenido or 'ninguno'}")
        if not campos_contenido:
            print(
                "  AVISO: no hay ningún campo de contenido conocido en el tipo Test. "
                "Se sigue igual: se van a guardar key y título del caso, con "
                "test_contenido vacío."
            )

        query = _construir_query(campos_contenido)

        keys_unicas = sorted({tp for _, tp in pendientes})
        print(f"\nResolviendo IDs internos de {len(keys_unicas)} Test Plan...")
        mapa_ids = _resolver_ids_internos(keys_unicas)
        faltantes = set(keys_unicas) - set(mapa_ids.keys())
        if faltantes:
            print(f"  AVISO: no se resolvió el ID interno de: {sorted(faltantes)}")

        for i, (hu_key, tp_key) in enumerate(pendientes, start=1):
            id_interno = mapa_ids.get(tp_key)
            if id_interno is None:
                print(f"  [{i}/{len(pendientes)}] {hu_key}: sin ID interno para {tp_key} -- se saltea.")
                continue

            print(f"  [{i}/{len(pendientes)}] {hu_key} -> Test Plan {tp_key}...")
            resp = _post_con_reintentos(
                cliente, _URL_GRAPHQL, headers=headers,
                json={"query": query, "variables": {"issueId": id_interno}},
            )
            if resp.status_code >= 400:
                print(f"    ERROR HTTP {resp.status_code} persistente: {resp.text[:300]}")
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
                continue

            datos = resp.json()
            if "errors" in datos:
                print(f"    ERROR de GraphQL: {str(datos['errors'])[:300]}")
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
                continue

            test_plan = (datos.get("data") or {}).get("getTestPlan")
            if test_plan is None:
                print("    getTestPlan devolvió null -- se saltea.")
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
                continue

            filas = _filas_de_test_plan(test_plan, hu_key, tp_key, campos_contenido)
            filas_por_hu[hu_key] = filas
            visitadas.add(hu_key)
            print(f"    {len(filas)} par(es) defecto-caso registrados.")
            _guardar(filas_por_hu, orden_hu, visitadas)
            time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)

    _guardar(filas_por_hu, orden_hu, visitadas)
    print(f"\nListo. {_ARCHIVO_SALIDA.resolve()}")
    _resumen_final(filas_por_hu)


def _resumen_final(filas_por_hu: dict[str, list[list[str]]]) -> None:
    todas = [fila for filas in filas_por_hu.values() for fila in filas]
    defectos = {fila[0] for fila in todas}
    sin_caso = {fila[0] for fila in todas if not fila[3]}
    print(f"{len(todas)} par(es) defecto-caso, sobre {len(defectos)} defecto(s) distintos.")
    if sin_caso:
        print(
            f"AVISO: {len(sin_caso)} defecto(s) quedaron sin key de caso detector "
            f"(el Test Run no traía `test`): {sorted(sin_caso)}"
        )


if __name__ == "__main__":
    main()
