"""
Detección de criterios de aceptación — VERSIÓN HISTÓRICA CONGELADA.

Esta es, palabra por palabra, la función que vivía en
`application/seguimiento/motor.py` hasta el 2026-09-06 y que produjo los
**191 criterios sobre 41 HU** de `cobertura_real_retro.csv`.

Por qué se conserva en vez de borrarse
--------------------------------------
El motor ya usa la versión ampliada (`patrones_criterios_v2.py`). Si se
borrara esta, el portón de regresión `scripts/verificar_patrones_criterios.py`
compararía la versión nueva contra sí misma y siempre daría "IGUAL" — una
prueba que no puede fallar no prueba nada.

Dejándola acá, el portón sigue siendo re-ejecutable y sigue siendo evidencia
citable: cualquiera puede volver a correrlo y confirmar que la ampliación de
patrones no movió ni un criterio de la línea base sobre la que se calculó la
cobertura. Mismo criterio de auditoría honesta que el resto del proyecto:
no se oculta lo anterior, se conserva y se etiqueta.

**No editar este archivo.** Es un registro de lo que había, no código vivo.
Cualquier mejora va en `patrones_criterios_v2.py`.
"""

from __future__ import annotations

import re

_RE_ETIQUETA_CRITERIO = re.compile(
    r"^\s*(?:C\d+|CA\d+|Criterio\s*\d+)\s*[:\.\)]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_RE_ENCABEZADO_CRITERIOS = re.compile(
    r"criterios?\s+de\s+aceptaci[oó]n\s*:?\s*$", re.IGNORECASE | re.MULTILINE,
)
_RE_LISTA_NUMERADA = re.compile(r"^\s*\d+\s*[\.\)]\s*(.+)$", re.MULTILINE)
_RE_LISTA_VINETAS = re.compile(r"^\s*[-*•]\s+(.+)$", re.MULTILINE)


def _extraer_seccion_criterios(texto: str) -> str:
    m = _RE_ENCABEZADO_CRITERIOS.search(texto)
    if not m:
        return ""
    resto = texto[m.end():]
    lineas = resto.splitlines()
    fin = len(lineas)
    for i, linea in enumerate(lineas[1:], start=1):
        l = linea.strip()
        if l and l.endswith(":") and len(l) < 60 and not re.match(r"^\s*(\d+[\.\)]|[-*•]|C\d+)", l):
            fin = i
            break
    return "\n".join(lineas[:fin])


def contar_criterios(descripcion: str) -> tuple[str, list[str]]:
    encontrados = _RE_ETIQUETA_CRITERIO.findall(descripcion)
    if encontrados:
        return "etiqueta_C_n", [e.strip() for e in encontrados]

    seccion = _extraer_seccion_criterios(descripcion)
    if seccion:
        numerados = _RE_LISTA_NUMERADA.findall(seccion)
        if numerados:
            return "lista_numerada_en_seccion", [n.strip() for n in numerados]
        vinetas = _RE_LISTA_VINETAS.findall(seccion)
        if vinetas:
            return "vinetas_en_seccion", [v.strip() for v in vinetas]

    return "SIN_PATRON_DETECTADO", []
