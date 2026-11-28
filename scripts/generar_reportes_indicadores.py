"""
NOTA: este script corresponde al análisis RETROSPECTIVO EXPLORATORIO (lo que
NEXUS habría hecho sobre las mismas historias del pre-test). NO produce las
cifras del artículo. Los resultados del artículo se reproducen con
`scripts/construir_hoja_datos.py` y `scripts/analisis_estadistico.py`.

Genera los dos reportes de detalle de los tres indicadores del estudio:
uno con el lado POST-TEST (NEXUS) y otro con el lado PRE-TEST (proceso manual).

    python scripts/generar_reportes_indicadores.py

Deja en la raíz del proyecto:

    reporte_POST_test_indicadores.xlsx
    reporte_PRE_test_indicadores.xlsx

Por qué existe este script y no una exportación desde la pantalla: los dos
archivos tienen que poder auditarse fuera de la app, fila por fila, sin que
nadie confíe en un número que solo se ve en una tarjeta. Cada hoja de detalle
trae la unidad completa --los 272 criterios, los casos uno por uno, los 57
defectos-- y el resumen de arriba NO está escrito como valor: son fórmulas
COUNTIFS contra esas mismas filas. Si alguien filtra, borra o corrige una
fila, el indicador de la portada se mueve con ella. Esa es toda la idea: que
el archivo no pueda mentir sobre su propio contenido.

Las tres cifras que tiene que reproducir, y que el script verifica antes de
escribir nada:

    Índice de cobertura de pruebas    Pre 207/272   Post 258/272
    Índice de ejecuciones de pruebas  Pre 371/455   Post 615/616
    Estado de defectos                Pre 57        Post 27

Sobre el indicador 3, que no se lee como los otros dos. El Pre y el Post NO
son el mismo conjunto medido dos veces: el Pre son los 57 defectos que
llegaron a producción, y el Post son los 27 que las pruebas de NEXUS habrían
identificado, que son un SUBCONJUNTO de esos 57. Por eso la hoja del reporte
Post trae 27 filas y no 57 con una columna de sí/no, y por eso no se reporta
ningún "defecto proyectado": los 30 que quedarían son un contrafáctico, no un
conjunto auditable. Lo que se cuenta a los dos lados es lo que existe.

Los predicados que deciden cada fila NO se reimplementan acá: se importan de
`infrastructure.reportes.pretest_posttest`, los mismos que alimentan la app.
Si el criterio de "ejecutable" cambiara algún día, cambia en los dos lados a
la vez o no cambia en ninguno.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.dimensions import ColumnDimension

from adapters.tesis.csv_tesis_repository import CsvTesisRepository
from application.tesis.auditar_evitabilidad import (
    AuditarEvitabilidad,
    etiqueta_veredicto,
)
from application.tesis.calcular_metricas_tesis import (
    _ETIQUETA_SEVERIDAD,
    _ORDEN_SEVERIDAD,
    CalcularMetricasTesis,
)
from infrastructure.reportes.pretest_posttest import (
    _RE_THEN,
    _RE_WHEN,
    _clasificar_historico,
    _es_ejecutable,
    _leer,
    _titulo_normalizado,
)


FUENTE = "Arial"
AZUL = "1F3864"
AZUL_CLARO = "D9E2F3"
GRIS = "F2F2F2"
_BORDE = Side(style="thin", color="BFBFBF")
BORDE = Border(left=_BORDE, right=_BORDE, top=_BORDE, bottom=_BORDE)

SI, NO = "Sí", "No"


def _motivo_no_ejecutable(gherkin: str) -> str:
    """Por qué un guion no es ejecutable. Mismo orden que el indicador: primero
    'no hay guion', que es el caso más grave, y después qué le falta al que sí
    existe."""
    texto = (gherkin or "").strip()
    if not texto:
        return "Sin guion — el caso existe como título, sin pasos"
    faltan = []
    if not _RE_WHEN.search(texto):
        faltan.append("acción (When)")
    if not _RE_THEN.search(texto):
        faltan.append("resultado verificable (Then)")
    return "No declara " + " ni ".join(faltan) if faltan else ""


def _identificar(defecto, ids: dict) -> tuple[str, str]:
    """Key y título de un defecto, con lo que haya. Cuando Jira no resolvió la
    etiqueta se cae al `defecto_id` crudo en vez de dejar la celda vacía: una
    celda vacía descuadra el COUNTA de la portada y, peor, esconde que ese
    defecto igual pesa en el denominador del indicador."""
    key = (defecto.defecto_key or "").strip()
    titulo = (defecto.titulo or "").strip()
    if key and titulo:
        return key, titulo
    crudo = ids.get((key, defecto.hu_keys[0] if defecto.hu_keys else "",
                     defecto.criticidad), "")
    etiqueta = f"ID Jira {crudo}" if crudo else "(sin identificador)"
    return (key or etiqueta,
            titulo or "(sin título resuelto en Jira — ver el ID)")


def _titulo(ws, fila: int, texto: str, ancho: int, sub: str = "") -> int:
    ws.cell(fila, 1, texto).font = Font(FUENTE, size=14, bold=True, color=AZUL)
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ancho)
    fila += 1
    if sub:
        c = ws.cell(fila, 1, sub)
        c.font = Font(FUENTE, size=9, italic=True, color="595959")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ancho)
        ws.row_dimensions[fila].height = 28
        fila += 1
    return fila + 1


def _tabla(ws, fila: int, encabezados: list[str], filas: list[list],
           anchos: list[int], congelar: bool = True) -> int:
    """Escribe una tabla con encabezado, autofiltro y columnas dimensionadas.
    Devuelve la fila siguiente a la última escrita."""
    for col, (texto, ancho) in enumerate(zip(encabezados, anchos), start=1):
        c = ws.cell(fila, col, texto)
        c.font = Font(FUENTE, size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = BORDE
        ws.column_dimensions[get_column_letter(col)] = ColumnDimension(
            ws, index=get_column_letter(col), width=ancho)
    ws.row_dimensions[fila].height = 30
    encabezado = fila

    for i, datos in enumerate(filas):
        fila += 1
        for col, valor in enumerate(datos, start=1):
            c = ws.cell(fila, col, valor)
            c.font = Font(FUENTE, size=9)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = BORDE
            if i % 2:
                c.fill = PatternFill("solid", fgColor=GRIS)
        ws.row_dimensions[fila].height = 14

    ws.auto_filter.ref = (f"A{encabezado}:"
                          f"{get_column_letter(len(encabezados))}{fila}")
    if congelar:
        ws.freeze_panes = ws.cell(encabezado + 1, 1)
    return fila + 2


def _bloque_resumen(ws, fila: int, titulo: str, pares: list[tuple[str, object]],
                    nota: str = "") -> int:
    """Etiqueta + valor, con el valor en fórmula cuando se puede."""
    c = ws.cell(fila, 1, titulo)
    c.font = Font(FUENTE, size=11, bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor=AZUL)
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=2)
    fila += 1
    for etiqueta, valor in pares:
        a = ws.cell(fila, 1, etiqueta)
        a.font = Font(FUENTE, size=10)
        a.fill = PatternFill("solid", fgColor=AZUL_CLARO)
        a.border = BORDE
        b = ws.cell(fila, 2, valor)
        b.font = Font(FUENTE, size=10, bold=True)
        b.border = BORDE
        b.alignment = Alignment(horizontal="right")
        if isinstance(valor, str) and valor.startswith("=") and "/" in valor:
            b.number_format = "0.0%"
        fila += 1
    if nota:
        c = ws.cell(fila, 1, nota)
        c.font = Font(FUENTE, size=9, italic=True, color="595959")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=2)
        ws.row_dimensions[fila].height = 42
        fila += 1
    return fila + 1


def cargar_datos():
    repo = CsvTesisRepository(RAIZ)
    resumen = CalcularMetricasTesis(repo).ejecutar("completa")
    corpus = repo.obtener_corpus()
    claves = {f.hu_key for f in corpus.filas}

    criterios = sorted(
        (c for c in repo.obtener_criterios_pareados() if c.hu_key in claves),
        key=lambda c: (c.hu_key, c.texto))

    crudo = [f for archivo in ("historico_gherkin_texto_57hu.csv",
                               "historico_gherkin_texto_septiembre.csv")
             for f in _leer(RAIZ, archivo)
             if (f.get("hu_key") or "").strip() in claves]
    titulos_gobierno, _ = _clasificar_historico(crudo)
    casos_pre = sorted(
        (f for f in crudo
         if _titulo_normalizado(f.get("test_summary")) not in titulos_gobierno),
        key=lambda f: ((f.get("hu_key") or "").strip(),
                       f.get("test_issue_key") or ""))
    casos_post = sorted(
        (f for f in _leer(RAIZ, "revision_manual_retrospectiva_test_cases.csv")
         if (f.get("hu_key") or "").strip() in claves),
        key=lambda f: ((f.get("hu_key") or "").strip(), f.get("titulo") or ""))


    ids = {}
    for x in _leer(RAIZ, "evitabilidad_defectos_retro.csv"):
        clave = ((x.get("defecto_key") or "").strip(),
                 (x.get("hu_keys") or "").strip(),
                 (x.get("criticidad") or "").strip())
        ids[clave] = (x.get("defecto_id") or "").strip()

    auditoria = AuditarEvitabilidad(repo).ejecutar()
    defectos = sorted(auditoria.defectos,
                      key=lambda d: (_ORDEN_SEVERIDAD.get(d.criticidad, 9),
                                     d.defecto_key))
    return {
        "ids": ids,
        "repo": repo, "resumen": resumen, "corpus": corpus,
        "hu": sorted(claves), "filas": {f.hu_key: f for f in corpus.filas},
        "criterios": criterios, "casos_pre": casos_pre, "casos_post": casos_post,
        "defectos": defectos, "auditoria": auditoria,
    }


def verificar(d) -> None:
    """Antes de escribir un solo archivo, que las tres cifras cuadren contra el
    caso de uso. Un reporte que no reproduce el indicador no es un reporte, es
    una cuarta versión del número."""
    r = d["resumen"]
    esperado = [
        ("Cobertura Pre", sum(1 for c in d["criterios"] if c.cubierto_humano),
         round(r.indice_cobertura_pruebas.valor_pre / 100 * len(d["criterios"]))),
        ("Cobertura Post", sum(1 for c in d["criterios"] if c.cubierto_gio),
         round(r.indice_cobertura_pruebas.valor_post / 100 * len(d["criterios"]))),
        ("Casos Pre", len(d["casos_pre"]),
         sum(f.casos_pre for f in d["corpus"].filas)),
        ("Casos Post", len(d["casos_post"]),
         sum(f.casos_post for f in d["corpus"].filas)),
        ("Ejecutables Pre",
         sum(1 for f in d["casos_pre"] if _es_ejecutable(f.get("gherkin_texto") or "")),
         sum(f.casos_pre_ejecutables for f in d["corpus"].filas)),
        ("Ejecutables Post",
         sum(1 for f in d["casos_post"] if _es_ejecutable(f.get("gherkin_final") or "")),
         sum(f.casos_post_ejecutables for f in d["corpus"].filas)),
        ("Defectos del universo (Pre)", len(d["defectos"]),
         int(r.estado_defectos_global.valor_pre)),
        ("Identificados por NEXUS (Post)",
         sum(1 for x in d["defectos"] if x.veredicto == "Evitable"),
         r.total_defectos_mitigados),


        ("El Post es un subconjunto estricto del Pre",
         sum(1 for x in d["defectos"] if x.veredicto == "Evitable")
         < len(d["defectos"]), True),
    ]
    sin_key = [x for x in d["defectos"] if not (x.defecto_key or "").strip()]
    if sin_key:
        print(f"    AVISO {len(sin_key)} defecto(s) sin key de Jira; se usa el "
              f"defecto_id crudo para que la fila no quede vacía")
    esperado.append(
        ("Filas de defecto con identificador",
         sum(1 for x in d["defectos"] if _identificar(x, d["ids"])[0].strip()),
         len(d["defectos"])))

    malos = [(n, a, b) for n, a, b in esperado if a != b]
    for n, a, b in esperado:
        print(f"    {'OK ' if a == b else 'MAL'} {n}: reporte={a} indicador={b}")
    if malos:
        raise SystemExit(f"\nEl reporte no reproduce el indicador: {malos}")


def hoja_cobertura(wb, d, lado: str):
    ws = wb.create_sheet("1. Cobertura de pruebas")
    es_post = lado == "POST"
    quien = "Gio (NEXUS)" if es_post else "el diseño humano histórico"
    col_cub = "¿Cubierto por Gio?" if es_post else "¿Cubierto por el humano?"

    fila = _titulo(
        ws, 1, "Indicador 1 · Índice de cobertura de pruebas", 5,
        f"Un criterio de aceptación por fila. La columna «{col_cub}» es la que "
        f"suma el indicador: cuenta cuántos de los criterios de las 60 historias "
        f"quedaron cubiertos por {quien}. Evaluación semántica automatizada, "
        f"criterio por criterio, con el mismo método a los dos lados.")

    filas = []
    for i, c in enumerate(d["criterios"], start=1):
        cubierto = c.cubierto_gio if es_post else c.cubierto_humano
        filas.append([c.hu_key, i, c.texto, SI if cubierto else NO, c.cuadrante])

    fin = _tabla(ws, fila, [
        "HU", "#", "Criterio de aceptación", col_cub,
        "Cuadrante (humano × Gio)"], filas, [14, 5, 95, 17, 20])

    primera, ultima = fila + 1, fila + len(filas)
    _bloque_resumen(ws, fin, "Total del indicador", [
        ("Criterios evaluados", f"=COUNTA(A{primera}:A{ultima})"),
        (f"Cubiertos por {quien}", f'=COUNTIF(D{primera}:D{ultima},"{SI}")'),
        ("Índice de cobertura de pruebas",
         f'=COUNTIF(D{primera}:D{ultima},"{SI}")/COUNTA(A{primera}:A{ultima})'),
    ], nota=(
        "Los criterios del cuadrante «Ambos» llevan un texto de referencia "
        "«(criterio N de HU, cubierto por ambos)» en vez de su enunciado: el "
        "corpus solo conserva el texto literal de los NO cubiertos de cada "
        "lado, que es de donde se reconstruye esta matriz. El cuadrante y el "
        "conteo sí son exactos y se verificaron HU por HU contra los totales "
        "declarados."))
    return primera, ultima


def hoja_ejecuciones(wb, d, lado: str):
    ws = wb.create_sheet("2. Ejecuciones de pruebas")
    es_post = lado == "POST"

    if es_post:
        sub = ("Un caso de prueba generado por Gio por fila. La columna «¿Guion "
               "ejecutable?» es la que suma el indicador: un caso lo es cuando "
               "su guion existe y declara acción (When) y resultado verificable "
               "(Then), de modo que un QA que no lo escribió pueda correrlo sin "
               "volver a diseñarlo. Verificación sintáctica determinista, sin "
               "LLM. OJO: el indicador mide el DISEÑO del caso, no su corrida en "
               "ambiente de test — ninguna ejecución real entra en esta cuenta.")
        encabezados = ["HU", "Caso de prueba generado", "¿Guion ejecutable?",
                       "Qué le falta al guion", "Estado en la revisión humana",
                       "Motivo del rechazo"]
        anchos = [14, 62, 17, 34, 20, 46]
        filas = []
        for f in d["casos_post"]:
            g = f.get("gherkin_final") or ""
            ok = _es_ejecutable(g)
            estado = (f.get("estado_final") or "").strip() or "s/d"
            filas.append([(f.get("hu_key") or "").strip(),
                          (f.get("titulo") or "").strip(),
                          SI if ok else NO,
                          "" if ok else _motivo_no_ejecutable(g),
                          estado,
                          (f.get("motivo_rechazo") or "").strip()])
    else:
        sub = ("Un caso de prueba del histórico humano por fila. La columna "
               "«¿Guion ejecutable?» es la que suma el indicador, con el mismo "
               "criterio determinista que se aplica al agente: guion presente, "
               "con acción (When) y resultado verificable (Then). Solo entran "
               "los casos FUNCIONALES — las verificaciones normativas de "
               "gobierno (cumplimiento normativo, análisis estático y seguridad de la información) quedan fuera porque el "
               "agente no genera ninguna, y compararlas sería comparar trabajos "
               "distintos.")
        encabezados = ["HU", "Test Key (Xray)", "Test Plan", "Caso de prueba",
                       "¿Guion ejecutable?", "Qué le falta al guion"]
        anchos = [14, 16, 16, 62, 17, 34]
        filas = []
        for f in d["casos_pre"]:
            g = f.get("gherkin_texto") or ""
            ok = _es_ejecutable(g)
            filas.append([(f.get("hu_key") or "").strip(),
                          (f.get("test_issue_key") or "").strip(),
                          (f.get("test_plan_key") or "").strip(),
                          (f.get("test_summary") or "").strip(),
                          SI if ok else NO,
                          "" if ok else _motivo_no_ejecutable(g)])

    fila = _titulo(ws, 1, "Indicador 2 · Índice de ejecuciones de pruebas",
                   len(encabezados), sub)
    fin = _tabla(ws, fila, encabezados, filas, anchos)
    primera, ultima = fila + 1, fila + len(filas)
    col = "C" if es_post else "E"
    _bloque_resumen(ws, fin, "Total del indicador", [
        ("Casos de prueba", f"=COUNTA(A{primera}:A{ultima})"),
        ("Con guion ejecutable", f'=COUNTIF({col}{primera}:{col}{ultima},"{SI}")'),
        ("No ejecutables", f'=COUNTIF({col}{primera}:{col}{ultima},"{NO}")'),
        ("Índice de ejecuciones de pruebas",
         f'=COUNTIF({col}{primera}:{col}{ultima},"{SI}")'
         f"/COUNTA(A{primera}:A{ultima})"),
    ], nota=(
        "El nombre del indicador es el del documento de tesis. Lo que la "
        "columna cuenta es ejecutabilidad estructural del guion: si el caso "
        "está escrito de forma que se pueda ejecutar. Las ejecuciones reales "
        "—tests corridos contra tests planificados— son la métrica secundaria "
        "de Viabilidad operativa y no se reportan en esta hoja."))
    return primera, ultima


def hoja_defectos(wb, d, lado: str):
    """
    Las dos caras del indicador NO son la misma tabla con una columna distinta,
    y por eso esta función se parte en dos.

    El Pre-Test lista los 57 defectos que llegaron a producción: lo que el
    proceso manual no previno. El Post-Test lista SOLO los 27 que las pruebas
    de NEXUS habrían identificado -- los parcialmente mitigables y los no
    mitigables no entran, porque el Post no es un recuento de los mismos 57 con
    una marca al lado, es el conjunto de defectos efectivamente identificados.

    Tampoco se reportan "defectos proyectados". Esa cifra (30) es un
    contrafáctico: cuántos quedarían. El Post reporta un conjunto auditado y
    contable, no una proyección.
    """
    ws = wb.create_sheet("3. Estado de defectos")
    es_post = lado == "POST"
    c = d["auditoria"].cabecera
    total_pre = c.total

    if es_post:
        defectos = [x for x in d["defectos"] if x.veredicto == "Evitable"]
        titulo_hoja = "Indicador 3 · Estado de defectos · identificados por NEXUS"
        sub = (f"Un defecto identificado por fila. Son los {len(defectos)} "
               f"defectos reales de producción que las pruebas generadas por "
               f"NEXUS habrían anticipado, validados uno por uno por el "
               f"investigador. NO están los {total_pre} del Pre-Test: los "
               f"parcialmente mitigables y los no mitigables quedan fuera de "
               f"esta hoja a propósito, porque el Post-Test no es el mismo "
               f"conjunto con una marca al lado — es el conjunto de lo "
               f"efectivamente identificado. El universo completo del que "
               f"salen está en el reporte PRE-TEST, misma hoja.")
        encabezados = ["Defecto", "Título", "Severidad", "HU",
                       "¿Corregido por el investigador?",
                       "Caso del agente que lo habría identificado",
                       "Por qué lo habría identificado"]
        anchos = [16, 58, 14, 14, 24, 48, 78]
        filas = []
        for x in defectos:
            key, titulo = _identificar(x, d["ids"])
            filas.append([
                key, titulo,
                _ETIQUETA_SEVERIDAD.get(x.criticidad, x.criticidad),
                x.hu_keys[0] if x.hu_keys else "",
                SI if x.corregido_por_humano else NO,
                x.caso_agente or "(ninguno señalado por el juez)",
                x.justificacion or ""])
        nota = (
            f"Criterio conservador: solo entran los clasificados como "
            f"mitigables por la validación humana. Los parcialmente mitigables "
            f"no suman — es la categoría de la duda, y contarla inflaría el "
            f"resultado justo donde el método es más débil. Validación humana "
            f"completa sobre los {c.total} del universo, con {c.acuerdo_pct:.1f}% "
            f"de acuerdo entre el juez LLM ({c.modelo_juez}) y el "
            f"investigador, que corrigió {c.discrepancias}. "
            f"{len(c.corregidos_sin_caso)} de estas filas no tienen caso "
            f"señalado por el juez ({', '.join(c.corregidos_sin_caso)}): son "
            f"las que el arbitraje humano subió de categoría, y se dejan a la "
            f"vista porque son el punto más cuestionable del indicador.")
    else:
        defectos = list(d["defectos"])
        titulo_hoja = "Indicador 3 · Estado de defectos · llegados a producción"
        sub = ("Un defecto por fila: los que se escaparon del proceso de "
               "pruebas manual y llegaron al cliente. Ninguno fue prevenido, y "
               "eso no es un artificio de cálculo sino la definición de la "
               "muestra — se parte del listado de defectos que SÍ llegaron a "
               "producción. La columna del caso histórico muestra qué prueba "
               "existía en Xray para esa HU y cómo terminó su corrida.")
        encabezados = ["Defecto", "Título", "Severidad", "HU",
                       "Estado del defecto", "Caso de prueba histórico",
                       "Resultado de la corrida"]
        anchos = [16, 58, 14, 14, 20, 58, 20]
        filas = []
        for x in defectos:
            tst = x.tests_historicos[0] if x.tests_historicos else {}
            key, titulo = _identificar(x, d["ids"])
            filas.append([
                key, titulo,
                _ETIQUETA_SEVERIDAD.get(x.criticidad, x.criticidad),
                x.hu_keys[0] if x.hu_keys else "",
                x.estado or "s/d",
                tst.get("titulo") or "(sin test vinculado)",
                tst.get("run_estado") or "s/d"])
        nota = ("Este es el universo completo del indicador. El reporte "
                "POST-TEST, en esta misma hoja, trae el subconjunto que las "
                "pruebas de NEXUS habrían identificado.")

    fila = _titulo(ws, 1, titulo_hoja, len(encabezados), sub)
    fin = _tabla(ws, fila, encabezados, filas, anchos)
    primera, ultima = fila + 1, fila + len(filas)

    if es_post:
        pares = [
            ("Defectos identificados por NEXUS", f"=COUNTA(A{primera}:A{ultima})"),
            (f"Sobre los {total_pre} llegados a producción en el Pre-Test",
             f"=COUNTA(A{primera}:A{ultima})/{total_pre}"),
        ]
    else:
        pares = [("Defectos llegados a producción",
                  f"=COUNTA(A{primera}:A{ultima})")]
    fin = _bloque_resumen(ws, fin, "Total del indicador", pares, nota=nota)


    fin += 1
    sev = sorted({x.criticidad for x in d["defectos"]},
                 key=lambda s: _ORDEN_SEVERIDAD.get(s, 9))
    encabezados_sev = ["Severidad",
                       "Identificados" if es_post else "Llegados a producción"]
    ws.cell(fin, 1, "Desglose por severidad").font = Font(
        FUENTE, size=11, bold=True, color=AZUL)
    fin += 1
    for col_i, texto in enumerate(encabezados_sev, start=1):
        cc = ws.cell(fin, col_i, texto)
        cc.font = Font(FUENTE, size=10, bold=True, color="FFFFFF")
        cc.fill = PatternFill("solid", fgColor=AZUL)
        cc.border = BORDE
    for s in sev:
        etiqueta = _ETIQUETA_SEVERIDAD.get(s, s)
        fin += 1
        for col_i, valor in enumerate(
                [etiqueta,
                 f'=COUNTIF(C{primera}:C{ultima},"{etiqueta}")'], start=1):
            cc = ws.cell(fin, col_i, valor)
            cc.font = Font(FUENTE, size=10)
            cc.border = BORDE
    return primera, ultima


def hoja_por_hu(wb, d, lado: str):
    ws = wb.create_sheet("Resumen por HU")
    es_post = lado == "POST"
    col_cob = "D"
    col_eje = "C" if es_post else "E"
    h1, h2, h3 = "'1. Cobertura de pruebas'", "'2. Ejecuciones de pruebas'", \
                 "'3. Estado de defectos'"

    fila = _titulo(
        ws, 1, f"Resumen por historia de usuario · lado {lado}-TEST", 10,
        "Una fila por HU. Ningún valor está escrito: todos son fórmulas "
        "COUNTIFS contra las hojas de detalle, así que si se corrige una fila "
        "allá, acá se mueve solo. Las HU sin defectos registrados muestran 0 — "
        "en el Pre son las que no tienen trazabilidad de incidentes en Jira, "
        "no HU sin problemas; en el Post son además las que sí tienen "
        "defectos pero ninguno resultó identificable por las pruebas del "
        "agente.")

    filas = []
    for hu in d["hu"]:
        filas.append([
            hu,
            f"=COUNTIF({h1}!$A:$A,$A{{r}})",
            f'=COUNTIFS({h1}!$A:$A,$A{{r}},{h1}!${col_cob}:${col_cob},"{SI}")',
            f"=IFERROR(C{{r}}/B{{r}},\"\")",
            f"=COUNTIF({h2}!$A:$A,$A{{r}})",
            f'=COUNTIFS({h2}!$A:$A,$A{{r}},{h2}!${col_eje}:${col_eje},"{SI}")',
            f"=IFERROR(F{{r}}/E{{r}},\"\")",
            f"=COUNTIF({h3}!$D:$D,$A{{r}})",
        ])


    col_def = "Defectos identificados" if es_post else "Defectos en producción"
    encabezados = ["HU", "Criterios", "Cubiertos", "% cobertura",
                   "Casos de prueba", "Con guion ejecutable", "% ejecutables",
                   col_def]
    anchos = [16, 11, 11, 12, 15, 17, 13, 16]
    encabezado = fila
    for col, (texto, ancho) in enumerate(zip(encabezados, anchos), start=1):
        c = ws.cell(fila, col, texto)
        c.font = Font(FUENTE, size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(wrap_text=True, vertical="center",
                                horizontal="center")
        c.border = BORDE
        ws.column_dimensions[get_column_letter(col)] = ColumnDimension(
            ws, index=get_column_letter(col), width=ancho)
    ws.row_dimensions[fila].height = 30

    for i, datos in enumerate(filas):
        fila += 1
        for col, valor in enumerate(datos, start=1):
            texto = valor.format(r=fila) if isinstance(valor, str) else valor
            c = ws.cell(fila, col, texto)
            c.font = Font(FUENTE, size=10)
            c.border = BORDE
            if col in (4, 7):
                c.number_format = "0.0%"
            if i % 2:
                c.fill = PatternFill("solid", fgColor=GRIS)


    fila += 1
    ws.cell(fila, 1, "TOTAL").font = Font(FUENTE, size=10, bold=True)
    p, u = encabezado + 1, fila - 1
    for col, formula in (
            (2, f"=SUM(B{p}:B{u})"), (3, f"=SUM(C{p}:C{u})"),
            (4, f"=C{fila}/B{fila}"), (5, f"=SUM(E{p}:E{u})"),
            (6, f"=SUM(F{p}:F{u})"), (7, f"=F{fila}/E{fila}"),
            (8, f"=SUM(H{p}:H{u})")):
        c = ws.cell(fila, col, formula)
        c.font = Font(FUENTE, size=10, bold=True)
        c.border = BORDE
        c.fill = PatternFill("solid", fgColor=AZUL_CLARO)
        if col in (4, 7):
            c.number_format = "0.0%"
    ws.freeze_panes = ws.cell(encabezado + 1, 2)
    return ws


def hoja_portada(wb, d, lado: str, rangos: dict):
    """`rangos` trae la primera y la última fila REAL de cada hoja de detalle.
    No se adivinan: un rango de más ancho --A5:A400, por ejemplo-- se come las
    filas del bloque de totales que va debajo de la tabla y la portada termina
    contando 277 criterios donde hay 272. Pasó en la primera versión de este
    script y por eso los rangos viajan calculados."""
    ws = wb.create_sheet("Resumen", 0)
    es_post = lado == "POST"
    r = d["resumen"]
    h1, h2, h3 = "'1. Cobertura de pruebas'", "'2. Ejecuciones de pruebas'", \
                 "'3. Estado de defectos'"
    quien = ("NEXUS — casos generados por el agente Gio" if es_post
             else "proceso manual — diseño de pruebas del equipo QA")

    fila = _titulo(
        ws, 1,
        f"Reporte de detalle · {lado}-TEST · los tres indicadores", 2,
        f"Lado medido: {quien}.\n"
        f"Muestra: {r.n_hu} historias de usuario · {r.n_criterios} criterios de "
        f"aceptación · {r.estado_defectos_global.n_muestra} HU con trazabilidad "
        f"de defectos. Cohorte completa. Generado el {date.today():%d/%m/%Y}.")
    ws.row_dimensions[2].height = 46

    c1, u1 = rangos["cobertura"]
    fila = _bloque_resumen(ws, fila, "Indicador 1 · Índice de cobertura de pruebas", [
        ("Criterios evaluados", f"=COUNTA({h1}!$A${c1}:$A${u1})"),
        ("Cubiertos", f'=COUNTIF({h1}!$D${c1}:$D${u1},"{SI}")'),
        ("Valor del indicador",
         f'=COUNTIF({h1}!$D${c1}:$D${u1},"{SI}")/COUNTA({h1}!$A${c1}:$A${u1})'),
    ], nota="Evaluación semántica automatizada criterio por criterio, mismo "
            "método a los dos lados. No la afectan los casos normativos: esas "
            "verificaciones no cubren criterios de ninguno de los dos lados.")

    col_eje = "C" if es_post else "E"
    c2, u2 = rangos["ejecuciones"]
    fila = _bloque_resumen(ws, fila, "Indicador 2 · Índice de ejecuciones de pruebas", [
        ("Casos de prueba", f"=COUNTA({h2}!$A${c2}:$A${u2})"),
        ("Con guion ejecutable",
         f'=COUNTIF({h2}!${col_eje}${c2}:${col_eje}${u2},"{SI}")'),
        ("Valor del indicador",
         f'=COUNTIF({h2}!${col_eje}${c2}:${col_eje}${u2},"{SI}")'
         f"/COUNTA({h2}!$A${c2}:$A${u2})"),
    ], nota="Verificación sintáctica determinista, sin LLM: el guion existe y "
            "declara acción (When) y resultado verificable (Then). Mide el "
            "diseño del caso, no su corrida en ambiente de test. Solo casos "
            "funcionales — el agente no genera verificaciones normativas.")

    c3, u3 = rangos["defectos"]
    total_pre = d["auditoria"].cabecera.total
    if es_post:
        pares3 = [
            ("Defectos identificados por NEXUS",
             f"=COUNTA({h3}!$A${c3}:$A${u3})"),
            (f"Sobre los {total_pre} llegados a producción en el Pre-Test",
             f"=COUNTA({h3}!$A${c3}:$A${u3})/{total_pre}"),
        ]
        nota3 = (f"Es un CONTEO de defectos auditados, no una proyección: son "
                 f"los que las pruebas de NEXUS habrían identificado, "
                 f"validados uno por uno. La hoja de detalle trae SOLO estos, "
                 f"no los {total_pre} del universo — el Post-Test no es el "
                 f"mismo conjunto con una marca al lado. Criterio conservador: "
                 f"los parcialmente mitigables no cuentan. El "
                 f"{total_pre} está en el reporte PRE-TEST.")
    else:
        pares3 = [("Defectos llegados a producción",
                   f"=COUNTA({h3}!$A${c3}:$A${u3})")]
        nota3 = ("Es un CONTEO de defectos, no un porcentaje. Este es el "
                 "universo del indicador: los defectos que el proceso manual "
                 "no previno y llegaron al cliente. El reporte POST-TEST trae "
                 "el subconjunto que las pruebas de NEXUS habrían "
                 "identificado.")
    fila = _bloque_resumen(ws, fila, "Indicador 3 · Estado de defectos",
                           pares3, nota=nota3)

    c = ws.cell(fila, 1, "Cómo leer este archivo")
    c.font = Font(FUENTE, size=11, bold=True, color=AZUL)
    fila += 1
    for texto in (
        "· Ningún número de esta portada está escrito: todos son fórmulas "
        "contra las hojas de detalle. Si se corrige una fila allá, el "
        "indicador de acá se mueve con ella.",
        "· «Resumen por HU» abre los mismos tres indicadores historia por "
        "historia, también con fórmulas.",
        "· Cada hoja de detalle trae la unidad completa y tiene autofiltro: se "
        "puede filtrar por HU, por severidad o por el sí/no del indicador y "
        "ver de qué filas sale el número.",
        "· Los valores se verificaron contra `CalcularMetricasTesis`, el mismo "
        "caso de uso que alimenta las pantallas, antes de escribir el archivo. "
        "Si no hubieran cuadrado, el script no lo habría generado.",
        f"· Este archivo cubre SOLO el lado {lado}-TEST. El otro lado está en "
        f"el reporte {'PRE' if es_post else 'POST'}-TEST, con la misma "
        f"estructura, para poder compararlos hoja contra hoja.",
    ):
        c = ws.cell(fila, 1, texto)
        c.font = Font(FUENTE, size=9, color="404040")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=2)
        ws.row_dimensions[fila].height = 26
        fila += 1

    ws.column_dimensions["A"] = ColumnDimension(ws, index="A", width=52)
    ws.column_dimensions["B"] = ColumnDimension(ws, index="B", width=22)
    return ws


def construir(d, lado: str) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    rangos = {
        "cobertura": hoja_cobertura(wb, d, lado),
        "ejecuciones": hoja_ejecuciones(wb, d, lado),
        "defectos": hoja_defectos(wb, d, lado),
    }
    hoja_por_hu(wb, d, lado)
    hoja_portada(wb, d, lado, rangos)
    wb.move_sheet("Resumen por HU", offset=-3)
    destino = RAIZ / f"reporte_{lado}_test_indicadores.xlsx"
    wb.save(destino)
    return destino


def main() -> None:
    print("Cargando el corpus...")
    d = cargar_datos()
    print("Verificando contra el caso de uso:")
    verificar(d)
    for lado in ("POST", "PRE"):
        destino = construir(d, lado)
        print(f"  escrito: {destino.name}")
    print("\nFalta recalcular las fórmulas con LibreOffice para que el archivo "
          "traiga sus valores en caché:\n"
          "    soffice --headless --convert-to xlsx --outdir . "
          "reporte_POST_test_indicadores.xlsx")


if __name__ == "__main__":
    main()
