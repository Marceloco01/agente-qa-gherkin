"""
Análisis retrospectivo (tesis) — Conteo determinístico de "criterios de aceptación" por HU,
para el índice de cobertura del libro [29] citado en domain/models.py::TipoCobertura
(situaciones cubiertas / situaciones identificadas × 100).

Decisión metodológica (2026-08-31, con el usuario): "situaciones identificadas"
= criterios de aceptación de la HU. Se decidió CONTARLOS DE FORMA
DETERMINÍSTICA (regex sobre el texto real de Jira), NO pedirle al LLM que los
cuente -- este proyecto ya documentó varias veces que el LLM es no
determinista (ver el flip de `HU-394` en la sección "Ejecución real de
ambos scripts..." de la documentación), y usar el LLM para el DENOMINADOR de
una métrica de tesis introduciría exactamente ese problema en el número que
se va a defender. Un conteo por regex es reproducible: la misma HU da
siempre el mismo número.

Cómo cuenta: **ya no tiene su propia copia de los regex**. Desde el 2026-09-06
importa `contar_criterios()` de `application/seguimiento/patrones_criterios_v2.py`,
la misma función que usa el motor de Seguimiento. Antes había tres copias de
la misma lógica (acá, en el motor, y en el módulo nuevo) y tres copias es una
copia que se desincroniza.

Los patrones, en orden (se queda con el primero que encuentre algo):

1. Líneas con etiqueta "C<n>" o "Criterio <n>" (ej. "C1:", "C2.", "Criterio 3:")
   -- confirmado como el patrón real más común en las HU de este corpus: se ve
   literalmente en el propio `vera_detalle` guardado durante la Ronda 5/6 (ej.
   "C1: Ambigüedad en 'enviar el servicio correspondiente'...").
2. Lista numerada dentro de una sección "Criterios de Aceptación" detectada
   por encabezado (ej. "1.", "2)").
3. Lista con viñetas ("-", "*", "•") dentro de esa misma sección.
4. (2026-09-06) Etiqueta por posición: cubre `[C1] ...` entre corchetes y la
   etiqueta con el cuerpo en las líneas de abajo (`Criterio 1` y el texto
   debajo). Exige al menos 2 etiquetas para no confundir una mención suelta.
5. (2026-09-06) Encabezado corto `Criterios:` + lista numerada o con viñetas.

Los 4 y 5 se evalúan DESPUÉS de los tres originales, así que ninguna HU que
ya se detectaba puede cambiar de patrón -- verificado sobre las 49 HU con
`scripts/verificar_patrones_criterios.py` antes de adoptarlos.

Si ninguno matchea, la HU queda marcada `SIN_PATRON_DETECTADO` en
vez de un cero silencioso -- 0 identificados haría que el índice de cobertura
diera división por cero o un 100% artificial, y en la práctica lo más
probable es que la HU tenga los criterios redactados en prosa corrida, no en
lista, lo cual amerita revisión manual antes de forzar un número.

IMPORTANTE -- disciplina ya establecida en este proyecto: este conteo es un
punto de partida reproducible, NO una verdad absoluta. Antes de usarlo en la
tesis, leer a mano 3-5 HU (sobre todo las que dieron `SIN_PATRON_DETECTADO` o
un número que se vea raro) para confirmar que el regex no se comió ni infló
nada -- mismo criterio de "leer contenido antes de confiar en el conteo" que
ya se aplicó para el checklist genérico del análisis retrospectivo.

Entrada (en la carpeta actual):
    retro_resultado_57hu.csv -- trae las 43 hu_key finales del análisis retrospectivo.
    Se le suman las 6 HU de `application/seguimiento/corpus_retro.py`
    (ampliación del 2026-09-06): quedaban fuera solo porque no se les
    detectaban los criterios, no por falta de casos. Ese archivo de entrada
    NO se toca -- es el registro histórico de cómo cerró el análisis retrospectivo.

Resumible con una excepción deliberada: las HU ya guardadas se reusan tal
cual (así el conteo que ya alimentó `cobertura_real_retro.csv` no puede
moverse por accidente), PERO las que quedaron en `SIN_PATRON_DETECTADO` o
`ERROR` se vuelven a traer de Jira, porque son justo las que los patrones
nuevos pueden arreglar.

Salida (en la carpeta actual):
    criterios_aceptacion_retro.csv
        hu_key, patron_usado, num_criterios_identificados, criterios_texto
        (los criterios detectados, separados por " || ", para poder
        auditarlos sin volver a Jira)

Uso (desde la raíz del proyecto, con el venv activado):

    python scripts\\contar_criterios_aceptacion_retro.py

Resumible: si se corta a mitad de camino, correr de nuevo retoma donde quedó.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.issue_tracker.jira_cloud_adapter import JiraCloudAdapter
from application.seguimiento.corpus_retro import ampliar
from application.seguimiento.patrones_criterios_v2 import contar_criterios as _contar_criterios
from infrastructure.config import cargar_configuracion_jira

_ESPERA_ENTRE_LLAMADAS_SEGUNDOS = 0.3

_ARCHIVO_ENTRADA = Path("retro_resultado_57hu.csv")
_ARCHIVO_SALIDA = Path("criterios_aceptacion_retro.csv")
_COLUMNAS_SALIDA = ["hu_key", "patron_usado", "num_criterios_identificados", "criterios_texto"]


_PATRONES_A_REINTENTAR = {"SIN_PATRON_DETECTADO", "ERROR"}


def _leer_entrada() -> list[str]:
    if not _ARCHIVO_ENTRADA.exists():
        raise SystemExit(
            f"No se encontró {_ARCHIVO_ENTRADA.resolve()} -- copiá ahí "
            "retro_resultado_57hu.csv antes de correr este script."
        )
    with _ARCHIVO_ENTRADA.open("r", newline="", encoding="utf-8") as f:
        return [fila["hu_key"] for fila in csv.DictReader(f)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cuenta criterios de aceptación por HU (solo Jira, sin costo de LLM)."
    )
    parser.add_argument(
        "--recontar-todo", action="store_true",
        help="Ignora la salida previa y vuelve a traer TODAS las HU de Jira. "
             "Se usa cuando cambia la regla de conteo y hay que aplicarla parejo "
             "a todo el corpus, no solo a lo pendiente.",
    )
    args = parser.parse_args()

    del_csv = _leer_entrada()
    keys_hu = ampliar(del_csv)
    extra = len(keys_hu) - len(del_csv)
    print(f"{len(keys_hu)} HU a procesar ({len(del_csv)} de {_ARCHIVO_ENTRADA}"
          + (f" + {extra} de la ampliación 2026-09-06)." if extra else ")."))

    ya_resueltas: dict[str, list] = {}
    a_recalcular: list[str] = []
    if args.recontar_todo:
        print("--recontar-todo: se ignora la salida previa y se recuenta el corpus "
              "entero con la regla vigente. Solo Jira, sin costo de LLM.")
    elif _ARCHIVO_SALIDA.exists():
        with _ARCHIVO_SALIDA.open("r", newline="", encoding="utf-8") as f:
            lector = csv.reader(f)
            next(lector, None)
            for fila in lector:
                if not fila:
                    continue
                if len(fila) > 1 and fila[1] in _PATRONES_A_REINTENTAR:
                    a_recalcular.append(fila[0])
                    continue
                ya_resueltas[fila[0]] = fila
        print(f"Se encontró una salida previa con {len(ya_resueltas)} HU ya "
              "procesadas -- se retoma (esas NO se recalculan, así el conteo "
              "ya usado en la cobertura no puede moverse).")
        if a_recalcular:
            print(f"  Se vuelven a traer {len(a_recalcular)} HU que habían "
                  f"quedado sin patrón o con error: {a_recalcular}")

    def _guardar() -> None:
        with _ARCHIVO_SALIDA.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_COLUMNAS_SALIDA)
            for hu_key in keys_hu:
                if hu_key in ya_resueltas:
                    writer.writerow(ya_resueltas[hu_key])

    pendientes = [k for k in keys_hu if k not in ya_resueltas]
    if not pendientes:
        print("Nada pendiente -- todas las HU ya tienen criterios contados.")
        _guardar()
        return

    config = cargar_configuracion_jira()
    adapter = JiraCloudAdapter(config.base_url, config.email, config.api_token)
    try:
        for i, hu_key in enumerate(pendientes, start=1):
            print(f"  [{i}/{len(pendientes)}] Trayendo {hu_key} de Jira...")
            try:
                hu = adapter.obtener_hu(hu_key)
            except Exception as exc:
                print(f"    ERROR trayendo {hu_key}: {exc}")
                ya_resueltas[hu_key] = [hu_key, "ERROR", "", str(exc)[:200]]
                _guardar()
                time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
                continue

            patron, criterios = _contar_criterios(hu.descripcion)
            ya_resueltas[hu_key] = [hu_key, patron, len(criterios), " || ".join(criterios)]
            _guardar()
            time.sleep(_ESPERA_ENTRE_LLAMADAS_SEGUNDOS)
    finally:
        adapter.cerrar()

    print(f"\nListo. {_ARCHIVO_SALIDA.resolve()}")
    from collections import Counter
    conteo_patrones = Counter(fila[1] for fila in ya_resueltas.values())
    print(f"Patrones usados: {dict(conteo_patrones)}")
    sin_patron = [hu for hu, fila in ya_resueltas.items() if fila[1] == "SIN_PATRON_DETECTADO"]
    if sin_patron:
        print(f"\nHU sin patrón detectado (revisar a mano): {sorted(sin_patron)}")
    print(
        "\nRecordatorio: leé a mano 3-5 filas de criterios_texto (sobre todo "
        "las de SIN_PATRON_DETECTADO o con un número que se vea raro) antes "
        "de usar este conteo en la tesis."
    )


if __name__ == "__main__":
    main()
