"""
📐 Cobertura de Gio vs Histórico — qué tipo de trabajo hace el agente y cuál no.

Fase 4.3. Esta pantalla es corta, y eso es el resultado, no una omisión.

El submódulo iba a responder "¿los casos de Gio son nuevos o replican lo que
ya existía?" midiendo similitud semántica contra el corpus histórico. Esa
medición se intentó cuatro veces con calibraciones distintas y cada una dio
un titular incompatible con las otras sobre exactamente los mismos vectores;
se descartó y la razón se muestra ACÁ, en pantalla, en vez de esconderse en
un commit. Un submódulo que prometía tres categorías y entrega una sola tiene
que explicar la diferencia a quien lo lee.

Lo que sí quedó en pie es un hecho verificable, contado contra el catálogo
real de títulos normativos y no asumido: Gio no genera compuertas de
gobierno. De ahí sale la corrección que sostiene toda la Fase 3 --comparar al
agente contra los 455 casos funcionales del histórico y no contra los 771
totales--, y sin ella el resto de los indicadores compararía peras con
manzanas.

El aporte incremental del agente, que era la pregunta de fondo, está medido
sin embeddings y con cuentas exactas en **Cobertura IA vs Humano** (4.1).

Declarativa, como toda la fase: el cálculo vive en
`application/impacto/AnalizarNovedadCasos`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from adapters.tesis.csv_tesis_repository import CsvTesisRepository
from application.impacto.analizar_impacto import AnalizarNovedadCasos
from frontend.auth import requerir_sesion
from frontend.comun.estilo import aplicar_estilo_institucional

st.set_page_config(page_title="Gio vs Histórico — NEXUS", page_icon="📐",
                   layout="wide")
requerir_sesion()


aplicar_estilo_institucional()

st.markdown("""
<style>
.section-header{font-size:12px;font-weight:700;letter-spacing:.08em;
 text-transform:uppercase;color:#4F46E5;margin:24px 0 10px;}
.hecho{background:#FFF;border:1px solid #E2E8F0;border-radius:6px;
 padding:16px 18px;height:100%;border-top:3px solid var(--c);}
.hecho .n{font-size:30px;font-weight:800;color:#0F172A;
 font-variant-numeric:tabular-nums;line-height:1.05;}
.hecho .t{font-size:12.5px;font-weight:700;color:#0F172A;margin-top:8px;}
.hecho .d{font-size:11.5px;color:#64748B;line-height:1.45;margin-top:3px;}
.nota{background:#F8FAFC;border-left:3px solid #CBD5E1;padding:11px 15px;
 border-radius:3px;font-size:12.5px;color:#334155;line-height:1.55;margin:10px 0;}
.limite{background:#FFFBEB;border-left:3px solid #D97706;padding:14px 17px;
 border-radius:3px;font-size:12.5px;color:#422006;line-height:1.65;margin:10px 0;}
.limite b{color:#78350F;}
</style>
""", unsafe_allow_html=True)

st.markdown(
    "<h1 style='color:#0F172A;font-size:22px;font-weight:700;"
    "letter-spacing:.02em;margin-bottom:4px;'>📐 Cobertura de Gio vs Histórico</h1>"
    "<p style='color:#64748B;font-size:13px;margin-top:0;max-width:840px;'>"
    "Qué parte del esfuerzo de prueba histórico entra en el terreno del agente "
    "y qué parte no. Es la corrección de base que hace comparables el Pre-Test "
    "y el Post-Test.</p>",
    unsafe_allow_html=True,
)

_RAIZ = Path(__file__).resolve().parent.parent.parent
d = AnalizarNovedadCasos(CsvTesisRepository(_RAIZ)).ejecutar()


st.markdown("<div class='section-header'>El hecho, contado y no asumido</div>",
            unsafe_allow_html=True)

_c1, _c2, _c3 = st.columns(3)
_c1.markdown(
    f"<div class='hecho' style='--c:#eb6834;'>"
    f"<div class='n'>{d.compuertas_generadas} <span style='font-size:15px;"
    f"font-weight:600;color:#64748B;'>de {d.casos_generados}</span></div>"
    f"<div class='t'>Compuertas de gobierno generadas por Gio</div>"
    f"<div class='d'>Se contó cada caso generado contra el catálogo real de "
    f"títulos normativos del histórico. El cero es un conteo, no un "
    f"supuesto.</div></div>", unsafe_allow_html=True)
_c2.markdown(
    f"<div class='hecho' style='--c:#94A3B8;'>"
    f"<div class='n'>{d.compuertas_historicas} <span style='font-size:15px;"
    f"font-weight:600;color:#64748B;'>({d.pct_gobierno:.0f}%)</span></div>"
    f"<div class='t'>Compuertas en el histórico humano</div>"
    f"<div class='d'>De {d.casos_historicos_total} casos históricos, esta "
    f"porción son verificaciones normativas que se repiten idénticas de una "
    f"HU a otra.</div></div>", unsafe_allow_html=True)
_c3.markdown(
    f"<div class='hecho' style='--c:#2a78d6;'>"
    f"<div class='n'>{d.casos_funcionales_humanos}</div>"
    f"<div class='t'>Casos funcionales humanos — la base comparable</div>"
    f"<div class='d'>Es contra estos, y no contra los "
    f"{d.casos_historicos_total} totales, que se mide al agente en toda la "
    f"evaluación de la tesis.</div></div>", unsafe_allow_html=True)

st.markdown(
    f"<div class='nota'><b>Por qué esto importa más que parecer un detalle.</b> "
    f"Gio genera casos funcionales derivados de los criterios de aceptación de "
    f"una HU; las compuertas de gobierno no salen de la HU, salen de la norma "
    f"--cumplimiento normativo, análisis estático, seguridad de la información y estándares de diseño-- y se repiten iguales "
    f"en decenas de historias. Medir al agente contra los "
    f"{d.casos_historicos_total} casos históricos lo penalizaría por no hacer "
    f"un trabajo que nadie le pidió; medirlo contra los "
    f"{d.casos_funcionales_humanos} funcionales lo compara con lo que "
    f"efectivamente hace. Este ajuste es el que corrigió la eficiencia "
    f"reportada en fases anteriores.</div>", unsafe_allow_html=True)


st.markdown("<div class='section-header'>Las verificaciones normativas del "
            "histórico</div>", unsafe_allow_html=True)
st.caption(
    f"Un título cuenta como compuerta de gobierno cuando aparece en "
    f"{d.umbral_hu_gobierno} o más HU distintas. El umbral es deliberadamente "
    f"conservador: deja fuera verificaciones normativas que aparecen en una o "
    f"dos HU, así que la cifra de {d.compuertas_historicas} es un piso, no un "
    f"techo."
)
st.dataframe(pd.DataFrame(d.tabla_gobierno), use_container_width=True,
             hide_index=True)


st.markdown("<div class='section-header'>Lo que se intentó medir y no entró</div>",
            unsafe_allow_html=True)
st.markdown(f"<div class='limite'>{d.limitacion_similitud}</div>",
            unsafe_allow_html=True)

st.markdown(
    "<div class='nota'>Para el aporte incremental del agente --cuántos "
    "criterios cubre Gio que el humano omitió y cuántos pierde-- la pantalla "
    "es <b>Cobertura IA vs Humano</b>, en esta misma sección. Ahí la cuenta es "
    "criterio por criterio, cuadra exacta contra el denominador de la Fase 3 y "
    "no depende de ningún embedding.</div>", unsafe_allow_html=True)
