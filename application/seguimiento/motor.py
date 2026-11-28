"""
Motor de cálculo de índices de Seguimiento (tesis) -- extraído de
`frontend/pages/5_🎯_Seguimiento.py` (2026-09-02) para que la página
Streamlit y el script batch de histórico cronológico
(`scripts/procesar_seguimiento_historico.py`) compartan EXACTAMENTE la
misma lógica sin duplicar ~500 líneas. Decisión de diseño:
persistir el histórico en `seguimiento_hu_metricas`
(`infrastructure/db/models_orm.py`) anclado cronológicamente en
`customfield_10428` ("Fin En certificación", ver
`CAMPO_FECHA_CERTIFICACION_TERMINADA` más abajo para el porqué de ese campo
puntual), en vez de remedir la misma muestra al paso de los días -- ver el
docstring de esa tabla para el razonamiento completo.

Este módulo NO depende de Streamlit: en vez de llamar a `st.progress()`
directo (lo que hacía imposible reusar este código desde un script de
consola), `ejecutar_seguimiento()` acepta un `on_progreso` opcional --
`Callable[[str, int, int, str], None]` (etapa, hecho, total, texto) -- que
el caller decide cómo mostrar (barras de Streamlit, `print` en consola, o
nada). Las etapas posibles son: "test_plan", "xray", "defectos",
"cobertura_ia".

Todo el resto del comportamiento es idéntico al ya validado con datos
reales (ver `frontend/pages/5_🎯_Seguimiento.py`, ahora reducido a wiring
de UI): misma fórmula de índice de ejecución, densidad de cobertura, test
pass rate, estado de defectos por severidad (customfield_10507,
"corregido" = Terminado) y cobertura real vía IA (opt-in en la página en
vivo, `LLMProvider.clasificar_cobertura_criterios()` -- el script batch la
activa siempre, ver su propio docstring sobre por qué el costo ya está
confirmado despreciable).
"""

from __future__ import annotations

import time
from datetime import date
from typing import Callable

import httpx
import pandas as pd

from adapters.issue_tracker.jira_cloud_adapter import JiraCloudAdapter
from infrastructure.fabrica_llm import crear_llm_provider


from application.seguimiento.patrones_criterios_v2 import (
    contar_criterios as contar_criterios,
)

OnProgreso = Callable[[str, int, int, str], None]

_URL_AUTENTICACION_XRAY = "https://xray.cloud.getxray.app/api/v2/authenticate"
_URL_GRAPHQL_XRAY = "https://xray.cloud.getxray.app/api/v2/graphql"

_MAX_REINTENTOS = 6
_ESPERA_INICIAL_SEGUNDOS = 3.0
_ESPERA_ENTRE_LLAMADAS_SEGUNDOS = 0.4
_MAX_PAGINAS_JQL = 20

_ESTADOS_FINALES = {"PASSED", "FAILED"}


CAMPO_SEVERIDAD_DEFECTO = "customfield_10507"
ESTADOS_DEFECTO_CORREGIDO = {"TERMINADO"}
NIVELES_SEVERIDAD = ["Menor", "Mediano", "Mayor", "Grave"]


CAMPO_FECHA_CERTIFICACION_TERMINADA = "customfield_10428"

_QUERY_TEST_PLAN = """
query($issueId: String) {
  getTestPlan(issueId: $issueId) {
    issueId
    tests(limit: 100) {
      total
      results {
        jira(fields: ["summary"])
      }
    }
    testExecutions(limit: 100) {
      results {
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


def construir_jql(estados_raw: str, desde: date, hasta: date) -> str:
    estados = [e.strip() for e in estados_raw.split(",") if e.strip()]
    partes = [
        f'status changed to "{e}" during ("{desde.isoformat()}", "{hasta.isoformat()}")'
        for e in estados
    ]
    if len(partes) == 1:
        return partes[0]
    return "(" + " OR ".join(partes) + ")"


def _post_con_reintentos(cliente: httpx.Client, url: str, **kwargs) -> httpx.Response:
    espera = _ESPERA_INICIAL_SEGUNDOS
    resp = None
    for intento in range(1, _MAX_REINTENTOS + 1):
        resp = cliente.post(url, **kwargs)
        if resp.status_code not in (429, 502, 503, 504):
            return resp
        retry_after = resp.headers.get("Retry-After")
        segundos_espera = float(retry_after) if retry_after else espera
        time.sleep(segundos_espera)
        espera *= 2
    return resp


def _get_con_reintentos(cliente: httpx.Client, url: str, **kwargs) -> httpx.Response:
    espera = _ESPERA_INICIAL_SEGUNDOS
    resp = None
    for intento in range(1, _MAX_REINTENTOS + 1):
        resp = cliente.get(url, **kwargs)
        if resp.status_code not in (429, 502, 503, 504):
            return resp
        retry_after = resp.headers.get("Retry-After")
        segundos_espera = float(retry_after) if retry_after else espera
        time.sleep(segundos_espera)
        espera *= 2
    return resp


def _resolver_detalle_defectos(cliente: httpx.Client, base_url: str, ids_defectos: list[str]) -> dict[str, dict]:
    """
    Trae estado + severidad (customfield_10507) de cada defecto detectado en
    TestRun.defects. Uno por uno vía GET /rest/api/3/issue/{id} -- ese
    endpoint de Jira acepta tanto la key visible como el ID interno
    numérico, y TestRun.defects devuelve justamente esos IDs internos, no
    keys (mismo hallazgo ya documentado para defectos_unicos en el punto
    12).
    """
    resultado: dict[str, dict] = {}
    for id_defecto in ids_defectos:
        resp = _get_con_reintentos(
            cliente, f"{base_url}/rest/api/3/issue/{id_defecto}",
            params={"fields": f"status,{CAMPO_SEVERIDAD_DEFECTO}"},
        )
        if resp is None or resp.status_code >= 400:
            resultado[id_defecto] = {"estado": "ERROR", "severidad": ""}
            continue
        campos = resp.json().get("fields", {})
        severidad_raw = campos.get(CAMPO_SEVERIDAD_DEFECTO)
        if isinstance(severidad_raw, dict):
            severidad = severidad_raw.get("value") or severidad_raw.get("name") or ""
        else:
            severidad = severidad_raw or ""
        resultado[id_defecto] = {
            "estado": (campos.get("status") or {}).get("name", ""),
            "severidad": severidad or "(sin severidad)",
        }
        time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
    return resultado


def _resumir_severidad(ids_defectos: set[str], detalle: dict[str, dict]) -> tuple[str, int, dict, dict, int, int]:
    """
    Arma el texto compacto "Menor: 1/2 · Mediano: 0/1 · ..." (resueltos/
    detectados) por nivel de severidad, más el total de resueltos. Un
    defecto sin severidad reconocida (valor distinto a los 4 niveles, o
    error al consultarlo) cae en "Otros", visible en vez de descartado en
    silencio.
    """
    detectados = {nivel: 0 for nivel in NIVELES_SEVERIDAD}
    resueltos = {nivel: 0 for nivel in NIVELES_SEVERIDAD}
    otros_detectados = 0
    otros_resueltos = 0

    for id_defecto in ids_defectos:
        info = detalle.get(id_defecto, {"estado": "", "severidad": ""})
        severidad = (info.get("severidad") or "").strip()
        esta_resuelto = (info.get("estado") or "").strip().upper() in ESTADOS_DEFECTO_CORREGIDO
        nivel = next((n for n in NIVELES_SEVERIDAD if n.lower() == severidad.lower()), None)
        if nivel:
            detectados[nivel] += 1
            if esta_resuelto:
                resueltos[nivel] += 1
        else:
            otros_detectados += 1
            if esta_resuelto:
                otros_resueltos += 1

    partes = [f"{n}: {resueltos[n]}/{detectados[n]}" for n in NIVELES_SEVERIDAD if detectados[n] > 0]
    if otros_detectados:
        partes.append(f"Otros: {otros_resueltos}/{otros_detectados}")

    total_resueltos = sum(resueltos.values()) + otros_resueltos
    return " · ".join(partes), total_resueltos, detectados, resueltos, otros_detectados, otros_resueltos


def buscar_issues_por_jql(cliente: httpx.Client, base_url: str, jql: str, campos: list[str]) -> list[dict]:
    resultados: list[dict] = []
    token_pagina: str | None = None
    for _ in range(_MAX_PAGINAS_JQL):
        body = {"jql": jql, "maxResults": 100, "fields": campos}
        if token_pagina:
            body["nextPageToken"] = token_pagina
        resp = _post_con_reintentos(cliente, f"{base_url}/rest/api/3/search/jql", json=body)
        resp.raise_for_status()
        data = resp.json()
        resultados.extend(data.get("issues", []))
        if data.get("isLast", True) or not data.get("nextPageToken"):
            break
        token_pagina = data["nextPageToken"]
    return resultados


def _resolver_ids_internos(cliente: httpx.Client, base_url: str, keys: list[str]) -> dict[str, str]:
    resultado: dict[str, str] = {}
    for i in range(0, len(keys), 40):
        lote = keys[i:i + 40]
        jql = "key in (" + ", ".join(lote) + ")"
        resp = _post_con_reintentos(
            cliente, f"{base_url}/rest/api/3/search/jql",
            json={"jql": jql, "maxResults": 100, "fields": []},
        )
        resp.raise_for_status()
        for issue in resp.json().get("issues", []):
            resultado[issue["key"]] = issue["id"]
    return resultado


def _autenticar_xray(cliente: httpx.Client, client_id: str, client_secret: str) -> str:
    resp = _post_con_reintentos(
        cliente, _URL_AUTENTICACION_XRAY,
        json={"client_id": client_id, "client_secret": client_secret},
    )
    resp.raise_for_status()
    return resp.json()


def _consultar_test_plan(cliente: httpx.Client, headers: dict, issue_id: str) -> dict | None:
    resp = _post_con_reintentos(
        cliente, _URL_GRAPHQL_XRAY, headers=headers,
        json={"query": _QUERY_TEST_PLAN, "variables": {"issueId": issue_id}},
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Xray HTTP {resp.status_code}: {resp.text[:200]}")
    datos = resp.json()
    if "errors" in datos:
        raise RuntimeError(str(datos["errors"])[:300])
    return datos["data"]["getTestPlan"]


def buscar_hu_certificadas(
    creds: dict,
    desde: date | None = None,
    hasta: date | None = None,
    jql_extra: str | None = None,
    jql_completo: str | None = None,
) -> list[dict]:
    """
    Busca HU con `customfield_10428` (Fin En certificación) cargado --
    candidatas para el histórico cronológico batch (ver
    `scripts/procesar_seguimiento_historico.py`). Devuelve
    `[{"key": str, "fecha_certificacion_terminada": date | None}, ...]`
    YA ORDENADO de más antigua a más nueva por ese campo.

    El orden lo hace Python después de traer los datos, no un `ORDER BY`
    de JQL sobre un campo custom (Jira Cloud no garantiza que un custom
    field de fecha sea ordenable vía JQL sin configurarlo explícitamente
    como tal). Si alguna HU viniera sin valor pese al filtro
    "is not EMPTY" (dato inconsistente real), no se descarta -- queda al
    final de la lista, visible, para que quien la procese decida (mismo
    criterio de "nunca ocultar datos raros" del resto del proyecto).

    Args:
        jql_extra: condiciones adicionales opcionales que se agregan con
            AND al filtro base (ej. excluir proyectos: 'project not in
            (PRJ-16, PRJ-11, PRJ-07)'). Se ignora si se pasa `jql_completo`.
        jql_completo: si se pasa, REEMPLAZA por completo el filtro base
            (customfield_10428 is not EMPTY + desde/hasta + jql_extra) --
            se usa tal cual, sin agregarle nada. Pensado para un JQL ya
            armado y validado por el usuario, ej. anclado en el historial
            de cambios de estado ("status changed to ... during (...)")
            en vez del customfield -- más confiable porque refleja la
            transición real del workflow en vez de un campo que alguien
            pudo cargar mal (decisión 2026-09-02, ver
            `scripts/procesar_seguimiento_historico.py`). El campo
            `customfield_10428` se sigue leyendo por issue igual (para
            ordenar y para guardar `fecha_certificacion_terminada`),
            aunque no forme parte del filtro de búsqueda.
    """
    if jql_completo:
        jql = jql_completo
    else:
        partes = [f"{CAMPO_FECHA_CERTIFICACION_TERMINADA} is not EMPTY"]
        if desde:
            partes.append(f'{CAMPO_FECHA_CERTIFICACION_TERMINADA} >= "{desde.isoformat()}"')
        if hasta:
            partes.append(f'{CAMPO_FECHA_CERTIFICACION_TERMINADA} <= "{hasta.isoformat()}"')
        if jql_extra:
            partes.append(f"({jql_extra})")
        jql = " AND ".join(partes)

    with httpx.Client(
        auth=(creds["jira_email"], creds["jira_api_token"]),
        timeout=60.0, headers={"Accept": "application/json"},
    ) as cliente:
        issues = buscar_issues_por_jql(
            cliente, creds["jira_base_url"], jql, ["key", CAMPO_FECHA_CERTIFICACION_TERMINADA],
        )

    filas = []
    for issue in issues:
        valor = issue.get("fields", {}).get(CAMPO_FECHA_CERTIFICACION_TERMINADA)
        fecha = date.fromisoformat(valor[:10]) if valor else None
        filas.append({"key": issue["key"], "fecha_certificacion_terminada": fecha})

    filas.sort(key=lambda f: (f["fecha_certificacion_terminada"] is None, f["fecha_certificacion_terminada"]))
    return filas


def ejecutar_seguimiento(
    jql: str,
    creds: dict,
    calcular_cobertura_ia: bool = False,
    on_progreso: OnProgreso | None = None,
) -> pd.DataFrame:
    def _avisar(etapa: str, hecho: int, total: int, texto: str) -> None:
        if on_progreso:
            on_progreso(etapa, hecho, total, texto)

    with httpx.Client(
        auth=(creds["jira_email"], creds["jira_api_token"]),
        timeout=60.0, headers={"Accept": "application/json"},
    ) as jira_client:
        issues = buscar_issues_por_jql(jira_client, creds["jira_base_url"], jql, ["key", "summary"])
        if not issues:
            return pd.DataFrame()

        keys_hu = [i["key"] for i in issues]

        adapter_jira = JiraCloudAdapter(creds["jira_base_url"], creds["jira_email"], creds["jira_api_token"])
        filas_hu = []
        try:
            for i, key_hu in enumerate(keys_hu, start=1):
                hu = adapter_jira.obtener_hu(key_hu)
                test_plans = adapter_jira.detectar_test_plan(key_hu)
                filas_hu.append({
                    "hu_key": key_hu,
                    "descripcion": hu.descripcion,
                    "test_plan_keys": [tp.key for tp in test_plans],
                })
                _avisar("test_plan", i, len(keys_hu), f"Test Plan de {key_hu} ({i}/{len(keys_hu)})")
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
        finally:
            adapter_jira.cerrar()

        keys_tp_unicas = sorted({tp for fila in filas_hu for tp in fila["test_plan_keys"]})
        mapa_ids_internos = (
            _resolver_ids_internos(jira_client, creds["jira_base_url"], keys_tp_unicas)
            if keys_tp_unicas else {}
        )

    filas_salida = []
    id_defectos_por_hu: dict[str, set[str]] = {}
    criterios_por_hu: dict[str, list[str]] = {}
    titulos_tests_por_hu: dict[str, list[str]] = {}
    with httpx.Client(timeout=60.0) as xray_client:
        token = _autenticar_xray(xray_client, creds["xray_client_id"], creds["xray_client_secret"])
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        for i, fila in enumerate(filas_hu, start=1):
            hu_key = fila["hu_key"]
            tp_keys = fila["test_plan_keys"]
            patron, criterios = contar_criterios(fila["descripcion"])
            num_criterios = len(criterios)

            if not tp_keys:
                filas_salida.append({
                    "hu_key": hu_key, "test_plan_keys": "", "num_test_plans": 0,
                    "patron_criterios": patron, "num_criterios_identificados": num_criterios,
                    "num_tests": None, "indice_cobertura_densidad_pct": None,
                    "num_test_runs": None, "num_runs_ejecutados": None, "indice_ejecucion_pct": None,
                    "num_runs_pass": None, "test_pass_rate_pct": None,
                    "num_runs_con_defecto": None, "indice_defectos_pct": None, "defectos_unicos": "",
                    "num_defectos_resueltos": None, "defectos_por_severidad": "",
                    "indice_cobertura_real_pct": None, "criterios_no_cubiertos": "",
                    "aviso": "sin Test Plan vinculado -- excluida de ejecución/cobertura/defectos",
                })
                id_defectos_por_hu[hu_key] = set()
                _avisar("xray", i, len(filas_hu), f"{hu_key} (sin Test Plan)")
                continue

            num_tests_total = 0
            titulos_tests: list[str] = []
            runs_totales = 0
            runs_ejecutados = 0
            runs_pass = 0
            runs_con_defecto = 0
            defectos_unicos: set[str] = set()
            error_tp = None

            for tp_key in tp_keys:
                id_interno = mapa_ids_internos.get(tp_key)
                if id_interno is None:
                    error_tp = f"no se resolvió ID interno de {tp_key}"
                    continue
                try:
                    test_plan = _consultar_test_plan(xray_client, headers, id_interno)
                except RuntimeError as exc:
                    error_tp = str(exc)
                    continue
                if test_plan is None:
                    error_tp = f"Xray no encontró el Test Plan {tp_key}"
                    continue

                info_tests = test_plan.get("tests") or {}
                num_tests_total += info_tests.get("total") or 0
                for t in info_tests.get("results", []) or []:
                    titulo_test = (t.get("jira") or {}).get("summary")
                    if titulo_test:
                        titulos_tests.append(titulo_test)

                for ejecucion in (test_plan.get("testExecutions") or {}).get("results", []) or []:
                    for run in (ejecucion.get("testRuns") or {}).get("results", []) or []:
                        runs_totales += 1
                        estado_run = (run.get("status") or {}).get("name")
                        if estado_run in _ESTADOS_FINALES:
                            runs_ejecutados += 1
                        if estado_run == "PASSED":
                            runs_pass += 1
                        defectos_run = run.get("defects") or []
                        if defectos_run:
                            runs_con_defecto += 1
                            defectos_unicos.update(defectos_run)
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)

            indice_ejecucion = round(runs_ejecutados / runs_totales * 100, 1) if runs_totales else None
            indice_cobertura = round(num_tests_total / num_criterios * 100, 1) if num_criterios else None
            test_pass_rate = round(runs_pass / runs_ejecutados * 100, 1) if runs_ejecutados else None
            indice_defectos = round(runs_con_defecto / runs_totales * 100, 1) if runs_totales else None
            id_defectos_por_hu[hu_key] = defectos_unicos
            criterios_por_hu[hu_key] = criterios
            titulos_tests_por_hu[hu_key] = titulos_tests

            avisos_fila = []
            if len(tp_keys) > 1:
                avisos_fila.append(f"{len(tp_keys)} Test Plans combinados")
            if patron == "SIN_PATRON_DETECTADO":
                avisos_fila.append("sin patrón de criterios detectado -- cobertura no calculable")
            if error_tp:
                avisos_fila.append(error_tp)

            filas_salida.append({
                "hu_key": hu_key,
                "test_plan_keys": ";".join(tp_keys),
                "num_test_plans": len(tp_keys),
                "patron_criterios": patron,
                "num_criterios_identificados": num_criterios,
                "num_tests": num_tests_total,
                "indice_cobertura_densidad_pct": indice_cobertura,
                "num_test_runs": runs_totales,
                "num_runs_ejecutados": runs_ejecutados,
                "indice_ejecucion_pct": indice_ejecucion,
                "num_runs_pass": runs_pass,
                "test_pass_rate_pct": test_pass_rate,
                "num_runs_con_defecto": runs_con_defecto,
                "indice_defectos_pct": indice_defectos,
                "defectos_unicos": ";".join(sorted(defectos_unicos)),
                "num_defectos_resueltos": None,
                "defectos_por_severidad": "",
                "indice_cobertura_real_pct": None,
                "criterios_no_cubiertos": "",
                "aviso": " | ".join(avisos_fila),
            })
            _avisar("xray", i, len(filas_hu), f"{hu_key} ({i}/{len(filas_hu)})")


    todos_los_ids_defectos = sorted({d for ids in id_defectos_por_hu.values() for d in ids})
    if todos_los_ids_defectos:
        with httpx.Client(
            auth=(creds["jira_email"], creds["jira_api_token"]),
            timeout=60.0, headers={"Accept": "application/json"},
        ) as jira_client_defectos:
            detalle_defectos = _resolver_detalle_defectos(
                jira_client_defectos, creds["jira_base_url"], todos_los_ids_defectos,
            )
            _avisar("defectos", 1, 1, f"{len(todos_los_ids_defectos)} defectos resueltos")

        for fila in filas_salida:
            ids_hu = id_defectos_por_hu.get(fila["hu_key"], set())
            if ids_hu:
                texto_severidad, total_resueltos, detectados, resueltos, otros_det, otros_res = (
                    _resumir_severidad(ids_hu, detalle_defectos)
                )
                fila["defectos_por_severidad"] = texto_severidad
                fila["num_defectos_resueltos"] = total_resueltos
                for nivel in NIVELES_SEVERIDAD:
                    clave = nivel.lower()
                    fila[f"defectos_{clave}_detectados"] = detectados[nivel]
                    fila[f"defectos_{clave}_resueltos"] = resueltos[nivel]
                fila["defectos_otros_detectados"] = otros_det
                fila["defectos_otros_resueltos"] = otros_res


    if calcular_cobertura_ia:
        hu_con_criterios = [
            hu_key for hu_key, criterios in criterios_por_hu.items() if criterios
        ]
        if hu_con_criterios:
            llm_provider = crear_llm_provider()
            for i, hu_key in enumerate(hu_con_criterios, start=1):
                criterios = criterios_por_hu[hu_key]
                tests = [{"titulo": t, "gherkin": ""} for t in titulos_tests_por_hu.get(hu_key, [])]
                try:
                    clasificacion = llm_provider.clasificar_cobertura_criterios(criterios, tests)
                except Exception as exc:
                    aviso_error = f"cobertura real no calculada: {exc}"
                    for fila in filas_salida:
                        if fila["hu_key"] == hu_key:
                            fila["aviso"] = (fila["aviso"] + " | " if fila["aviso"] else "") + aviso_error
                    _avisar("cobertura_ia", i, len(hu_con_criterios), f"{hu_key}: error")
                    continue

                cubiertos = sum(1 for c in clasificacion if c["cubierto"])
                no_cubiertos = [c["criterio"] for c in clasificacion if not c["cubierto"]]
                indice_real = round(cubiertos / len(criterios) * 100, 1) if criterios else None

                for fila in filas_salida:
                    if fila["hu_key"] == hu_key:
                        fila["indice_cobertura_real_pct"] = indice_real
                        fila["criterios_no_cubiertos"] = " || ".join(no_cubiertos)
                _avisar("cobertura_ia", i, len(hu_con_criterios), f"Cobertura real de {hu_key} ({i}/{len(hu_con_criterios)})")

    return pd.DataFrame(filas_salida)
