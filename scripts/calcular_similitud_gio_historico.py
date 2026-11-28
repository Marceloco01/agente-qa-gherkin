"""
Compara los casos que generó Gio contra los casos funcionales históricos que
escribió el equipo de la organización (Fase 4.3).

    python scripts/calcular_similitud_gio_historico.py

**No clasifica en grupos, y eso es deliberado.** Se intentó tres veces y las
tres dieron titulares incompatibles sobre los mismos datos:

  1. Umbrales absolutos 0.85 / 0.60  ->  25.3% replicado, 0% novedoso.
     El 0.60 estaba por debajo del piso entero de la distribución (mínimo
     real 0.70): la categoría era inalcanzable por aritmética.
  2. Nula de pares al azar           ->  92.7% replicado, 0% novedoso.
     Comparaba un MÁXIMO sobre 455 candidatos contra pares sueltos. Simulado
     con ruido puro da 100% "replicado" sin que haya ninguna señal.
  3. Nula de mejor-match humano      ->  0% replicado, 61.4% novedoso.
     El estadístico ya era el correcto, pero la nula está contaminada: el p95
     del mejor match humano es 1.0000 EXACTO, o sea que al menos el 5% de los
     casos históricos tiene un duplicado literal en otra HU.

Un indicador que se mueve de 25% a 92.7% a 0% según cómo se calibre no
sostiene una afirmación de tesis. Así que este script ya no clasifica: mide
las dos distribuciones y las deja una al lado de la otra. La comparación no
necesita ningún umbral y por eso no se puede romper eligiendo mal uno.

Salidas:
  similitud_gio_historico.csv  -- un caso de Gio por fila, con su mejor match
                                  histórico y en qué percentil de la
                                  distribución humana cae ese parecido.
  distribucion_similitud.csv   -- las dos distribuciones, para graficarlas sin
                                  recalcular embeddings.
  duplicados_historico.csv     -- pares de casos históricos casi idénticos,
                                  para revisar a mano la redundancia del
                                  corpus antes de afirmarla.

Los históricos son los FUNCIONALES, no los 771: el agente no genera
verificaciones normativas, así que medir su parecido contra compuertas de
gobierno no compararía nada. Los embeddings corren por Ollama
(`nomic-embed-text`, el mismo del RAG) y se cachean en disco: cero créditos.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from adapters.llm.ollama_provider import OllamaProvider
from adapters.tesis.csv_tesis_repository import CsvTesisRepository
from infrastructure.config import obtener_logger
from infrastructure.reportes.pretest_posttest import (
    _clasificar_historico,
    _leer,
    _titulo_normalizado,
)

_log = obtener_logger(__name__)

SALIDA = "similitud_gio_historico.csv"
SALIDA_DIST = "distribucion_similitud.csv"
SALIDA_DUP = "duplicados_historico.csv"
CACHE = "similitud_embeddings.cache.json"


UMBRAL_DUPLICADO = 0.95


def _coseno(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return num / (na * nb) if na and nb else 0.0


def _percentil_de(valor: float, distribucion: list[float]) -> float:
    """Qué porcentaje de `distribucion` queda por debajo de `valor`."""
    if not distribucion:
        return 0.0
    return sum(1 for x in distribucion if x < valor) / len(distribucion) * 100


def _cargar_cache() -> dict:
    ruta = RAIZ / CACHE
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        _log.warning("Caché ilegible, se recalcula todo.")
        return {}


def main() -> int:

    base = {f.hu_key for f in CsvTesisRepository(RAIZ).obtener_corpus().filas}
    _log.info("Base del estudio: %d HU", len(base))

    crudo = [f for archivo in ("historico_gherkin_texto_57hu.csv",
                               "historico_gherkin_texto_septiembre.csv")
             for f in _leer(RAIZ, archivo)]
    titulos_gobierno, _ = _clasificar_historico(crudo)
    historicos = [
        {"hu_key": f.get("hu_key", ""), "titulo": f.get("test_summary", ""),
         "texto": f"{f.get('test_summary', '')}\n{f.get('gherkin_texto', '')}".strip()}
        for f in crudo
        if (f.get("hu_key") or "").strip() in base
        and _titulo_normalizado(f.get("test_summary")) not in titulos_gobierno
        and (f.get("gherkin_texto") or "").strip()
    ]
    gio = [
        {"hu_key": (f.get("hu_key") or "").strip(), "titulo": f.get("titulo", ""),
         "estado": f.get("estado_final", ""),
         "texto": f"{f.get('titulo', '')}\n{f.get('gherkin_final', '')}".strip()}
        for f in _leer(RAIZ, "revision_manual_retrospectiva_test_cases.csv")
        if (f.get("hu_key") or "").strip() in base
        and (f.get("gherkin_final") or "").strip()
    ]
    if not historicos or not gio:
        _log.error("Faltan datos: %d históricos, %d de Gio", len(historicos), len(gio))
        return 1
    _log.info("Históricos funcionales: %d · casos de Gio: %d", len(historicos), len(gio))

    cache = _cargar_cache()
    proveedor = None
    nuevos = 0

    def embeber(items: list[dict], etiqueta: str) -> list[list[float]]:
        nonlocal proveedor, nuevos
        salida = []
        for i, it in enumerate(items, 1):
            clave = hashlib.sha1(it["texto"].encode("utf-8")).hexdigest()
            if clave not in cache:
                if proveedor is None:
                    proveedor = OllamaProvider()
                cache[clave] = proveedor.generar_embedding(it["texto"])
                nuevos += 1
            salida.append(cache[clave])
            if i % 100 == 0 or i == len(items):
                _log.info("  %s: %d/%d", etiqueta, i, len(items))
        return salida

    emb_hist = embeber(historicos, "históricos")
    emb_gio = embeber(gio, "Gio")
    if nuevos:
        (RAIZ / CACHE).write_text(json.dumps(cache), encoding="utf-8")
        _log.info("Caché actualizado: %d embeddings nuevos", nuevos)


    _log.info("Midiendo el lado humano (%d casos)...", len(historicos))
    nula: list[float] = []
    duplicados = []
    for i, vi in enumerate(emb_hist):
        mejor, idx = -1.0, -1
        for j, vj in enumerate(emb_hist):
            if i == j:
                continue
            s = _coseno(vi, vj)
            if s > mejor:
                mejor, idx = s, j
            if s >= UMBRAL_DUPLICADO and i < j:
                duplicados.append({
                    "similitud": round(s, 4),
                    "hu_a": historicos[i]["hu_key"], "caso_a": historicos[i]["titulo"],
                    "hu_b": historicos[j]["hu_key"], "caso_b": historicos[j]["titulo"],
                    "misma_hu": "si" if historicos[i]["hu_key"] == historicos[j]["hu_key"] else "no",
                    "identico": "si" if s >= 0.9999 else "no",
                })
        if idx >= 0:
            nula.append(mejor)
    nula.sort()


    filas = []
    for caso, vector in zip(gio, emb_gio):
        mejor, mejor_h = -1.0, None
        for h, vh in zip(historicos, emb_hist):
            s = _coseno(vector, vh)
            if s > mejor:
                mejor, mejor_h = s, h
        filas.append({
            "hu_key": caso["hu_key"],
            "caso_gio": caso["titulo"],
            "estado_revision": caso["estado"],
            "aprobado": "si" if caso["estado"].strip().lower() == "aprobado" else "no",
            "mejor_match_hu": mejor_h["hu_key"] if mejor_h else "",
            "mejor_match_titulo": mejor_h["titulo"] if mejor_h else "",
            "similitud": round(mejor, 4),


            "percentil_vs_humano": round(_percentil_de(mejor, nula), 1),
            "misma_hu": "si" if mejor_h and mejor_h["hu_key"] == caso["hu_key"] else "no",
        })

    with (RAIZ / SALIDA).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader(); w.writerows(filas)

    with (RAIZ / SALIDA_DIST).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["lado", "similitud"])
        w.writeheader()
        w.writerows([{"lado": "humano", "similitud": round(v, 4)} for v in nula])
        w.writerows([{"lado": "gio", "similitud": x["similitud"]} for x in filas])

    duplicados.sort(key=lambda d: -d["similitud"])
    with (RAIZ / SALIDA_DUP).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(duplicados[0].keys()) if duplicados
                           else ["similitud", "hu_a", "caso_a", "hu_b", "caso_b",
                                 "misma_hu", "identico"])
        w.writeheader(); w.writerows(duplicados)

    def pct(d: list[float], p: int) -> float:
        return d[min(len(d) - 1, int(len(d) * p / 100))] if d else 0.0

    propios = sorted(x["similitud"] for x in filas)
    print(f"\nEscrito: {SALIDA}, {SALIDA_DIST}, {SALIDA_DUP}")
    print("\nLAS DOS DISTRIBUCIONES — parecido con lo más cercano del corpus histórico")
    print(f"  {'':22s} {'p5':>8s} {'mediana':>8s} {'p95':>8s} {'máximo':>8s}")
    print(f"  {'caso HUMANO':22s} {pct(nula, 5):8.4f} {pct(nula, 50):8.4f} "
          f"{pct(nula, 95):8.4f} {nula[-1]:8.4f}   (n={len(nula)})")
    print(f"  {'caso de GIO':22s} {pct(propios, 5):8.4f} {pct(propios, 50):8.4f} "
          f"{pct(propios, 95):8.4f} {propios[-1]:8.4f}   (n={len(propios)})")

    aprob = sorted(x["similitud"] for x in filas if x["aprobado"] == "si")
    if aprob:
        print(f"  {'  solo aprobados':22s} {pct(aprob, 5):8.4f} {pct(aprob, 50):8.4f} "
              f"{pct(aprob, 95):8.4f} {aprob[-1]:8.4f}   (n={len(aprob)})")

    identicos = [d for d in duplicados if d["identico"] == "si"]
    distintas_hu = [d for d in duplicados if d["misma_hu"] == "no"]
    print(f"\nREDUNDANCIA DEL CORPUS HISTÓRICO (revisar {SALIDA_DUP} a mano)")
    print(f"  pares con similitud >= {UMBRAL_DUPLICADO}: {len(duplicados)}")
    print(f"     de los cuales IDÉNTICOS (>= 0.9999): {len(identicos)}")
    print(f"     entre HU DISTINTAS: {len(distintas_hu)}")
    casos_en_dup = len({d[k] + d[v] for d in duplicados
                        for k, v in (("hu_a", "caso_a"), ("hu_b", "caso_b"))})
    print(f"  casos históricos involucrados: {casos_en_dup} de {len(historicos)} "
          f"({casos_en_dup / len(historicos) * 100:.1f}%)")
    print(f"\nCompuertas de gobierno generadas por Gio: 0 de {len(gio)}.")
    print("\nNo se clasifica en grupos: ver el docstring de este script para el "
          "detalle de por qué.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
