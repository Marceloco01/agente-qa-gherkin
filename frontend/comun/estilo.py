"""
Estilo institucional de NEXUS: gris pizarra, texto blanco, letra grande.

UNA sola hoja para toda la app. Antes cada página traía su propio bloque
`<style>` con los mismos nombres de clase y valores distintos --indigo acá,
gris allá, 10.5px en una y 12.5px en otra--, así que cambiar el color de los
encabezados significaba editar trece archivos y acordarse de los trece.

Cómo se usa: una línea después de `requerir_sesion()`.

    from frontend.comun.estilo import aplicar_estilo_institucional
    aplicar_estilo_institucional()

POR QUÉ `!important`. Las páginas todavía conservan sus bloques `<style>`
propios, con las mismas clases y la misma especificidad. En igualdad de
especificidad gana el último que se inyecta, y el orden depende de dónde cayó
la llamada en cada archivo -- o sea, de la suerte. `!important` saca al orden
de la ecuación: esta hoja gana siempre, se la llame donde se la llame. Cuando
los bloques viejos se vayan limpiando de las páginas, estas marcas se pueden
sacar.

CONTRASTE, verificado y no estimado:
    blanco sobre #334155  -> 10.35:1   (mínimo AA para texto: 4.5:1)
    blanco sobre #1E293B  -> 14.63:1
    #14181F sobre blanco  -> 16.1:1
La letra sube en bloque: ningún texto de la interfaz baja de 15px, que fue la
observación que originó este archivo.
"""

from __future__ import annotations

import streamlit as st

ACENTO = "#334155"
ACENTO_OSCURO = "#1E293B"
ACENTO_CLARO = "#F8FAFC"
AZUL = "#1D6FA3"
TINTA = "#14181F"
TINTA_SUAVE = "#5B6472"
BORDE = "#E2E8F0"

_CSS = f"""
<style>
/* ── Base ─────────────────────────────────────────────────────────────── */
/* Se apunta al CONTENEDOR DE MARKDOWN, no a `[class*="st-"]`: ese comodín
   alcanza también a los componentes internos de los selectores y las tablas,
   donde forzar 16px descoloca la maquetación. Van los dos nombres --la clase
   vieja y el data-testid nuevo-- porque cambian entre versiones de Streamlit
   y hace falta que funcione en la que el usuario tenga instalada. */
.stMarkdown p, .stMarkdown li, .stMarkdown span,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {{
  font-size: 16px !important;
  line-height: 1.6 !important;
}}
.stMarkdown h1, [data-testid="stMarkdownContainer"] h1, .stApp h1 {{
  font-size: 32px !important; font-weight: 700 !important;
}}
.stMarkdown h2, [data-testid="stMarkdownContainer"] h2, .stApp h2 {{
  font-size: 25px !important; font-weight: 700 !important;
}}
.stMarkdown h3, [data-testid="stMarkdownContainer"] h3, .stApp h3 {{
  font-size: 20px !important; font-weight: 700 !important;
}}
.stCaption, .stCaption p, [data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {{
  font-size: 15px !important; color: {TINTA_SUAVE} !important; line-height: 1.55;
}}

/* ── Encabezados de sección: la banda de acento con letras blancas ──────── */
/* `.section-header` es el nombre viejo y `.seccion` el nuevo; los dos se
   pintan igual para no tener que renombrar clases en trece archivos. */
.section-header, .seccion {{
  background: {ACENTO} !important;
  color: #FFFFFF !important;
  font-size: 18px !important;
  font-weight: 700 !important;
  letter-spacing: .04em !important;
  text-transform: uppercase !important;
  padding: 12px 20px !important;
  border-radius: 6px !important;
  margin: 32px 0 8px !important;
  display: block !important;
}}
.titulo-banda {{
  background: linear-gradient(90deg, {ACENTO_OSCURO} 0%, {ACENTO} 100%) !important;
  color: #FFFFFF !important; padding: 26px 32px !important;
  border-radius: 8px !important; margin-bottom: 8px !important;
}}
.titulo-banda h1 {{
  color: #FFFFFF !important; font-size: 32px !important; font-weight: 700 !important;
  margin: 0 !important; line-height: 1.2 !important;
}}
.titulo-banda p {{
  color: #E2E8F0 !important; font-size: 17px !important; margin: 10px 0 0 !important;
  line-height: 1.5 !important; max-width: 980px;
}}
.sub {{ font-size: 18px !important; font-weight: 700 !important; color: {TINTA} !important;
       margin: 18px 0 8px !important; }}
.fuente {{ font-size: 15px !important; color: {TINTA_SUAVE} !important;
          margin: 0 0 18px !important; padding-left: 4px; }}

/* ── Tarjetas y avisos: borde y fondo con el color de acento ─────────────────── */
.kpi, .hallazgo {{
  background: #FFFFFF !important; border: 1px solid {BORDE} !important;
  border-top: 5px solid {ACENTO} !important; border-radius: 8px !important;
  padding: 20px 22px !important; height: 100%;
}}
.kpi .sigla {{
  background: {ACENTO} !important; color: #FFFFFF !important;
  font-size: 15px !important; font-weight: 800 !important; letter-spacing: .06em;
  padding: 4px 10px !important; border-radius: 4px !important; display: inline-block;
}}
.kpi .nombre, .hallazgo > div:nth-child(2) {{
  font-size: 17px !important; font-weight: 700 !important; color: {TINTA} !important;
  line-height: 1.35 !important; margin: 10px 0 14px !important;
}}
.kpi .par {{ font-size: 16px !important; color: {TINTA_SUAVE} !important;
            display: flex; justify-content: space-between; align-items: baseline;
            margin: 7px 0 !important; }}
.kpi .par b {{ color: {TINTA} !important; font-size: 26px !important;
              font-weight: 700 !important; font-variant-numeric: tabular-nums; }}
.kpi .det, .hallazgo .e {{ font-size: 15px !important; color: #7C8694 !important; }}
.kpi .delta, .d-bien, .d-neutro {{
  background: {ACENTO} !important; color: #FFFFFF !important;
  font-size: 20px !important; font-weight: 700 !important;
  padding: 8px 16px !important; border-radius: 5px !important;
  display: inline-block !important; margin-top: 14px !important;
  font-variant-numeric: tabular-nums;
}}
.hallazgo .v {{ font-size: 30px !important; font-weight: 800 !important;
               color: {ACENTO} !important; }}
.nota, .badge, .callout, .beneficio, .costo {{
  background: {ACENTO_CLARO} !important;
  border: none !important;
  border-left: 5px solid {ACENTO} !important;
  color: #3B424D !important; font-size: 16px !important; line-height: 1.6 !important;
  padding: 16px 20px !important; border-radius: 4px !important; margin: 16px 0 !important;
}}
.nota b, .badge b, .callout b, .balance b {{ color: {TINTA} !important; }}

/* ── Controles de Streamlit ───────────────────────────────────────────── */
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {{
  font-size: 16px !important; color: {TINTA_SUAVE} !important; font-weight: 600 !important;
}}
[data-testid="stMetricValue"] {{ font-size: 30px !important; color: {TINTA} !important; }}
[data-testid="stMetricDelta"] {{ font-size: 16px !important; }}
[data-testid="stWidgetLabel"] p, label p {{
  font-size: 16px !important; font-weight: 600 !important; color: {TINTA} !important;
}}
[data-testid="stExpander"] summary, .streamlit-expanderHeader {{
  font-size: 16px !important; font-weight: 700 !important; color: {ACENTO} !important;
}}
[data-testid="stDataFrame"] {{ font-size: 16px !important; }}
.stTabs [data-baseweb="tab"] {{ font-size: 17px !important; font-weight: 600 !important; }}
.stTabs [aria-selected="true"] {{ color: {ACENTO} !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: {ACENTO} !important; }}
.stButton > button, .stDownloadButton > button {{
  font-size: 16px !important; font-weight: 600 !important;
  border-color: {ACENTO} !important; color: {ACENTO} !important;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  background: {ACENTO} !important; color: #FFFFFF !important;
}}
.stProgress > div > div > div {{ background-color: {ACENTO} !important; }}

/* ── Barra lateral: índice ejecutivo, sin iconos y con borde por pestaña ── */
/* Los `data-testid` son los de Streamlit 1.58, que es la versión fijada en
   `requirements-lock.txt`. Si en una versión futura cambian, lo único que
   pasa es que el menú vuelve a su aspecto por defecto: nada se rompe. */
[data-testid="stSidebarNav"] {{ padding-top: 6px !important; }}
[data-testid="stSidebarNav"] ul {{ padding: 0 10px !important; }}
[data-testid="stSidebarNav"] li {{ margin: 0 !important; }}

/* Encabezado de grupo: la línea de acento de abajo es la que separa bloques. */
[data-testid="stNavSectionHeader"] {{
  font-size: 15px !important; font-weight: 800 !important;
  letter-spacing: .10em !important; text-transform: uppercase !important;
  color: {ACENTO} !important;
  padding: 20px 2px 7px !important; margin: 0 0 8px !important;
  border-bottom: 2px solid {ACENTO} !important;
  /* Streamlit recorta con puntos suspensivos y "EVALUACIÓN DEL AG..." no es
     un encabezado: que baje de renglón. */
  white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important; line-height: 1.35 !important;
}}
/* El recorte no está en el <header> sino en el <span>/<div>/<p> de adentro,
   que Streamlit trae con `nowrap` + `ellipsis`. Hay que desactivarlo ahí, y
   repetir la tipografía porque el <p> interior cae bajo la regla general de
   párrafos. Se apunta solo al contenedor de texto: el chevron de plegar la
   sección es otro hijo y no debe heredar ni el tamaño ni el interletrado. */
[data-testid="stNavSectionHeader"] > span,
[data-testid="stNavSectionHeader"] [data-testid="stMarkdownContainer"],
[data-testid="stNavSectionHeader"] [data-testid="stMarkdownContainer"] p {{
  white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important;
  font-size: 15px !important; font-weight: 800 !important;
  letter-spacing: .10em !important; text-transform: uppercase !important;
  color: {ACENTO} !important; line-height: 1.35 !important; margin: 0 !important;
}}

/* Cada pestaña, con su borde. El filete izquierdo es lo que se tiñe al pasar
   por encima y lo que marca la página activa, así el ojo encuentra dónde está
   parado sin tener que leer. */
[data-testid="stSidebarNavLink"] {{
  border: 1px solid {BORDE} !important;
  border-left: 4px solid #CBD5E1 !important;
  border-radius: 5px !important;
  background: #FFFFFF !important;
  margin: 0 0 7px !important;
  padding: 11px 13px !important;
  transition: none !important;
}}
[data-testid="stSidebarNavLink"] span,
[data-testid="stSidebarNavLink"] p {{
  font-size: 16px !important; font-weight: 600 !important;
  color: {TINTA} !important; line-height: 1.35 !important;
  /* Mismo motivo: "Cobertura de Gio vs Histó..." no dice nada. Que envuelva. */
  white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important;
}}
[data-testid="stSidebarNavLink"]:hover {{
  border-left-color: {ACENTO} !important;
  background: {ACENTO_CLARO} !important;
}}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
  background: {ACENTO} !important;
  border-color: {ACENTO} !important;
  border-left-color: {ACENTO_OSCURO} !important;
}}
[data-testid="stSidebarNavLink"][aria-current="page"] span,
[data-testid="stSidebarNavLink"][aria-current="page"] p {{
  color: #FFFFFF !important; font-weight: 700 !important;
}}
/* Sin icono por pestaña. No se puede evitar desde el router: `st.Page` toma
   el emoji del nombre del archivo aunque no se le pase `icon=`, y pasarle una
   cadena vacía lanza excepción. Se oculta el envoltorio entero (si no, queda
   su hueco) y, como respaldo para navegadores sin `:has()`, también el span
   del emoji. Va acotado al menú: un emoji dentro de una página no se toca. */
[data-testid="stSidebarNavLink"] > span:has([data-testid="stIconEmoji"]) {{
  display: none !important;
}}
[data-testid="stSidebarNav"] [data-testid="stIconEmoji"] {{ display: none !important; }}
[data-testid="stSidebarNavSeparator"] {{ margin: 14px 0 !important; }}
</style>
"""


def aplicar_estilo_institucional() -> None:
    """Inyecta la hoja. Idempotente: llamarla dos veces no rompe nada."""
    st.markdown(_CSS, unsafe_allow_html=True)
