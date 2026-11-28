"""
Corpus comparable del análisis retrospectivo — una sola fuente de verdad para la ampliación.

El corpus original del análisis retrospectivo vive en `retro/retro_resultado_57hu.csv`
(43 HU). Ese archivo es un **registro histórico** de cómo cerró el punto y no
se toca: reescribirlo borraría la trazabilidad de lo que se midió entonces.

La ampliación del 2026-09-06 suma 6 HU que quedaban fuera únicamente porque
`contar_criterios()` no reconocía cómo estaban escritos sus criterios de
aceptación. Todas tienen las otras dos piezas que hacen falta para comparar
(Gherkin histórico del humano y casos del agente aprobados en la revisión
manual), así que lo único que las excluía era la detección.

Cómo se verificó, antes de sumarlas
-----------------------------------
`scripts/verificar_patrones_criterios.py` corrió las dos versiones del
detector sobre las 49 HU y confirmó que las **41 HU de la línea base**
(las que aportan a los 191 criterios ya calculados) dan exactamente el mismo
patrón y el mismo conteo. La ampliación suma, no reescribe.

De las 6, dos (`HU-082`, `HU-083`) ya se detectaban con los patrones
viejos: estaban afuera por un error de inclusión, no de detección. Las otras
cuatro las recuperan los patrones nuevos de `patrones_criterios_v2.py`.
`HU-084` ya estaba en el corpus, así que no aparece en esta lista — se
recupera sola al recalcularle los criterios.

Sigue afuera: `HU-300`, que no se detecta con ninguna de las dos
versiones. No se fuerza un número para ella.
"""

from __future__ import annotations

HU_AMPLIACION: list[str] = [
    "HU-066",
    "HU-082",
    "HU-083",
    "HU-392",
    "HU-466",
    "HU-469",
]


HU_SEPTIEMBRE: list[str] = [
    "HU-143",
    "HU-144",
    "HU-145",
    "HU-146",
    "HU-312",
    "HU-313",
    "HU-314",
    "HU-315",
    "HU-316",
    "HU-317",
    "HU-320",
    "HU-321",
    "HU-323",
    "HU-375",
    "HU-388",
    "HU-389",
    "HU-415",
    "HU-441",
    "HU-452",
    "HU-453",
]


def ampliar(corpus: list[str]) -> list[str]:
    """Corpus original + las dos ampliaciones, sin duplicar y en orden."""
    ya = set(corpus)
    salida = list(corpus)
    for lista in (HU_AMPLIACION, HU_SEPTIEMBRE):
        for h in lista:
            if h not in ya:
                ya.add(h)
                salida.append(h)
    return salida
