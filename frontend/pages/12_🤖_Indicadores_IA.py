"""
Indicadores de IA — cómo se está portando el agente.

Sale de la mitad "agente" de `pages/1_📊_Dashboard.py`: calidad de la
generación, evaluación de Vera (distribución y evolución de scores contra el
umbral) y desenlace de las alucinaciones detectadas. Los bloques se movieron
por rango de línea, sin retipearlos; lo compartido con "Indicadores de QA"
(estilos, filtros, queries) vive en `frontend/comun/panel_operativo.py`.

NO se trajo el bloque "🤖🧠 Interpretación con IA" (Nora): el propio Dashboard
lo tenía marcado como deprecado y absorbido por Nexus Insights.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from frontend.auth import requerir_sesion
from infrastructure.config import cargar_configuracion_vera
from frontend.comun.panel_operativo import (
    aplicar_estilos, filtros_sidebar, fmt_duracion, badge, render_desenlace_alucinaciones, render_distribucion_scores_vera, render_evolucion_scores_vera, agregar_defectos_por_severidad, render_barras_severidad, cargar_datos, obtener_keys_hu_periodo,
)
from frontend.comun.estilo import aplicar_estilo_institucional

st.set_page_config(page_title="Indicadores de IA — NEXUS", page_icon="🤖", layout="wide")
requerir_sesion()
aplicar_estilos()


aplicar_estilo_institucional()

fecha_desde, fecha_hasta, key_hu_filtro = filtros_sidebar("ind_ia")

st.markdown(
    "<h1 style='color:#0F172A;font-size:22px;font-weight:700;"
    "letter-spacing:0.02em;margin-bottom:4px;'>🤖 Indicadores de IA</h1>"
    "<p style='color:#64748B;font-size:13px;margin-top:0;'>Qué tan bien trabajan Vera y Gio</p>",
    unsafe_allow_html=True,
)

datos = cargar_datos(str(fecha_desde), str(fecha_hasta), key_hu_filtro)
v = datos["volumen"]
c = datos["calidad"]

if not v["total_hus"]:
    st.markdown(
        "<div class='empty-state'>"
        "<div class='icon'>📭</div>"
        "<p>No hay datos para el período y filtros seleccionados.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()


st.markdown("<div class='section-header'>Calidad del agente · Eficiencia QA</div>",
            unsafe_allow_html=True)

col_cal, col_ef = st.columns(2)

with col_cal:
    pct_al = c['pct_alucinacion'] or 0
    color_al = "#DC2626" if pct_al > 30 else "#D97706" if pct_al > 10 else "#16A34A"
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-row">
            <span class="metric-name">Alucinaciones detectadas</span>
            <span class="metric-val" style="color:{color_al};">{pct_al}%</span>
        </div>
        <div style="font-size:12px;color:#64748B;margin-top:4px;">
            {c['con_alucinacion'] or 0} test cases marcados
        </div>
    </div>
    <div class="metric-card">
        <div class="metric-row">
            <span class="metric-name">Regeneraciones promedio</span>
            <span class="metric-val">{c['avg_regeneraciones'] or 0}</span>
        </div>
        <div style="font-size:12px;color:#64748B;margin-top:4px;">
            por test case hasta aprobación
        </div>
    </div>
    <div class="metric-card">
        <div class="metric-row">
            <span class="metric-name">Rechazados</span>
            <span class="metric-val">{c['rechazados'] or 0}</span>
        </div>
        <div style="font-size:12px;color:#64748B;margin-top:4px;">
            test cases rechazados en el período
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_ef:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-row">
            <span class="metric-name">Tiempo promedio por test case</span>
            <span class="metric-val kpi-accent">{fmt_duracion(datos['avg_min_tc'])}</span>
        </div>
        <div style="font-size:12px;color:#64748B;margin-top:4px;">
            desde generación hasta aprobación
        </div>
    </div>
    <div class="metric-card">
        <div class="metric-row">
            <span class="metric-name">Subidos a Xray</span>
            <span class="metric-val">{datos['pct_subidos']}%</span>
        </div>
        <div style="font-size:12px;color:#64748B;margin-top:4px;">
            del total de aprobados
        </div>
    </div>
    <div class="metric-card">
        <div class="metric-row">
            <span class="metric-name">Total aprobados</span>
            <span class="metric-val" style="color:#16A34A;">{c['aprobados'] or 0}</span>
        </div>
        <div style="font-size:12px;color:#64748B;margin-top:4px;">
            listos para subir o ya en Xray
        </div>
    </div>
    """, unsafe_allow_html=True)


st.markdown("<div class='section-header'>🧭 Evaluación de Vera</div>",
            unsafe_allow_html=True)

vera_d = datos["vera"]
_total_evaluadas_vera = vera_d["total_evaluadas"] or 0

if not _total_evaluadas_vera:
    st.markdown(
        "<div class='empty-state'>"
        "<div class='icon'>🧭</div>"
        "<p>Ninguna HU del período pasó todavía por la evaluación de Vera.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
else:
    _aprobadas_vera = _total_evaluadas_vera - (vera_d["bloqueadas"] or 0)
    _pct_aprobadas_vera = round(_aprobadas_vera / _total_evaluadas_vera * 100, 1)
    _avg_score_vera = vera_d["avg_score"] or 0
    _umbral_vera = cargar_configuracion_vera().umbral_score
    _color_score = (
        "#16A34A" if _avg_score_vera >= _umbral_vera
        else "#D97706" if _avg_score_vera >= _umbral_vera - 15
        else "#DC2626"
    )
    _pct_bloq_vera = vera_d["pct_bloqueadas"] or 0
    _color_bloq = "#DC2626" if _pct_bloq_vera > 30 else "#D97706" if _pct_bloq_vera > 10 else "#16A34A"

    col_ve1, col_ve2, col_ve3, col_ve4 = st.columns(4)
    with col_ve1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">HUs evaluadas</div>
            <div class="kpi-value">{_total_evaluadas_vera}</div>
            <div class="kpi-sub">por Vera en el período</div>
        </div>""", unsafe_allow_html=True)
    with col_ve2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Aprobadas</div>
            <div class="kpi-value" style="color:#16A34A;">{_aprobadas_vera}</div>
            <div class="kpi-sub">{_pct_aprobadas_vera}% del total evaluado</div>
        </div>""", unsafe_allow_html=True)
    with col_ve3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Bloqueadas</div>
            <div class="kpi-value" style="color:{_color_bloq};">{vera_d['bloqueadas'] or 0}</div>
            <div class="kpi-sub">{_pct_bloq_vera}% del total evaluado</div>
        </div>""", unsafe_allow_html=True)
    with col_ve4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Health Score promedio</div>
            <div class="kpi-value" style="color:{_color_score};">{_avg_score_vera}</div>
            <div class="kpi-sub">umbral de aprobación: {_umbral_vera}</div>
        </div>""", unsafe_allow_html=True)

    _vera_serie = datos["vera_serie"]
    col_vd, col_ve = st.columns(2)
    with col_vd:
        st.markdown(
            "<div style='font-size:11px;font-weight:600;color:#64748B;margin:12px 0 8px 0;'>"
            "Distribución de scores</div>",
            unsafe_allow_html=True,
        )
        render_distribucion_scores_vera(_vera_serie, _umbral_vera)
    with col_ve:
        st.markdown(
            "<div style='font-size:11px;font-weight:600;color:#64748B;margin:12px 0 8px 0;'>"
            "Evolución del score por cohorte</div>",
            unsafe_allow_html=True,
        )
        _tamano_cohorte_vera = st.slider(
            "HU por cohorte", min_value=3, max_value=20, value=10, key="vera_tamano_cohorte",
        )
        render_evolucion_scores_vera(_vera_serie, _tamano_cohorte_vera, _umbral_vera)


st.markdown("<div class='section-header'>🔎 Desenlace de alucinaciones</div>",
            unsafe_allow_html=True)
render_desenlace_alucinaciones(datos["desenlace_alucinaciones"])
