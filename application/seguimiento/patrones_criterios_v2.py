"""
Detección de criterios de aceptación — versión vigente.

**Esta es la única implementación viva.** Desde el 2026-09-06 la importan
`application/seguimiento/motor.py` (que la re-exporta como
`contar_criterios`) y `scripts/contar_criterios_aceptacion_retro.py`. Antes
la misma lógica estaba duplicada en esos dos lugares; tres copias es una
copia que se desincroniza.

Cómo se adoptó
--------------
Primero se probó, después se adoptó. `scripts/verificar_patrones_criterios.py`
corrió esta versión y la anterior sobre las 49 HU y confirmó que las **41 HU
que aportan a los 191 criterios** de `cobertura_real_retro.csv` dan
exactamente el mismo patrón y el mismo conteo; los patrones nuevos solo
recuperan HU que estaban en `SIN_PATRON_DETECTADO`, es decir que aportaban
cero. Resultado: corpus comparable 41 → 48 HU, criterios 191 → 230.

La versión anterior quedó congelada en `patrones_criterios_v1.py` para que
ese portón siga siendo una prueba que puede fallar. Si se borrara, compararía
esta versión contra sí misma y siempre daría verde.

Qué agrega, y por qué
---------------------
La versión actual reconoce tres formas:
  1. etiquetas `C1:` / `CA1:` / `Criterio 1:`  (exige separador `:` `.` o `)`)
  2. encabezado "Criterios de aceptación" + lista numerada
  3. encabezado "Criterios de aceptación" + viñetas

El diagnóstico sobre las HU que quedaron fuera del corpus mostró tres formas
reales que ninguna de esas captura, todas verificadas contra el texto de Jira:

  a) **Etiqueta entre corchetes**: `[C1] Contexto: ...` (HU-066)
  b) **Etiqueta sin separador y cuerpo en las líneas siguientes**:
     `Criterio 1\nContexto: ...` (HU-466), `[C1]\nContexto: ...`
     (HU-469)
  c) **Encabezado corto**: `Criterios:` en vez de "Criterios de aceptación"
     (HU-392)

Las tres son variantes de la misma idea, así que en vez de sumar tres regex
sueltas el enfoque cambia: se localizan las POSICIONES de las etiquetas y el
cuerpo de cada criterio es el texto que va hasta la etiqueta siguiente. Eso
cubre por igual el cuerpo en la misma línea y el cuerpo en las líneas de
abajo, que era justamente lo que rompía el enfoque anterior de "capturá el
resto de la línea".

Filtro de fragmentos (2026-09-07)
---------------------------------
Al ampliar el corpus a 48 HU apareció un problema que no era de los patrones
nuevos sino del más viejo de todos (`vinetas_en_seccion`): las viñetas de una
sección "Criterios de aceptación" no siempre son criterios. A veces son
encabezados de una tabla, marcadores de imagen, o notas sueltas.

Los 23 fragmentos que el umbral descarta en las 48 HU, todos verificados a
mano contra el texto de Jira, son exactamente estos:

    HU-082   'Modalidad', 'Periodo libre', 'Fecha de desembolso'  (x3)
    HU-083   los mismos tres, (x2) -- son campos de pantalla dentro de
                 [C1] y [C2], no criterios. ACTUALIZADO 2026-09-20: la HU ya
                 NO queda en cero; el patrón 4 (`etiqueta_por_posicion`)
                 reconoce [C1] y [C2] y cuenta 2 criterios. Ver el
                 comentario dentro de `contar_criterios` y
                 tests/test_patrones_criterios.py.
    HU-518    'URL_01', 'IMG_01', 'IMG_02', 'IMG_03'
    HU-002   'Pruebas fuse', 'Pruebas Apigee/GO'
    HU-140 'Aplica para APP'
    HU-173   'Aplica para app'

Ninguno es un criterio de aceptación y ninguno podía ser "cubierto" por un
test case, así que inflaban el denominador del índice de cobertura y --peor--
lo hacían de forma asimétrica: en `HU-082` el juez marcó los 12
fragmentos como no cubiertos del lado humano y los 12 como cubiertos del lado
del agente, empujando el Δ global casi 4 puntos hacia arriba con datos que no
significan nada. Un número que sube por basura en el denominador es
exactamente el tipo de número que se cae en una sustentación.

El umbral es una regla **uniforme sobre las 48**, no una exclusión de HU
elegidas a dedo: por eso también saca fragmentos de HU que ya estaban en la
línea base original, y por eso mueve el número de 191 criterios. Ese cambio
es deliberado y está documentado; `scripts/auditar_criterios_extraidos.py`
lo reproduce sin gastar una sola llamada a ningún modelo.

Precauciones tomadas contra falsos positivos
---------------------------------------------
- El número va PEGADO a la letra (`C1`, `CA1`), no `C 1`. Sin esto, una línea
  como "C 70" de una tabla de agencias se leería como criterio.
- La etiqueta debe estar al inicio de línea.
- El encabezado corto `Criterios:` exige dos puntos y estar solo en su línea;
  "criterios" suelto en medio de un párrafo no dispara nada.
- El orden de evaluación conserva el de la versión actual, así que una HU que
  hoy matchea por un patrón sigue matcheando por ese mismo patrón primero.
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


_LARGO_MINIMO = 20


_RE_ETIQUETA_POSICION = re.compile(
    r"^[ \t]*\[?[ \t]*(?:CA\d+|C\d+|Criterio[ \t]*\d+)[ \t]*\]?[ \t]*[:\.\)]?[ \t]*",
    re.IGNORECASE | re.MULTILINE,
)

_RE_ENCABEZADO_CORTO = re.compile(
    r"^[ \t]*criterios?[ \t]*:[ \t]*$", re.IGNORECASE | re.MULTILINE,
)


def _extraer_seccion(texto: str, inicio: int) -> str:
    """Desde `inicio` hasta el próximo encabezado corto tipo 'Casuísticas:'."""
    lineas = texto[inicio:].splitlines()
    fin = len(lineas)
    for i, linea in enumerate(lineas[1:], start=1):
        l = linea.strip()
        if l and l.endswith(":") and len(l) < 60 and not re.match(r"^\s*(\d+[\.\)]|[-*•]|\[?C\d+)", l):
            fin = i
            break
    return "\n".join(lineas[:fin])


def _extraer_seccion_criterios(texto: str) -> str:
    m = _RE_ENCABEZADO_CRITERIOS.search(texto)
    if not m:
        return ""
    return _extraer_seccion(texto, m.end())


def _por_posicion_de_etiqueta(texto: str) -> list[str]:
    """
    Cuerpo de cada criterio = texto entre una etiqueta y la siguiente.

    Cubre por igual `[C1] Contexto: ...` (cuerpo en la misma línea) y
    `Criterio 1\\nContexto: ...` (cuerpo en las líneas de abajo).
    """
    marcas = list(_RE_ETIQUETA_POSICION.finditer(texto))
    if not marcas:
        return []
    criterios: list[str] = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        cuerpo = " ".join(texto[m.end():fin].split())
        if cuerpo:
            criterios.append(cuerpo)
    return criterios


def contar_criterios(descripcion: str, largo_minimo: int | None = None) -> tuple[str, list[str]]:
    """
    Mismo contrato que la versión del motor: (patrón, lista de criterios).

    `largo_minimo` existe para que la auditoría pueda pedir el resultado EN
    CRUDO (`largo_minimo=0`) y mostrar exactamente qué descarta el filtro.
    Nadie más debería pasarlo: con el default, el conteo es el vigente.

    El orden de evaluación conserva el original para que ninguna HU que hoy
    matchea cambie de patrón; los dos patrones nuevos se prueban DESPUÉS.

    El patrón se decide con lo que matcheó EN CRUDO y recién después se
    filtran los fragmentos cortos. Hacerlo al revés cambiaría de patrón una
    HU cuyos ítems son todos cortos, en vez de dejarla en cero -- y "cero
    criterios utilizables" es la respuesta honesta ahí, no "probemos con otro
    patrón hasta que dé algo".
    """
    umbral = _LARGO_MINIMO if largo_minimo is None else largo_minimo

    def _utiles(criterios: list[str]) -> list[str]:
        return [c for c in criterios if len(c) >= umbral]


    candidatos: list[tuple[str, list[str]]] = []

    def _intentar(patron: str, crudos: list[str]) -> tuple[str, list[str]] | None:
        if not crudos:
            return None
        utiles = _utiles([c.strip() for c in crudos])
        if utiles:
            return patron, utiles
        candidatos.append((patron, []))
        return None


    if (r := _intentar("etiqueta_C_n",
                       _RE_ETIQUETA_CRITERIO.findall(descripcion))):
        return r

    seccion = _extraer_seccion_criterios(descripcion)
    if seccion:
        if (r := _intentar("lista_numerada_en_seccion",
                           _RE_LISTA_NUMERADA.findall(seccion))):
            return r
        if (r := _intentar("vinetas_en_seccion",
                           _RE_LISTA_VINETAS.findall(seccion))):
            return r


    por_posicion = _por_posicion_de_etiqueta(descripcion)
    if len(por_posicion) >= 2:
        if (r := _intentar("etiqueta_por_posicion", por_posicion)):
            return r


    m = _RE_ENCABEZADO_CORTO.search(descripcion)
    if m:
        seccion_corta = _extraer_seccion(descripcion, m.end())
        if (r := _intentar("lista_numerada_encabezado_corto",
                           _RE_LISTA_NUMERADA.findall(seccion_corta))):
            return r
        if (r := _intentar("vinetas_encabezado_corto",
                           _RE_LISTA_VINETAS.findall(seccion_corta))):
            return r


    if candidatos:
        return candidatos[0][0], []
    return "SIN_PATRON_DETECTADO", []
