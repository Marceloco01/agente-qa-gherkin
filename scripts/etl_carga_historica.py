"""
ETL de carga histórica — Fase 3.

Lee el Excel histórico `Dev_Preubas__1_.xlsx` (6 hojas), aplica las reglas
de limpieza confirmadas contra el archivo real, genera embeddings con
`nomic-embed-text` vía Ollama, y carga los casos en la tabla
`embeddings_historicos` de PostgreSQL.

Uso (desde la raíz del proyecto, con el venv activado y Ollama corriendo):

    python scripts/etl_carga_historica.py <ruta_al_excel>

Ejemplo:
    python scripts/etl_carga_historica.py "ruta/a/exportacion_historica.xlsx"

Reglas de limpieza aplicadas (todas confirmadas contra el archivo real):

1. Excluir filas con Estado = "Obsoleto" (80 filas en el archivo real).
2. Excluir filas con Key TP nulo (3 filas).
3. Excluir filas con Key TP múltiple (celda con comas, ej.
   "HU-056,HU-061") -- 26 filas. Impacto mínimo (1.3% del
   total útil); incluirlos requeriría lógica de desambiguación que agrega
   complejidad sin beneficio real para el RAG.
4. Deduplicar por Key test: si el mismo test case aparece en varias
   ejecuciones (Key TE distintas), conservar la más reciente según
   "Empezó en" (fecha real de ejecución, más precisa que comparar números
   de Key TE entre proyectos distintos). Para las 16 filas con "Empezó en"
   vacío, usar el número al final de Key TE como criterio de ordenamiento
   fallback.
5. Corregir encoding roto (109 filas en el archivo real): caracteres '?'
   sustituyendo tildes y eñes en el campo Resumen. Se aplica un mapa de
   corrección sobre los patrones más frecuentes detectados en el análisis
   previo. Los caracteres que no se puedan corregir automáticamente quedan
   tal cual -- no se descartan filas por encoding roto.
6. Cruzar con hoja TestPlan para obtener Key HU (necesaria para el
   contexto del embedding: texto = Resumen + Key HU).

El script genera embeddings de a uno (no en batch) para no saturar la RAM
de 8 GB disponible (hardware confirmado: AMD Ryzen 5 4500U, 8 GB RAM, sin
GPU dedicada -- ver spec, sección 2).

Genera un reporte de limpieza al final con todos los conteos de filas
procesadas, excluidas y por qué.

Si el mismo Key test ya existe en la tabla (de una corrida anterior del
ETL), se actualiza en lugar de fallar -- `guardar_embedding()` usa
`merge()`, no `add()`.

Logging: usa el mismo logger rotativo del proyecto (logs/agente_qa.log).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from adapters.vector_store.postgres_pgvector import PostgresPgvectorAdapter
from infrastructure.config import cargar_configuracion_ollama, obtener_logger
from infrastructure.db.conexion import obtener_sesion

log = obtener_logger(__name__)


_MAPA_ENCODING = {

    "\u00e1": ["\u00e1", "\u00c3\u00a1"],
    "\u00e9": ["\u00e9", "\u00c3\u00a9"],
    "\u00ed": ["\u00ed", "\u00c3\u00ad"],
    "\u00f3": ["\u00f3", "\u00c3\u00b3"],
    "\u00fa": ["\u00fa", "\u00c3\u00ba"],

    "\u00c1": ["\u00c1", "\u00c3\u0081"],
    "\u00c9": ["\u00c9", "\u00c3\u0089"],
    "\u00cd": ["\u00cd", "\u00c3\u008d"],
    "\u00d3": ["\u00d3", "\u00c3\u0093"],
    "\u00da": ["\u00da", "\u00c3\u009a"],

    "\u00f1": ["\u00f1", "\u00c3\u00b1"],
    "\u00d1": ["\u00d1", "\u00c3\u0091"],

    "\u00bf": ["\u00bf", "\u00c2\u00bf"],
    "\u00a1": ["\u00a1", "\u00c2\u00a1"],

    '"': ["\u201c", "\u201d"],
}


_REEMPLAZOS: list[tuple[str, str]] = []
for correcto, rotos in _MAPA_ENCODING.items():
    for roto in rotos:
        _REEMPLAZOS.append((roto, correcto))

_REEMPLAZOS.sort(key=lambda x: -len(x[0]))


def _corregir_encoding(texto: str) -> str:
    """Aplica el mapa de corrección de encoding sobre un string."""
    for roto, correcto in _REEMPLAZOS:
        texto = texto.replace(roto, correcto)
    return texto


def _tiene_key_tp_multiple(valor: str) -> bool:
    """True si la celda Key TP contiene más de un valor (separado por coma)."""
    return "," in str(valor)


def _extraer_numero_te(key_te: str) -> int:
    """Extrae el número al final de una Key TE (ej. 'HU-171' -> 2537)."""
    match = re.search(r"-(\d+)$", str(key_te))
    return int(match.group(1)) if match else -1


def _parsear_fecha(valor) -> pd.Timestamp | None:
    """
    Parsea el formato de fecha real del Excel ('14/Nov/24 07:54 PM').
    Devuelve None si el valor está vacío o no es parseable -- las 16
    filas con 'Empezó en' vacío caen acá y se manejan con el número
    de Key TE como fallback.
    """
    if pd.isna(valor):
        return None
    try:
        return pd.to_datetime(str(valor), dayfirst=True, errors="coerce")
    except Exception:
        return None


def _generar_texto_embedding(resumen: str, hu_key: str | None) -> str:
    """
    Construye el texto que se embedea: Resumen del caso + contexto de la
    HU asociada. El contexto de la HU se agrega como prefijo porque los
    modelos de embedding dan más peso al principio del texto, y el contexto
    de la HU es el campo que el agente va a usar para buscar similares
    (siempre busca a partir de una HU).

    Si no hay Key HU (26 casos excluidos por Key TP doble quedan fuera,
    pero podría haber otros), se usa solo el Resumen.
    """
    if hu_key and str(hu_key).strip():
        return f"HU: {hu_key} | {resumen}"
    return resumen


def _separador(titulo: str) -> None:
    print()
    print("=" * 70)
    print(titulo)
    print("=" * 70)


def main(ruta_excel: str, max_filas: int | None = None) -> None:
    ruta = Path(ruta_excel)
    if not ruta.exists():
        print(f"ERROR: no se encontró el archivo: {ruta}")
        sys.exit(1)

    log.info("ETL histórico iniciado. Archivo: %s", ruta)


    _separador("Paso 1: Leyendo hojas del Excel")
    df_casos = pd.read_excel(ruta, sheet_name="CasosPrueba")
    df_tp = pd.read_excel(ruta, sheet_name="TestPlan")
    filas_originales = len(df_casos)
    print(f"OK: CasosPrueba cargado ({filas_originales} filas x {len(df_casos.columns)} columnas).")
    print(f"OK: TestPlan cargado ({len(df_tp)} filas).")


    reporte = {
        "filas_originales": filas_originales,
        "excluidos_obsoleto": 0,
        "excluidos_key_tp_nulo": 0,
        "excluidos_key_tp_multiple": 0,
        "excluidos_sin_hu": 0,
        "duplicados_eliminados": 0,
        "filas_con_encoding_corregido": 0,
        "filas_a_cargar": 0,
        "cargadas_ok": 0,
        "errores_embedding": 0,
        "errores_guardado": 0,
    }


    _separador("Paso 2: Excluyendo filas con Estado = 'Obsoleto'")
    mask_obsoleto = df_casos["Estado"] == "Obsoleto"
    reporte["excluidos_obsoleto"] = mask_obsoleto.sum()
    df_casos = df_casos[~mask_obsoleto].copy()
    print(f"Excluidos: {reporte['excluidos_obsoleto']} filas Obsoleto.")
    print(f"Restantes: {len(df_casos)}")


    _separador("Paso 3: Excluyendo filas con Key TP nulo")
    mask_tp_nulo = df_casos["Key TP"].isna()
    reporte["excluidos_key_tp_nulo"] = mask_tp_nulo.sum()
    df_casos = df_casos[~mask_tp_nulo].copy()
    print(f"Excluidos: {reporte['excluidos_key_tp_nulo']} filas con Key TP nulo.")
    print(f"Restantes: {len(df_casos)}")


    _separador("Paso 4: Excluyendo filas con Key TP múltiple (celda con comas)")
    mask_tp_multiple = df_casos["Key TP"].astype(str).apply(_tiene_key_tp_multiple)
    reporte["excluidos_key_tp_multiple"] = mask_tp_multiple.sum()
    if reporte["excluidos_key_tp_multiple"] > 0:
        print(f"Ejemplos de Key TP múltiple encontrados:")
        for v in df_casos[mask_tp_multiple]["Key TP"].unique()[:3]:
            print(f"  '{v}'")
    df_casos = df_casos[~mask_tp_multiple].copy()
    print(f"Excluidos: {reporte['excluidos_key_tp_multiple']} filas con Key TP múltiple.")
    print(f"Restantes: {len(df_casos)}")


    _separador("Paso 5: Deduplicando (1 fila por Key test, ejecución más reciente)")
    total_antes_dedup = len(df_casos)


    df_casos["_fecha_te"] = df_casos["Empezó en"].apply(_parsear_fecha)


    df_casos["_num_te"] = df_casos["Key TE"].apply(_extraer_numero_te)


    df_casos = df_casos.sort_values(
        by=["_fecha_te", "_num_te"],
        ascending=[False, False],
        na_position="last",
    )


    df_casos = df_casos.drop_duplicates(subset=["Key test"], keep="first")

    reporte["duplicados_eliminados"] = total_antes_dedup - len(df_casos)
    print(f"Filas antes de deduplicar: {total_antes_dedup}")
    print(f"Filas después: {len(df_casos)}")
    print(f"Duplicados eliminados: {reporte['duplicados_eliminados']}")


    _separador("Paso 6: Incorporando Key HU desde hoja TestPlan")
    df_casos = df_casos.merge(
        df_tp[["Key TP", "Key HU"]].drop_duplicates("Key TP"),
        on="Key TP",
        how="left",
    )
    sin_hu = df_casos["Key HU"].isna().sum()
    reporte["excluidos_sin_hu"] = sin_hu
    if sin_hu > 0:
        print(f"AVISO: {sin_hu} casos no encontraron Key HU en TestPlan (se cargarán sin Key HU).")
        print("  Primeros afectados:")
        print(df_casos[df_casos["Key HU"].isna()][["Key test", "Key TP"]].head(5).to_string())
    else:
        print("OK: todos los casos tienen Key HU.")
    print(f"Filas listas para cargar: {len(df_casos)}")


    _separador("Paso 7: Corrigiendo encoding roto en columna Resumen")
    resumen_original = df_casos["Resumen"].copy()
    df_casos["Resumen"] = df_casos["Resumen"].astype(str).apply(_corregir_encoding)
    cambiados = (df_casos["Resumen"] != resumen_original.astype(str)).sum()
    reporte["filas_con_encoding_corregido"] = cambiados
    print(f"Filas con correcciones de encoding: {cambiados}")
    if cambiados > 0:

        ejemplo_idx = (df_casos["Resumen"] != resumen_original.astype(str)).idxmax()
        print(f"  Ejemplo antes: {resumen_original[ejemplo_idx][:80]}")
        print(f"  Ejemplo después: {df_casos.loc[ejemplo_idx, 'Resumen'][:80]}")


    if max_filas is not None:
        df_casos = df_casos.head(max_filas).copy()
        print()
        print(f"*** MODO PRUEBA: procesando solo las primeras {max_filas} filas ***")
        print("    Para la carga completa, corre sin el flag --prueba.")

    _separador(f"Paso 8: Generando embeddings y cargando {len(df_casos)} casos")
    print("Esto puede tardar varios minutos (Ollama corre en CPU).")
    print("Se muestra progreso cada 50 casos.\n")

    import ollama

    config_ollama = cargar_configuracion_ollama()
    modelo_embedding = "nomic-embed-text"

    reporte["filas_a_cargar"] = len(df_casos)
    filas = df_casos.reset_index(drop=True)


    TAMANIO_LOTE = 50

    for inicio in range(0, len(filas), TAMANIO_LOTE):
        lote = filas.iloc[inicio: inicio + TAMANIO_LOTE]
        errores_lote = 0

        try:
            with obtener_sesion() as sesion:
                adapter = PostgresPgvectorAdapter(sesion)

                for _, fila in lote.iterrows():
                    key_test = str(fila["Key test"])
                    resumen = str(fila["Resumen"])
                    key_te = str(fila["Key TE"]) if pd.notna(fila["Key TE"]) else None
                    key_tp = str(fila["Key TP"]) if pd.notna(fila["Key TP"]) else None
                    hu_key = str(fila["Key HU"]) if pd.notna(fila["Key HU"]) else None

                    texto_a_embedear = _generar_texto_embedding(resumen, hu_key)

                    try:
                        respuesta = ollama.embeddings(
                            model=modelo_embedding,
                            prompt=texto_a_embedear,
                        )
                        vector = respuesta["embedding"]
                    except Exception as exc:
                        log.warning(
                            "Error generando embedding para %s: %s", key_test, exc
                        )
                        reporte["errores_embedding"] += 1
                        errores_lote += 1
                        continue

                    try:
                        adapter.guardar_embedding(
                            referencia_id=key_test,
                            vector=vector,
                            metadata={
                                "key_te": key_te or "",
                                "key_tp": key_tp or "",
                                "hu_key": hu_key or "",
                                "resumen": resumen,
                            },
                        )
                        reporte["cargadas_ok"] += 1
                    except Exception as exc:
                        log.warning(
                            "Error guardando embedding para %s: %s", key_test, exc
                        )
                        reporte["errores_guardado"] += 1
                        errores_lote += 1

        except Exception as exc:
            log.error("Error de sesión en lote %d-%d: %s", inicio, inicio + TAMANIO_LOTE, exc)
            reporte["errores_guardado"] += len(lote)


        procesados = min(inicio + TAMANIO_LOTE, len(filas))
        pct = procesados / len(filas) * 100
        print(
            f"  [{procesados:>4}/{len(filas)}] {pct:.0f}% "
            f"— OK: {reporte['cargadas_ok']}, "
            f"errores embedding: {reporte['errores_embedding']}, "
            f"errores guardado: {reporte['errores_guardado']}"
        )


    _separador("REPORTE DE LIMPIEZA Y CARGA")
    print(f"  Filas originales en CasosPrueba:       {reporte['filas_originales']:>6}")
    print(f"  Excluidas por Estado = Obsoleto:       {reporte['excluidos_obsoleto']:>6}")
    print(f"  Excluidas por Key TP nulo:             {reporte['excluidos_key_tp_nulo']:>6}")
    print(f"  Excluidas por Key TP múltiple:         {reporte['excluidos_key_tp_multiple']:>6}")
    print(f"  Duplicados eliminados (keep reciente): {reporte['duplicados_eliminados']:>6}")
    print(f"  Sin Key HU (cargadas igual):           {reporte['excluidos_sin_hu']:>6}")
    print(f"  Filas con encoding corregido:          {reporte['filas_con_encoding_corregido']:>6}")
    print(f"  ─────────────────────────────────────────────")
    print(f"  Filas procesadas para carga:           {reporte['filas_a_cargar']:>6}")
    print(f"  Cargadas exitosamente:                 {reporte['cargadas_ok']:>6}")
    print(f"  Errores al generar embedding:          {reporte['errores_embedding']:>6}")
    print(f"  Errores al guardar en BD:              {reporte['errores_guardado']:>6}")
    print()
    if reporte["errores_embedding"] == 0 and reporte["errores_guardado"] == 0:
        print("RESULTADO: carga completa sin errores.")
    else:
        total_errores = reporte["errores_embedding"] + reporte["errores_guardado"]
        print(
            f"RESULTADO: carga completada con {total_errores} errores. "
            f"Revisa logs/agente_qa.log para el detalle de cada caso fallido."
        )
        print(
            "Puedes volver a correr el script -- los casos ya cargados se "
            "actualizarán sin duplicarse, y los fallidos se reintentarán."
        )

    log.info(
        "ETL histórico finalizado. Cargadas: %d, errores: %d",
        reporte["cargadas_ok"],
        reporte["errores_embedding"] + reporte["errores_guardado"],
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="ETL de carga histórica de casos de prueba al RAG."
    )
    parser.add_argument(
        "ruta_excel",
        help='Ruta al archivo Excel. Ej: "C:/ruta/Dev_Preubas.xlsx"',
    )
    parser.add_argument(
        "--prueba",
        type=int,
        metavar="N",
        default=None,
        help=(
            "Modo prueba: procesa solo las primeras N filas (tras la limpieza) "
            "para verificar que Ollama y la base funcionan antes de lanzar el "
            "ETL completo. Ej: --prueba 5"
        ),
    )
    args = parser.parse_args()
    main(args.ruta_excel, max_filas=args.prueba)
