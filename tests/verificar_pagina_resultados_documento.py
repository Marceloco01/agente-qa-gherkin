"""
Verificación de la pantalla «Resultados» y del estilo institucional.

La regla de este proyecto: una pantalla no se entrega sin que un script la
haya EJECUTADO y comparado sus números contra la fuente. Acá la fuente es el
libro de resultados publicado, y las aserciones están escritas contra sus
cifras, celda por celda.

Verifica además dos pedidos explícitos del usuario (2026-10-14): que la
pantalla hable de la HERRAMIENTA y no del estudio que la evaluó, y que el
color de acento con letras blancas llegue a todas las pestañas.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_streamlit_documento as fake_streamlit


fake_streamlit.instalar()

ok, fallos = 0, []


def check(nombre: str, condicion: bool, detalle: str = "") -> None:
    global ok
    if condicion:
        ok += 1
    else:
        fallos.append(f"{nombre}{' — ' + detalle if detalle else ''}")


from adapters.tesis.csv_resultados_documento import CsvResultadosDocumento
from application.tesis.calcular_resultados_documento import (
    CalcularResultadosDocumento,
)

r = CalcularResultadosDocumento(CsvResultadosDocumento(RAIZ)).ejecutar()

check("[1] 60 ciclos", r.total_ciclos == 60, f"son {r.total_ciclos}")


c = r.cobertura
check("[1] cobertura identificadas pre = 263", c.denominador_pre == 263, str(c.denominador_pre))
check("[1] cobertura cubiertas pre = 201", c.numerador_pre == 201, str(c.numerador_pre))
check("[1] cobertura identificadas post = 272", c.denominador_post == 272, str(c.denominador_post))
check("[1] cobertura cubiertas post = 258", c.numerador_post == 258, str(c.numerador_post))
check("[1] cobertura índice pre = 76.43", round(c.valor_pre, 2) == 76.43, f"{c.valor_pre:.4f}")
check("[1] cobertura índice post = 94.85", round(c.valor_post, 2) == 94.85, f"{c.valor_post:.4f}")
check("[1] diferencia cobertura = 18.42", round(c.diferencia_pp, 2) == 18.42,
      f"{c.diferencia_pp:.4f}")
check("[1] cobertura desv pre = 28.28", round(c.desviacion_pre, 2) == 28.28,
      f"{c.desviacion_pre:.4f}")
check("[1] cobertura desv post = 11.60", round(c.desviacion_post, 2) == 11.60,
      f"{c.desviacion_post:.4f}")


e = r.ejecuciones
check("[1] ejecución especificados pre = 465", e.denominador_pre == 465, str(e.denominador_pre))
check("[1] ejecución ejecutados pre = 392", e.numerador_pre == 392, str(e.numerador_pre))
check("[1] ejecución especificados post = 605", e.denominador_post == 605, str(e.denominador_post))
check("[1] ejecución ejecutados post = 604", e.numerador_post == 604, str(e.numerador_post))
check("[1] ejecución índice pre = 84.30", round(e.valor_pre, 2) == 84.30, f"{e.valor_pre:.4f}")
check("[1] ejecución índice post = 99.83", round(e.valor_post, 2) == 99.83, f"{e.valor_post:.4f}")
check("[1] diferencia ejecuciones = 15.53", round(e.diferencia_pp, 2) == 15.53,
      f"{e.diferencia_pp:.4f}")
check("[1] ejecución desv pre = 31.99", round(e.desviacion_pre, 2) == 31.99,
      f"{e.desviacion_pre:.4f}")
check("[1] ejecución desv post = 1.29", round(e.desviacion_post, 2) == 1.29,
      f"{e.desviacion_post:.4f}")


d = r.defectos
ESPERADO = {

    "Bajo":     (8,  8,  0, 100.00,  0,  0, 0, None),
    "Medio":    (26, 18, 8,  69.23,  4,  3, 1, 75.00),
    "Alto":     (5,  3,  2,  60.00,  2,  1, 1, 50.00),
    "Crítico":  (16, 14, 2,  87.50, 14, 12, 2, 85.71),
}
check("[2] orden Bajo→Crítico (de menor a mayor criticidad)",
      [f.severidad for f in d.por_severidad] == ["Bajo", "Medio", "Alto", "Crítico"],
      str([f.severidad for f in d.por_severidad]))
for f in d.por_severidad:
    esp = ESPERADO[f.severidad]
    check(f"[2] {f.severidad} detectados pre", f.detectados_pre == esp[0], str(f.detectados_pre))
    check(f"[2] {f.severidad} corregidos pre", f.corregidos_pre == esp[1], str(f.corregidos_pre))
    check(f"[2] {f.severidad} no corregidos pre", f.no_corregidos_pre == esp[2],
          str(f.no_corregidos_pre))
    check(f"[2] {f.severidad} estado pre",
          esp[3] is None if f.estado_pre is None else round(f.estado_pre, 2) == esp[3],
          str(f.estado_pre))
    check(f"[2] {f.severidad} detectados post", f.detectados_post == esp[4],
          str(f.detectados_post))
    check(f"[2] {f.severidad} corregidos post", f.corregidos_post == esp[5],
          str(f.corregidos_post))
    check(f"[2] {f.severidad} no corregidos post", f.no_corregidos_post == esp[6],
          str(f.no_corregidos_post))
    check(f"[2] {f.severidad} estado post",
          (esp[7] is None and f.estado_post is None)
          or (esp[7] is not None and f.estado_post is not None
              and round(f.estado_post, 2) == esp[7]),
          str(f.estado_post))

check("[2] Bajo post sin defectos NO se imputa como 0%",
      d.por_severidad[0].estado_post is None, str(d.por_severidad[0].estado_post))
check("[2] total detectados pre = 55", d.detectados_pre == 55, str(d.detectados_pre))
check("[2] total corregidos pre = 43", d.corregidos_pre == 43, str(d.corregidos_pre))
check("[2] no corregidos pre = 12", d.no_corregidos_pre == 12, str(d.no_corregidos_pre))
check("[2] estado pre = 78.18", round(d.estado_pre, 2) == 78.18, f"{d.estado_pre:.4f}")
check("[2] total detectados post = 20", d.detectados_post == 20, str(d.detectados_post))
check("[2] total corregidos post = 16", d.corregidos_post == 16, str(d.corregidos_post))
check("[2] no corregidos post = 4", d.no_corregidos_post == 4,
      str(d.no_corregidos_post))
check("[2] estado post = 80.00", round(d.estado_post, 2) == 80.00,
      f"{d.estado_post:.4f}")
check("[2] diferencia defectos = 1.82", round(d.diferencia_pp, 2) == 1.82,
      f"{d.diferencia_pp:.4f}")


check("[3] ciclos con defectos pre = 22", d.ciclos_con_defectos_pre == 22,
      str(d.ciclos_con_defectos_pre))
check("[3] ciclos sin defectos pre = 38", d.ciclos_sin_defectos_pre == 38,
      str(d.ciclos_sin_defectos_pre))
check("[3] ciclos con defectos post = 9", d.ciclos_con_defectos_post == 9,
      str(d.ciclos_con_defectos_post))
check("[3] ciclos sin defectos post = 51", d.ciclos_sin_defectos_post == 51,
      str(d.ciclos_sin_defectos_post))
check("[3] las severidades suman el total pre",
      sum(f.detectados_pre for f in d.por_severidad) == d.detectados_pre)
check("[3] las severidades suman el total post",
      sum(f.detectados_post for f in d.por_severidad) == d.detectados_post)
check("[3] corregidos + no corregidos = detectados (pre)",
      d.corregidos_pre + d.no_corregidos_pre == d.detectados_pre)
check("[3] corregidos + no corregidos = detectados (post)",
      d.corregidos_post + d.no_corregidos_post == d.detectados_post)


for nombre, ind in (("cobertura", c), ("ejecuciones", e)):
    for lado in ("pre", "post"):
        caja = getattr(ind, f"caja_{lado}")
        check(f"[4] {nombre} caja {lado}: n = 60", caja.n == 60, str(caja.n))
        check(f"[4] {nombre} caja {lado}: Q1 ≤ mediana ≤ Q3",
              caja.q1 <= caja.mediana <= caja.q3,
              f"{caja.q1:.2f}/{caja.mediana:.2f}/{caja.q3:.2f}")
        check(f"[4] {nombre} caja {lado}: bigotes contienen la caja",
              caja.minimo <= caja.q1 and caja.q3 <= caja.maximo)
        check(f"[4] {nombre} caja {lado}: dentro de 0-100",
              0 <= caja.minimo and caja.maximo <= 100)
    check(f"[4] {nombre}: las dos curvas tienen 60 puntos",
          len(ind.curva_pre) == 60 and len(ind.curva_post) == 60)


    check(f"[4] {nombre}: la curva pre está ordenada de menor a mayor",
          list(ind.curva_pre) == sorted(ind.curva_pre))
    check(f"[4] {nombre}: la curva post está ordenada de menor a mayor",
          list(ind.curva_post) == sorted(ind.curva_post))

check("[4] detalle por ciclo = 60 filas", len(r.detalle_por_ciclo) == 60,
      str(len(r.detalle_por_ciclo)))


PAGINA = RAIZ / "frontend" / "pages" / "15_📈_Resultados.py"
fuente = PAGINA.read_text(encoding="utf-8")
cuerpo = "\n".join(l for l in fuente.splitlines() if not l.strip().startswith("#"))
for patron in ("sum(", "/ len(", "round(sum", "statistics.", "np.", "mean("):
    check(f"[5] la página no usa «{patron}»", patron not in cuerpo)
check("[5] la página no divide para sacar porcentajes",
      not re.search(r"\*\s*100\b", cuerpo))


import importlib

_estilo = importlib.import_module("frontend.comun.estilo")
HOJA = _estilo._CSS
graficos = (RAIZ / "frontend" / "comun" / "graficos_documento.py").read_text(encoding="utf-8")

tam_css = [int(m) for m in re.findall(r"font-size:\s*(\d+)(?:\.\d+)?px", HOJA)]
check("[6] la hoja institucional declara tamaños de letra", len(tam_css) >= 10,
      str(len(tam_css)))
check("[6] ningún texto de la interfaz baja de 15px",
      all(x >= 15 for x in tam_css), f"mínimo {min(tam_css) if tam_css else '—'}px")
check("[6] los títulos de página suben a 32px", 32 in tam_css)
tam_svg = [int(m) for m in re.findall(r"^T_[A-Z]+\s*=\s*(\d+)", graficos, re.M)]
check("[6] los gráficos declaran su escala tipográfica", len(tam_svg) >= 5)
check("[6] ningún texto de los gráficos baja de 14px",
      all(x >= 14 for x in tam_svg), f"mínimo {min(tam_svg) if tam_svg else '—'}px")


check("[7] el color de acento neutro está en los gráficos", 'ACENTO = "#334155"' in graficos)
check("[7] la hoja institucional usa el color de acento neutro", _estilo.ACENTO == "#334155")
check("[7] los encabezados de sección van en el color de acento",
      ".section-header, .seccion {" in HOJA
      and "background: #334155 !important" in HOJA)
check("[7] los encabezados de sección llevan texto blanco",
      HOJA.count("color: #FFFFFF !important") >= 3)
check("[7] los avisos y tarjetas dejaron el fondo gris",
      ".nota, .badge, .callout" in HOJA and "#F8FAFC" in HOJA)
check("[7] el borde de las tarjetas va en el color de acento",
      "border-top: 5px solid #334155 !important" in HOJA)
check("[7] no quedó el índigo viejo en la hoja", "#4F46E5" not in HOJA)
check("[7] la página nueva no trae CSS propio que pelee con la hoja",
      "<style>" not in fuente, "la página volvió a declarar estilos")


sys.modules.pop("frontend.auth", None)
import types

auth = types.ModuleType("frontend.auth")
auth.requerir_sesion = lambda *a, **k: None
sys.modules["frontend.auth"] = auth

reg = fake_streamlit.instalar()
import runpy

try:
    runpy.run_path(str(PAGINA), run_name="__main__")
    corrio = True
    error = ""
except Exception as exc:
    corrio, error = False, f"{type(exc).__name__}: {exc}"
check("[8] la página corre sin excepción", corrio, error)
check("[8] la página no mostró errores", not reg.errores, "; ".join(reg.errores))

salida = "\n".join(reg.markdown)
for valor in ("76.43", "94.85", "+18.42", "84.30", "99.83", "+15.53",
              "78.18", "80.00", "+1.82", "60 ciclos"):
    check(f"[8] en pantalla aparece «{valor}»", valor in salida)
check("[8] declara sobre qué se midió", "ciclos de prueba" in salida.lower())
check("[8] rotula los dos periodos en lenguaje de producto",
      "Sin el agente" in salida and "Con el agente" in salida)
check("[8] hay una tabla de respaldo", len(reg.dataframes) >= 1)
check("[8] se puede descargar el detalle", len(reg.descargas) >= 1)


svgs = re.findall(r"<svg.*?</svg>", salida, re.S)
check("[9] se dibujaron al menos 9 gráficos", len(svgs) >= 9, f"son {len(svgs)}")
for i, s in enumerate(svgs, 1):
    check(f"[9] svg {i} sin None", "None" not in s)
    check(f"[9] svg {i} sin nan", "nan" not in s.lower())
    check(f"[9] svg {i} tiene viewBox", "viewBox=" in s)
    check(f"[9] svg {i} tiene etiqueta accesible", "aria-label=" in s)


check("[9] hay un diagrama de cajas por indicador",
      sum(1 for s in svgs if 'stroke="#FFFFFF" stroke-width="3.5"' in s) == 2,
      str(sum(1 for s in svgs if 'stroke-width="3.5"' in s)))
check("[9] hay una curva de cuantiles por indicador",
      sum(1 for s in svgs if "<polyline" in s) == 2,
      str(sum(1 for s in svgs if "<polyline" in s)))
check("[9] la curva sombrea la distancia entre distribuciones",
      sum(1 for s in svgs if "<polygon" in s) == 2)
check("[9] se dibujaron los 10 gráficos previstos", len(svgs) == 10, f"son {len(svgs)}")
check("[9] hay barras apiladas (gris de remanente)",
      sum(1 for s in svgs if "#CBD5E1" in s) >= 3)
check("[9] ninguna barra dibuja el 0/0 como cero",
      salida.count("sin defectos registrados") >= 1)


visible = "\n".join(reg.texto_visible).lower()
check("[10] no aparece «evitabilidad» en pantalla", "evitabilidad" not in visible)
check("[10] no aparece «proyectado» en pantalla", "proyectad" not in visible)


for palabra in ("tesis", "informe", "documento", "tabla ii", "tabla iii",
                "tabla vii", "tabla xiii", "fig.", "figura", "unidad de análisis",
                "pre-test", "post-test"):
    check(f"[10] no aparece «{palabra}» en pantalla", palabra not in visible)
check("[10] el eje de la curva aclara que no es una línea de tiempo",
      "no es una línea de tiempo" in visible)
check("[10] se declara que la severidad va de menor a mayor criticidad",
      "menor a mayor criticidad" in visible)


router = (RAIZ / "frontend" / "streamlit_app.py").read_text(encoding="utf-8")
paginas_router = re.findall(r'st\.Page\("([^"]+)"', router)
check("[11] la página está en el menú", "pages/15_📈_Resultados.py" in paginas_router,
      str(paginas_router))
check("[11] el Resumen ejecutivo salió del menú",
      not any("Resumen_Ejecutivo" in p for p in paginas_router))
check("[11] la sección ya no se llama «de la tesis»",
      "Evaluación de la tesis" not in router)
check("[11] la sección es «Evaluación del agente»",
      '"Evaluación del agente"' in router)
check("[11] es la primera de su sección",
      router.index('"Evaluación del agente"')
      < router.index("pages/15_📈_Resultados.py")
      < router.index("pages/8_🧪_Pre_Test_Post_Test.py"))


import ast


_arbol_router = ast.parse(router)
_llamadas_page = [n for n in ast.walk(_arbol_router)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "Page"]
check("[13] se leyeron las llamadas a st.Page", len(_llamadas_page) == 12,
      str(len(_llamadas_page)))
check("[13] ninguna pestaña declara icono",
      not any(k.arg == "icon" for c_ in _llamadas_page for k in c_.keywords))


check("[13] la hoja oculta el icono heredado del nombre de archivo",
      '[data-testid="stIconEmoji"] {' in HOJA
      and "display: none !important" in HOJA)
secciones = re.findall(r'^\s{8}"([^"]+)":\s*\[', router, re.M)
check("[13] se leyeron las secciones del menú", len(secciones) == 7, str(secciones))
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2190-\u2BFF\uFE0F]")
for s in secciones:
    check(f"[13] la sección «{s}» no lleva emoji", not EMOJI.search(s))
titulos = re.findall(r'title="([^"]+)"', router)
check("[13] se leyeron los títulos de las pestañas", len(titulos) == 12, str(len(titulos)))

check("[13] «Registro Pre-Test» salió del menú", "Registro Pre-Test" not in titulos)
check("[13] «Validar mitigación» ahora es «Revisar defectos»",
      "Revisar defectos" in titulos and "Validar mitigación" not in titulos)
for s in titulos:
    check(f"[13] la pestaña «{s}» no lleva emoji", not EMOJI.search(s))
check("[13] la hoja le da borde a cada pestaña",
      '[data-testid="stSidebarNavLink"] {' in HOJA
      and "border-left: 4px solid" in HOJA)
check("[13] la pestaña activa se pinta del color de acento con letra blanca",
      '[data-testid="stSidebarNavLink"][aria-current="page"] {' in HOJA
      and HOJA.count('color: #FFFFFF !important') >= 4)
check("[13] los encabezados de grupo van en el color de acento con su línea",
      '[data-testid="stNavSectionHeader"] {' in HOJA
      and f"border-bottom: 2px solid #334155 !important" in HOJA)
check("[13] los rótulos largos no se recortan con puntos suspensivos",
      HOJA.count("text-overflow: clip !important") >= 3)


for ruta in paginas_router:
    archivo = RAIZ / "frontend" / ruta
    check(f"[12] existe {ruta}", archivo.exists())
    if not archivo.exists():
        continue
    codigo = archivo.read_text(encoding="utf-8")
    check(f"[12] {Path(ruta).name} importa la hoja institucional",
          "from frontend.comun.estilo import aplicar_estilo_institucional" in codigo)
    check(f"[12] {Path(ruta).name} la aplica",
          re.search(r"^\s*aplicar_estilo_institucional\(\)\s*$", codigo, re.M) is not None)
    try:
        ast.parse(codigo)
        compila = True
    except SyntaxError as exc:
        compila, codigo = False, f"{exc}"
    check(f"[12] {Path(ruta).name} compila", compila, "" if compila else codigo)


print(f"\nOK: {ok}   FALLOS: {len(fallos)}")
for f in fallos:
    print("  ✗", f)
sys.exit(1 if fallos else 0)
