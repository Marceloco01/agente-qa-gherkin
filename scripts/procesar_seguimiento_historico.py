"""
Backfill cronológico de `seguimiento_hu_metricas` (tesis, decisión
adoptada para este diseño 2026-09-02: "cronológico").

Ancla las HU en `customfield_10428` ("Fin En certificación") --
señalado por el usuario como más confiable que el estado "En Producción"
(práctica de registro del equipo todavía inconsistente) -- y las procesa en
cohortes configurables (default 10), de más antigua a más nueva,
restringido a HU con al menos un criterio de aceptación detectable. Ver el
docstring completo de la decisión en
`infrastructure/db/models_orm.py::SeguimientoHUMetricasORM`.

Reusa EXACTAMENTE el mismo motor que la página en vivo
(`application/seguimiento/motor.py::ejecutar_seguimiento()`) -- no
reimplementa nada de la consulta a Jira/Xray ni de las fórmulas.

Resumible SIN necesidad de un CSV de control aparte (a diferencia de otros
scripts batch del proyecto, ej. `extraer_defectos_retro.py`): antes de
cada corrida se le pregunta a la base de datos qué HU ya tienen snapshot
guardado (`obtener_keys_ya_medidas()`) y se procesan solo las pendientes.
Correr este script de nuevo más adelante -- cuando haya HU nuevas con
customfield_10428 recién cargado -- es, sin un modo aparte, exactamente el
mecanismo que también cubre "ir sumando la muestra al día" que el usuario
planteaba como alternativa: es el mismo comando, no dos.

Cada cohorte se guarda en la base ANTES de pasar a la siguiente (no todo al
final): si el proceso se corta a mitad de camino, lo ya guardado no se
pierde y la próxima corrida retoma desde la cohorte pendiente. Si UNA
cohorte falla completa (ej. Xray caído a mitad de la corrida), se reporta y
se sigue con la siguiente -- no se guarda nada parcial de esa cohorte (cada
HU se persiste recién cuando `ejecutar_seguimiento()` ya terminó de
calcular sus índices), así que un reintento posterior la vuelve a procesar
entera, nunca a medias.

Costo de la cobertura real (IA): la inferencia corre local sobre Ollama, así
que el costo es tiempo de CPU y no dinero, incluso para varias decenas de HU.
Por eso este script la calcula SIEMPRE (a diferencia de la casilla opcional
de la página en vivo) -- es justo el número que motivó guardar este
histórico. El resultado queda congelado en el snapshot: nunca se recalcula
sola en corridas futuras (ver docstring de `SeguimientoHUMetricasORM` sobre
por qué es append-only).

Descubrimiento de HU (2026-09-02, actualizado): el filtro base
`customfield_10428 is not EMPTY` sin acotar por issuetype/proyecto llegó a
matchear miles de issues (ver el docstring anterior de este archivo y de
`application/seguimiento/motor.py::CAMPO_FECHA_CERTIFICACION_TERMINADA`).
El usuario armó y validó un JQL propio, más preciso, anclado en el
historial de cambios de estado en vez del customfield -- se pasa entero
con `--jql-completo` y REEMPLAZA el filtro base (no se combina con
`--desde`/`--hasta`/`--jql-extra`, que quedan para el caso sin JQL propio).
Antes de gastar tokens de IA con este script, conviene chequear el alcance
gratis con `scripts/diagnosticar_alcance_seguimiento_historico.py
--jql-completo "..."` (mismo parámetro, sin costo -- no llama a
`ejecutar_seguimiento()`), o simplemente mirar la cantidad de "HU
candidatas encontradas" que este script imprime ANTES de empezar a
procesar cohortes (recién ahí arranca el gasto de IA) y cortar con Ctrl+C
si el número no cierra.

Uso (desde la raíz del proyecto, con el venv activado):

    python scripts\\procesar_seguimiento_historico.py
    python scripts\\procesar_seguimiento_historico.py --tamano-cohorte 5
    python scripts\\procesar_seguimiento_historico.py --desde 2026-01-01 --hasta 2026-06-30
    python scripts\\procesar_seguimiento_historico.py --jql-extra "project not in (PRJ-16, PRJ-11, PRJ-07)"
    python scripts\\procesar_seguimiento_historico.py --jql-completo "type = Historia AND status CHANGED TO \\"Certificación Terminada\\" DURING (\\"2026-01-01\\", \\"2026-10-31\\") AND project NOT IN (PRJ-12, PRJ-11, PRJ-07, PRJ-09) AND fixVersion IS NOT EMPTY AND \\"Story Points\\" is not EMPTY AND key not in (HU-382, HU-442, HU-439, HU-414, HU-378)"

2026-09-02 (segunda corrida): El requerimiento pide sumar al histórico también
las HU que llegaron a "En producción" (no solo "Certificación Terminada"),
sin tope superior de fecha -- JQL vigente para esta corrida:

    python scripts\\procesar_seguimiento_historico.py --jql-completo "type = Historia AND status in ('Certificación Terminada','En producción') AND 'Fin En certificación' >= 2026-05-01 AND project NOT IN (PRJ-12, PRJ-11, PRJ-07, PRJ-09) And 'Story Points' is not EMPTY And key not in (HU-382,HU-442, HU-439, HU-414,HU-378)"

Como la tabla es append-only y `obtener_keys_ya_medidas()` salta lo que ya
tiene snapshot, correr esto no toca las 98 filas ya validadas -- solo suma
las HU nuevas que matcheen este JQL más amplio.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from application.seguimiento.motor import buscar_hu_certificadas, ejecutar_seguimiento
from infrastructure.config import cargar_configuracion_jira, cargar_configuracion_xray
from infrastructure.db.seguimiento_metricas import guardar_snapshot_hu, obtener_keys_ya_medidas

_TAMANO_COHORTE_DEFAULT = 10


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill cronológico de seguimiento_hu_metricas, anclado en customfield_10428.",
    )
    parser.add_argument(
        "--tamano-cohorte", type=int, default=_TAMANO_COHORTE_DEFAULT,
        help=f"HU por cohorte (default {_TAMANO_COHORTE_DEFAULT}; el usuario mencionó 5 o 10).",
    )
    parser.add_argument(
        "--desde", type=date.fromisoformat, default=None,
        help="Fecha mínima de customfield_10428 (YYYY-MM-DD), opcional.",
    )
    parser.add_argument(
        "--hasta", type=date.fromisoformat, default=None,
        help="Fecha máxima de customfield_10428 (YYYY-MM-DD), opcional.",
    )
    parser.add_argument(
        "--jql-extra", type=str, default=None,
        help='Filtro JQL adicional con AND, ej. "project not in (PRJ-16, PRJ-11, PRJ-07)".',
    )
    parser.add_argument(
        "--jql-completo", type=str, default=None,
        help=(
            "JQL completo que REEMPLAZA el filtro base (customfield_10428 is not "
            "EMPTY + --desde/--hasta/--jql-extra) -- se usa tal cual, sin agregarle "
            "nada. No combinar con --desde/--hasta/--jql-extra."
        ),
    )
    return parser.parse_args()


def _cargar_credenciales() -> dict:
    jira = cargar_configuracion_jira()
    xray = cargar_configuracion_xray()
    return {
        "jira_base_url": jira.base_url, "jira_email": jira.email, "jira_api_token": jira.api_token,
        "xray_client_id": xray.client_id, "xray_client_secret": xray.client_secret,
    }


def _dividir_en_cohortes(items: list, tamano: int) -> list[list]:
    return [items[i:i + tamano] for i in range(0, len(items), tamano)]


def _progreso_consola(etapa: str, hecho: int, total: int, texto: str) -> None:
    print(f"    [{etapa}] ({hecho}/{total}) {texto}")


def main() -> None:
    args = _parsear_argumentos()
    if args.tamano_cohorte < 1:
        raise SystemExit("--tamano-cohorte debe ser >= 1.")
    if args.jql_completo and (args.desde or args.hasta or args.jql_extra):
        raise SystemExit(
            "--jql-completo reemplaza el filtro entero -- no lo combines con "
            "--desde/--hasta/--jql-extra."
        )

    creds = _cargar_credenciales()

    if args.jql_completo:
        print("Buscando HU con el JQL completo provisto (--jql-completo)...")
    else:
        print("Buscando HU con customfield_10428 (Fin En certificación) cargado...")
    candidatas = buscar_hu_certificadas(
        creds, desde=args.desde, hasta=args.hasta, jql_extra=args.jql_extra, jql_completo=args.jql_completo,
    )
    print(f"{len(candidatas)} HU candidatas encontradas (ordenadas de más antigua a más nueva).")

    sin_fecha = sum(1 for c in candidatas if c["fecha_certificacion_terminada"] is None)
    if sin_fecha:
        print(
            f"  AVISO: {sin_fecha} vinieron sin valor utilizable en customfield_10428 pese al filtro "
            "'is not EMPTY' -- quedan al final del orden, revisar a mano si conviene."
        )

    ya_medidas = obtener_keys_ya_medidas()
    pendientes = [c for c in candidatas if c["key"] not in ya_medidas]
    print(f"{len(ya_medidas)} ya tenían snapshot guardado -- quedan {len(pendientes)} pendientes.")

    if not pendientes:
        print("Nada pendiente.")
        return

    cohortes = _dividir_en_cohortes(pendientes, args.tamano_cohorte)
    print(f"Se procesarán en {len(cohortes)} cohortes de hasta {args.tamano_cohorte} HU cada una.\n")

    total_guardadas = 0
    total_excluidas_sin_criterios = 0
    total_fallidas_al_guardar = 0
    total_cohortes_fallidas = 0

    for i, cohorte in enumerate(cohortes, start=1):
        keys = [c["key"] for c in cohorte]
        fechas_por_key = {c["key"]: c["fecha_certificacion_terminada"] for c in cohorte}
        print(f"=== Cohorte {i}/{len(cohortes)}: {keys} ===")

        jql = "key in (" + ", ".join(keys) + ")"
        try:
            df = ejecutar_seguimiento(
                jql, creds, calcular_cobertura_ia=True, on_progreso=_progreso_consola,
            )
        except Exception as exc:
            total_cohortes_fallidas += 1
            print(f"  ERROR procesando la cohorte completa -- se reintentará entera en la próxima corrida: {exc}\n")
            continue

        if df.empty:
            print("  (sin resultados para esta cohorte)\n")
            continue

        for fila_dict in df.to_dict(orient="records"):
            num_criterios = fila_dict.get("num_criterios_identificados") or 0
            if num_criterios <= 0:
                total_excluidas_sin_criterios += 1
                print(f"  {fila_dict['hu_key']}: sin criterios detectables -- no se guarda ().")
                continue
            try:
                guardar_snapshot_hu(fila_dict, fechas_por_key.get(fila_dict["hu_key"]))
            except Exception as exc:


                total_fallidas_al_guardar += 1
                print(f"  {fila_dict['hu_key']}: ERROR al guardar, se reintentará en la próxima corrida: {exc}")
                continue
            total_guardadas += 1
            print(f"  {fila_dict['hu_key']}: guardada.")
        print()

    print(
        f"Listo. {total_guardadas} HU guardadas en seguimiento_hu_metricas, "
        f"{total_excluidas_sin_criterios} excluidas por no tener criterios detectables, "
        f"{total_fallidas_al_guardar} fallaron al guardar (quedan pendientes para la próxima corrida), "
        f"{total_cohortes_fallidas} cohortes fallidas por completo (reintentar corriendo el script de nuevo)."
    )


if __name__ == "__main__":
    main()
