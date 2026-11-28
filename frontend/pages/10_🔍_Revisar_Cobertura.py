"""
🔍 Cobertura IA vs Humano — matriz de intersección sobre los criterios.

Fase 4.1. La pregunta que responde no es "¿cuánto cubre cada uno?" --eso ya
está en Pre-Test/Post-Test-- sino "¿dónde se solapan y dónde no?". El
promedio de cobertura esconde justamente lo que acá se ve: que el agente no
cubre *lo mismo pero más*, sino que agrega criterios que el humano omitió y
pierde unos pocos que el humano sí tenía.

Declarativa, como toda la fase: el cálculo vive en
`application/impacto/AnalizarCoberturaIAvsHumano`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from adapters.tesis.csv_tesis_repository import CsvTesisRepository
from application.impacto.analizar_impacto import (
    CUADRANTES,
    AnalizarCoberturaIAvsHumano,
)
from frontend.auth import requerir_sesion
from frontend.comun.graficos import barra_apilada_100
from frontend.comun.estilo import aplicar_estilo_institucional

st.set_page_config(page_title="Cobertura IA vs Humano — NEXUS", page_icon="🔍",
                   layout="wide")
requerir_sesion()


aplicar_estilo_institucional()

st.markdown("""
<style>
.section-header{font-size:12px;font-weight:700;letter-spacing:.08em;
 text-transform:uppercase;color:#4F46E5;margin:24px 0 10px;}
.cuad{background:#FFF;border:1px solid #E2E8F0;border-radius:6px;
 padding:13px 15px;height:100%;border-top:3px solid var(--c);}
.cuad .n{font-size:22px;font-weight:800;color:#0F172A;
 font-variant-numeric:tabular-nums;line-height:1.1;}
.cuad .p{font-size:12px;color:#475569;font-weight:700;}
.cuad .t{font-size:12.5px;font-weight:700;color:#0F172A;margin-top:6px;}
.cuad .d{font-size:11.5px;color:#64748B;line-height:1.45;margin-top:2px;}
.nota{background:#F8FAFC;border-left:3px solid #CBD5E1;padding:11px 15px;
 border-radius:3px;font-size:12.5px;color:#334155;line-height:1.55;margin:10px 0;}
</style>
""", unsafe_allow_html=True)

st.markdown(
    "<h1 style='color:#0F172A;font-size:22px;font-weight:700;"
    "letter-spacing:.02em;margin-bottom:4px;'>🔍 Cobertura IA vs Humano</h1>"
    "<p style='color:#64748B;font-size:13px;margin-top:0;max-width:840px;'>"
    "Matriz de intersección criterio por criterio: dónde coinciden el diseño "
    "humano y el del agente, dónde gana cada uno y qué queda sin cubrir.</p>",
    unsafe_allow_html=True,
)

_RAIZ = Path(__file__).resolve().parent.parent.parent
_uso = AnalizarCoberturaIAvsHumano(CsvTesisRepository(_RAIZ))
_previo = _uso.ejecutar()

_f1, _f2 = st.columns([1.2, 2.8])
with _f1:
    _opciones = {"Completa": "completa", "Estándar": "estandar", "Primario": "primario"}
    _sel = st.selectbox("Cohorte", list(_opciones), index=0)
d = _uso.ejecutar(_opciones[_sel])
with _f2:
    st.markdown(
        f"<div class='nota' style='margin-top:26px;'>Muestra activa: "
        f"<b>{d.cohorte_nombre}</b> · <b>{d.n_hu} HU</b> · "
        f"<b>{d.total_criterios} criterios</b>. Los criterios suman el mismo "
        f"denominador que la Fase 3, y los marginales también: "
        f"<b>{d.cubiertos_humano}</b> cubiertos por el humano y "
        f"<b>{d.cubiertos_gio}</b> por Gio.</div>", unsafe_allow_html=True)


st.markdown("<div class='section-header'>Los cuatro cuadrantes</div>",
            unsafe_allow_html=True)
for _col, _q in zip(st.columns(4), d.cuadrantes):
    _col.markdown(
        f"<div class='cuad' style='--c:{_q.color};'>"
        f"<div class='n'>{_q.criterios}</div>"
        f"<div class='p'>{_q.porcentaje:.1f}% de los criterios</div>"
        f"<div class='t'>{_q.nombre}</div>"
        f"<div class='d'>{_q.descripcion}</div></div>", unsafe_allow_html=True)

st.markdown("<div class='section-header'>Distribución</div>", unsafe_allow_html=True)
st.markdown(
    barra_apilada_100([{"etiqueta": q.nombre, "valor": q.criterios, "color": q.color}
                       for q in d.cuadrantes]),
    unsafe_allow_html=True,
)

if d.razon_ganancia:
    st.markdown(
        f"<div class='nota'><strong>El agente aporta "
        f"{d.ganancia_neta} criterios que el humano omitió y pierde "
        f"{d.puntos_ciegos}.</strong> Razón de "
        f"<strong>{d.razon_ganancia:.1f} a 1</strong>. Ese es el aporte "
        f"incremental real, y no se ve en el promedio de cobertura: ahí los "
        f"{d.ganancia_neta} ganados y los {d.puntos_ciegos} perdidos quedan "
        f"sumados en un solo número.</div>", unsafe_allow_html=True)


st.markdown("<div class='section-header'>Criterios, uno por uno</div>",
            unsafe_allow_html=True)
_t1, _t2 = st.columns([1.4, 1])
with _t1:
    _hu = st.multiselect("HU", d.hu_disponibles, default=[],
                         help="Vacío = todas las HU de la cohorte.")
with _t2:
    _cuad = st.multiselect("Cuadrante", list(CUADRANTES), default=[],
                           help="Vacío = los cuatro cuadrantes.")
_df = pd.DataFrame(d.detalle)
if _hu:
    _df = _df[_df["HU Key"].isin(_hu)]
if _cuad:
    _df = _df[_df["Cuadrante"].isin(_cuad)]
st.caption(f"{len(_df)} criterios en el filtro.")
st.dataframe(_df, use_container_width=True, hide_index=True)
st.download_button(
    "⬇️ Exportar criterios (CSV)",
    data=_df.to_csv(index=False).encode("utf-8"),
    file_name=f"cobertura_ia_vs_humano_{d.n_hu}hu.csv", mime="text/csv",
)
st.caption(
    "Los criterios marcados como cubiertos por ambos no traen su enunciado: "
    "el corpus solo guarda el texto de los NO cubiertos de cada lado, que es "
    "de donde se reconstruye toda esta matriz. Lo que sí es exacto de ellos es "
    "el cuadrante, y la reconstrucción se verifica contra los conteos "
    "declarados HU por HU — si una no cuadrara, se omitiría en vez de adivinar."
)
