"""
Análisis retrospectivo / NEXUS Pre-Test-Post-Test — severidad y estado real de los
defectos históricos (2026-09-06).

`scripts/extraer_defectos_retro.py` ya trae, por cada una de las 43 HU del
análisis retrospectivo, la lista de IDs internos de defecto en la columna `defectos_unicos`
de `retro/retro_resultado_57hu.csv` -- pero son identificadores internos
numéricos de Xray/Jira, SIN severidad ni estado resueltos (documentado así
en ese mismo script: "auditar un defecto puntual en Jira requeriría el mismo
tipo de resolución interno↔key ya usado en el proyecto para Test Plans -- no
se hizo, no era necesario para el número"). Este script cierra ese gap para
poder construir la sección "Estado de defectos por criticidad" del nuevo
dashboard Pre-Test/Post-Test.

Para cada ID interno único, resuelve vía Jira Cloud REST v3
(`/rest/api/3/issue/{id}`, que acepta indistintamente key o ID interno --
mismo endpoint que ya usa `JiraCloudAdapter.obtener_hu()`, solo que ahí se le
pasa la key y acá el ID):
  - `key`                    -> key legible del defecto.
  - `customfield_10507`      -> severidad real (Menor/Mediano/Mayor/Grave),
                                 el mismo campo que ya usa la sección
                                 "Estado de defectos" de Seguimiento.
  - `status.name`            -> abierto (!= "Terminado") o cerrado
                                 (== "Terminado"), mismo criterio que ya usa
                                 el índice de defectos del libro [29].
  - `summary`                -> título del defecto.
  - `description`            -> descripción, convertida de ADF a texto plano
                                 reusando `JiraCloudAdapter._adf_a_texto`
                                 (la misma conversión ya verificada que usa
                                 `obtener_hu()`; en Jira Cloud v3 el campo
                                 description NO es texto plano).

**Ampliación 2026-09-06 (segunda pasada)**: `summary` y `description` no
estaban en la primera versión -- se agregaron porque el análisis de
"evitabilidad" acordado con el usuario (¿este defecto lo habría detectado el
agente, o se iba a dar igual?) necesita el CONTENIDO del defecto, no solo su
severidad. Sin el título y la descripción no hay forma de juzgar contra qué
caso del agente compararlo.

Consecuencia para la resumibilidad: una salida previa generada por la PRIMERA
versión de este script no tiene columna `defecto_titulo`. Por eso el criterio
de "ya resuelto" pasó a exigir un `defecto_titulo` no vacío -- un detalle
viejo se vuelve a pedir a Jira en vez de quedarse para siempre sin título.
Todo defecto real de Jira tiene summary (la descripción sí puede venir
vacía), así que este criterio no descarta nada legítimo.

Mapeo de criticidad (Decisión de diseño para el mockup de
Pre-Test/Post-Test): Grave->Critico, Mayor->Alto, Mediano->Medio,
Menor->Bajo. Un valor de severidad que no matchea ninguno de los 4 (o que
Jira devuelve vacío) se marca SIN_CLASIFICAR en vez de inventar un bucket --
mismo criterio que SIN_PATRON_DETECTADO en
`contar_criterios_aceptacion_retro.py`.

Importante -- esto es SOLO el lado histórico (Pre-Test) de "Estado de
defectos": la corrida exploratoria utilizó `RepositoryNulo`, sin publicar
sus casos en Xray ni tocar producción. Este corpus no aporta defectos
observados de Post-Test; no describe las ejecuciones QA del flujo operativo. Qué mostrar ahí es una decisión de producto pendiente de
confirmar con el usuario, no algo que este script deba inventar.

A diferencia de otros scripts del proyecto que golpean la API de Xray (con
reintento agresivo y checkpoints), acá el volumen es chico -- unas pocas
decenas de defectos únicos, no una llamada por HU -- así que alcanza con
reintento simple ante 429/502/503/504 y una escritura incremental liviana
(por si se corta a mitad de camino, correr de nuevo retoma sin repetir
llamadas ya resueltas).

Entrada (ya generada por corridas reales previas, en la carpeta actual):
    retro/retro_resultado_57hu.csv -- trae hu_key + defectos_unicos.

Salida (en la carpeta actual):
    defectos_severidad_detalle_retro.csv
        Una fila por defecto único real: defecto_id, defecto_key,
        defecto_titulo, defecto_descripcion, severidad_real, criticidad,
        estado_real, abierto_cerrado, hu_keys (las HU del corpus de 43 donde
        aparece, separadas por ";").
    defectos_severidad_resumen_retro.csv
        Una fila por HU, con el conteo de defectos por
        criticidad x abierto/cerrado (8 columnas) + sin_clasificar +
        total_defectos, para poder sumarlas directo en el dashboard sin
        tener que releer el detalle.

Uso (desde la raíz del proyecto, con el venv activado):

    python scripts\\resolver_severidad_defectos_retro.py

Si se corta a mitad de camino, correr de nuevo el mismo comando retoma
donde quedó (no vuelve a pedir los defectos ya resueltos). A diferencia de
`extraer_defectos_retro.py` (que persiste un "ERROR" permanente para no
reintentar), acá un defecto que da 404 o error persistente NO se marca como
resuelto -- queda pendiente y se reintenta en la próxima corrida. Decisión
deliberada: un 404 real en Xray/Jira para un defecto que ya se sabía
vinculado (viene de `defectos_unicos`, ya confirmado real en la extracción
anterior) es más probable que sea un problema transitorio que un borrado
real, así que no conviene descartarlo en silencio.
"""

from __future__ import annotations

import csv
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from adapters.issue_tracker.jira_cloud_adapter import JiraCloudAdapter
from infrastructure.config import cargar_configuracion_jira

_MAX_REINTENTOS = 5
_ESPERA_INICIAL_SEGUNDOS = 2.0
_ESPERA_ENTRE_LLAMADAS_SEGUNDOS = 0.3

_ARCHIVO_ENTRADA = Path("retro") / "retro_resultado_57hu.csv"
_ARCHIVO_SALIDA_DETALLE = Path("defectos_severidad_detalle_retro.csv")
_ARCHIVO_SALIDA_RESUMEN = Path("defectos_severidad_resumen_retro.csv")

_CAMPO_SEVERIDAD = "customfield_10507"
_ESTADO_CERRADO = "terminado"

_MAPA_CRITICIDAD = {
    "grave": "Critico",
    "mayor": "Alto",
    "mediano": "Medio",
    "menor": "Bajo",
}
_CRITICIDADES_ORDENADAS = ["Critico", "Alto", "Medio", "Bajo"]

_COLUMNAS_DETALLE = [
    "defecto_id", "defecto_key", "defecto_titulo", "defecto_descripcion",
    "severidad_real", "criticidad", "estado_real", "abierto_cerrado", "hu_keys",
]
_COLUMNAS_RESUMEN = (
    ["hu_key", "total_defectos"]
    + [f"{crit.lower()}_abiertos" for crit in _CRITICIDADES_ORDENADAS]
    + [f"{crit.lower()}_cerrados" for crit in _CRITICIDADES_ORDENADAS]
    + ["sin_clasificar"]
)


def _criticidad_de(severidad_real: str) -> str:
    return _MAPA_CRITICIDAD.get((severidad_real or "").strip().lower(), "SIN_CLASIFICAR")


def _abierto_cerrado_de(estado_real: str) -> str:
    return "Cerrado" if (estado_real or "").strip().lower() == _ESTADO_CERRADO else "Abierto"


def _leer_entrada() -> list[tuple[str, list[str]]]:
    if not _ARCHIVO_ENTRADA.exists():
        raise SystemExit(
            f"No se encontró {_ARCHIVO_ENTRADA.resolve()} -- corré primero "
            "extraer_defectos_retro.py (ya mergeado en "
            "retro/retro_resultado_57hu.csv) antes de este script."
        )
    filas: list[tuple[str, list[str]]] = []
    with _ARCHIVO_ENTRADA.open("r", newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            crudos = (fila.get("defectos_unicos") or "").strip()
            ids = [x for x in crudos.split(";") if x] if crudos else []
            filas.append((fila["hu_key"], ids))
    return filas


def _get_con_reintentos(cliente: httpx.Client, url: str, **kwargs) -> httpx.Response:
    espera = _ESPERA_INICIAL_SEGUNDOS
    for intento in range(1, _MAX_REINTENTOS + 1):
        resp = cliente.get(url, **kwargs)
        if resp.status_code not in (429, 502, 503, 504):
            return resp
        retry_after = resp.headers.get("Retry-After")
        segundos_espera = float(retry_after) if retry_after else espera
        print(
            f"    Jira respondió {resp.status_code}. Esperando {segundos_espera:.1f}s "
            f"antes de reintentar (intento {intento}/{_MAX_REINTENTOS})..."
        )
        time.sleep(segundos_espera)
        espera *= 2
    return resp


def _resolver_un_defecto(cliente: httpx.Client, base_url: str, defecto_id: str) -> dict | None:
    """
    Trae key/severidad/estado real de un defecto a partir de su ID interno.

    Jira Cloud REST v3 acepta tanto la key como el ID interno numérico en el
    mismo endpoint `/rest/api/3/issue/{issueIdOrKey}` -- no hace falta JQL ni
    ningún endpoint especial para esto, mismo endpoint que ya usa
    `JiraCloudAdapter.obtener_hu()` en el resto del proyecto.
    """
    url = f"{base_url}/rest/api/3/issue/{defecto_id}"
    params = {"fields": f"key,summary,description,{_CAMPO_SEVERIDAD},status"}
    resp = _get_con_reintentos(cliente, url, params=params)

    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    campos = data.get("fields", {})

    valor_severidad = campos.get(_CAMPO_SEVERIDAD)
    if isinstance(valor_severidad, dict):

        severidad_real = valor_severidad.get("value", "") or ""
    else:
        severidad_real = valor_severidad or ""

    estado_real = (campos.get("status") or {}).get("name", "") or ""


    descripcion = JiraCloudAdapter._adf_a_texto(campos.get("description"))

    return {
        "key": data.get("key", defecto_id),
        "titulo": (campos.get("summary") or "").strip(),
        "descripcion": descripcion,
        "severidad_real": severidad_real,
        "estado_real": estado_real,
    }


def _escribir_detalle(resueltos: dict[str, dict], hus_por_defecto: dict[str, set[str]]) -> None:
    with _ARCHIVO_SALIDA_DETALLE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_COLUMNAS_DETALLE)
        for defecto_id in sorted(hus_por_defecto.keys()):
            info = resueltos.get(defecto_id)
            hu_keys = ";".join(sorted(hus_por_defecto[defecto_id]))
            if info is None:
                writer.writerow([defecto_id, "", "", "", "", "SIN_CLASIFICAR", "", "SIN_DATO", hu_keys])
                continue
            criticidad = _criticidad_de(info["severidad_real"])
            abierto_cerrado = _abierto_cerrado_de(info["estado_real"])
            writer.writerow([
                defecto_id, info["key"], info.get("titulo", ""), info.get("descripcion", ""),
                info["severidad_real"], criticidad,
                info["estado_real"], abierto_cerrado, hu_keys,
            ])


def _escribir_resumen(filas_entrada: list[tuple[str, list[str]]], resueltos: dict[str, dict]) -> None:
    with _ARCHIVO_SALIDA_RESUMEN.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_COLUMNAS_RESUMEN)
        for hu_key, ids in filas_entrada:
            conteos: dict[str, int] = defaultdict(int)
            sin_clasificar = 0
            for defecto_id in ids:
                info = resueltos.get(defecto_id)
                if info is None:
                    sin_clasificar += 1
                    continue
                criticidad = _criticidad_de(info["severidad_real"])
                if criticidad == "SIN_CLASIFICAR":
                    sin_clasificar += 1
                    continue
                abierto_cerrado = _abierto_cerrado_de(info["estado_real"])
                sufijo = "abiertos" if abierto_cerrado == "Abierto" else "cerrados"
                conteos[f"{criticidad.lower()}_{sufijo}"] += 1

            fila = [hu_key, len(ids)]
            for crit in _CRITICIDADES_ORDENADAS:
                fila.append(conteos.get(f"{crit.lower()}_abiertos", 0))
            for crit in _CRITICIDADES_ORDENADAS:
                fila.append(conteos.get(f"{crit.lower()}_cerrados", 0))
            fila.append(sin_clasificar)
            writer.writerow(fila)


def main() -> None:
    config_jira = cargar_configuracion_jira()
    filas_entrada = _leer_entrada()
    print(f"{len(filas_entrada)} HU leídas de {_ARCHIVO_ENTRADA}.")

    hus_por_defecto: dict[str, set[str]] = defaultdict(set)
    for hu_key, ids in filas_entrada:
        for defecto_id in ids:
            hus_por_defecto[defecto_id].add(hu_key)

    ids_unicos = sorted(hus_por_defecto.keys())
    if not ids_unicos:
        print("Ninguna HU del corpus tiene defectos vinculados -- nada que resolver.")
        _escribir_detalle({}, hus_por_defecto)
        _escribir_resumen(filas_entrada, {})
        print(f"\nListo. {_ARCHIVO_SALIDA_DETALLE.resolve()} / {_ARCHIVO_SALIDA_RESUMEN.resolve()}")
        return

    print(f"{len(ids_unicos)} defectos únicos a resolver.")

    resueltos: dict[str, dict] = {}
    formato_viejo = 0
    if _ARCHIVO_SALIDA_DETALLE.exists():
        with _ARCHIVO_SALIDA_DETALLE.open("r", newline="", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                if not fila.get("defecto_key"):

                    continue
                if not (fila.get("defecto_titulo") or "").strip():


                    formato_viejo += 1
                    continue
                resueltos[fila["defecto_id"]] = {
                    "key": fila["defecto_key"],
                    "titulo": fila.get("defecto_titulo", ""),
                    "descripcion": fila.get("defecto_descripcion", ""),
                    "severidad_real": fila["severidad_real"],
                    "estado_real": fila["estado_real"],
                }
        if resueltos:
            print(f"Se encontró una salida previa con {len(resueltos)} defecto(s) ya resueltos -- se retoma.")
        if formato_viejo:
            print(
                f"{formato_viejo} defecto(s) venían de la versión previa del script (sin título ni "
                "descripción) -- se vuelven a pedir a Jira para completarlos."
            )

    pendientes = [d for d in ids_unicos if d not in resueltos]
    if not pendientes:
        print("Nada pendiente -- todos los defectos ya estaban resueltos.")
    else:
        with httpx.Client(
            auth=(config_jira.email, config_jira.api_token),
            timeout=30.0,
            headers={"Accept": "application/json"},
        ) as cliente:
            for i, defecto_id in enumerate(pendientes, start=1):
                print(f"  [{i}/{len(pendientes)}] Resolviendo defecto {defecto_id}...")
                try:
                    info = _resolver_un_defecto(cliente, config_jira.base_url, defecto_id)
                except httpx.HTTPStatusError as exc:
                    print(f"    ERROR HTTP {exc.response.status_code} persistente -- se deja sin resolver.")
                    info = None
                except httpx.RequestError as exc:
                    print(f"    ERROR de conexión ({exc!r}) -- se deja sin resolver.")
                    info = None

                if info is None:
                    print(f"    AVISO: no se pudo resolver el defecto {defecto_id} (404 o error persistente).")
                else:
                    resueltos[defecto_id] = info

                _escribir_detalle(resueltos, hus_por_defecto)
                _escribir_resumen(filas_entrada, resueltos)
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)

    _escribir_detalle(resueltos, hus_por_defecto)
    _escribir_resumen(filas_entrada, resueltos)

    print(f"\nListo. {_ARCHIVO_SALIDA_DETALLE.resolve()} / {_ARCHIVO_SALIDA_RESUMEN.resolve()}")

    sin_resolver = [d for d in ids_unicos if d not in resueltos]
    if sin_resolver:
        print(f"AVISO: {len(sin_resolver)} defecto(s) no se pudieron resolver: {sin_resolver}")

    conteo_criticidad: dict[str, int] = defaultdict(int)
    for info in resueltos.values():
        conteo_criticidad[_criticidad_de(info["severidad_real"])] += 1
    print("Distribución real por criticidad (todos los defectos resueltos, sin distinguir HU):")
    for crit in _CRITICIDADES_ORDENADAS + ["SIN_CLASIFICAR"]:
        print(f"  {crit}: {conteo_criticidad.get(crit, 0)}")


if __name__ == "__main__":
    main()
