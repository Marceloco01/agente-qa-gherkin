"""
Indicadores de QA — el pulso operativo del equipo.

Sale de la mitad "equipo" de `pages/1_📊_Dashboard.py`: volumen del período,
estado de defectos por severidad (histórico y en vivo) y detalle por HU.
Absorbe además la evolución histórica por cohortes que vivía en
`pages/5_🎯_Seguimiento.py`; el resto de esa página --su "Resumen del período"
y su "Detalle por HU"-- mostraba lo MISMO que el Dashboard, que es justamente
por lo que las dos páginas se fusionaron acá.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

import calendar
from datetime import date

from application.seguimiento.motor import ejecutar_seguimiento
from frontend.auth import obtener_credenciales, requerir_sesion
from infrastructure.db.seguimiento_metricas import listar_metricas
from frontend.comun.panel_operativo import (
    aplicar_estilos, filtros_sidebar, fmt_duracion, badge, render_desenlace_alucinaciones, render_distribucion_scores_vera, render_evolucion_scores_vera, agregar_defectos_por_severidad, render_barras_severidad, cargar_datos, obtener_keys_hu_periodo,
)
from frontend.comun.estilo import aplicar_estilo_institucional

st.set_page_config(page_title="Indicadores de QA — NEXUS", page_icon="🎯", layout="wide")
requerir_sesion()
aplicar_estilos()


aplicar_estilo_institucional()

fecha_desde, fecha_hasta, key_hu_filtro = filtros_sidebar("ind_qa")

st.markdown(
    "<h1>Indicadores de QA</h1>"
    "<p class='fuente'>Volumen, defectos y detalle por historia</p>",
    unsafe_allow_html=True,
)

datos = cargar_datos(str(fecha_desde), str(fecha_hasta), key_hu_filtro)


v = datos["volumen"]

if not v["total_hus"]:
    st.markdown(
        "<div class='empty-state'>"
        "<div class='icon'>📭</div>"
        "<p>No hay datos para el período y filtros seleccionados.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()


st.markdown("<div class='section-header'>🩹 Estado de defectos por severidad</div>",
            unsafe_allow_html=True)

tab_defectos_historico, tab_defectos_vivo = st.tabs(["📚 Histórico", "🔴 En vivo"])

with tab_defectos_historico:
    st.markdown(
        "<span style='font-size:11px;color:#64748B;'>Del histórico cronológico ya cargado "
        "(seguimiento_hu_metricas) -- corpus más amplio, no solo HU de este agente. "
        "Filtrado por \"Fin En certificación\" dentro del período elegido.</span>",
        unsafe_allow_html=True,
    )
    _snapshots_periodo = listar_metricas(desde=fecha_desde, hasta=fecha_hasta)
    _textos_severidad_hist = [
        s.defectos_por_severidad for s in _snapshots_periodo if s.defectos_por_severidad
    ]
    if not _textos_severidad_hist:
        st.markdown(
            "<div class='empty-state'><div class='icon'>📭</div>"
            "<p>No hay datos de defectos del histórico en este período.</p></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
        render_barras_severidad(agregar_defectos_por_severidad(_textos_severidad_hist))
        st.caption(f"{len(_textos_severidad_hist)} HU del histórico con datos de defectos en este período.")

with tab_defectos_vivo:
    st.markdown(
        "<span style='font-size:11px;color:#64748B;'>Jira/Xray en vivo para las HU de este agente "
        "en el período -- no calcula cobertura real (sin costo de IA), pero sí hace llamadas de red "
        "reales, por eso corre solo cuando lo pedís.</span>",
        unsafe_allow_html=True,
    )
    if "defectos_vivo_cache" not in st.session_state:
        st.session_state.defectos_vivo_cache = {}
    _fp_defectos_vivo = (str(fecha_desde), str(fecha_hasta), key_hu_filtro)
    _defectos_vivo_cacheados = st.session_state.defectos_vivo_cache.get(_fp_defectos_vivo)

    if st.button(
        "Cargar defectos en vivo" if _defectos_vivo_cacheados is None else "Volver a cargar este período",
        key="boton_defectos_vivo",
    ):
        _keys_periodo = obtener_keys_hu_periodo(str(fecha_desde), str(fecha_hasta), key_hu_filtro)
        if not _keys_periodo:
            st.info("No hay HU de este agente en este período.")
        else:
            try:
                _creds_vivo = obtener_credenciales()
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                _jql_vivo = "key in (" + ", ".join(_keys_periodo) + ")"
                _estado_vivo = st.empty()

                def _reportar_progreso_vivo(etapa, hecho, total, texto):
                    _estado_vivo.markdown(
                        f"<span style='font-size:11px;color:#64748B;'>{texto}</span>",
                        unsafe_allow_html=True,
                    )

                with st.spinner(f"Consultando Jira/Xray para {len(_keys_periodo)} HU..."):
                    try:
                        _df_vivo = ejecutar_seguimiento(
                            _jql_vivo, _creds_vivo, calcular_cobertura_ia=False,
                            on_progreso=_reportar_progreso_vivo,
                        )
                    except Exception as exc:
                        st.error(f"No se pudo consultar en vivo: {exc}")
                        _df_vivo = None
                _estado_vivo.empty()
                if _df_vivo is not None:
                    _textos_severidad_vivo = (
                        _df_vivo["defectos_por_severidad"].dropna().tolist()
                        if not _df_vivo.empty else []
                    )
                    _defectos_vivo_cacheados = agregar_defectos_por_severidad(_textos_severidad_vivo)
                    st.session_state.defectos_vivo_cache[_fp_defectos_vivo] = _defectos_vivo_cacheados

    if _defectos_vivo_cacheados is not None:
        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
        render_barras_severidad(_defectos_vivo_cacheados)
    else:
        st.markdown(
            "<div class='empty-state'><div class='icon'>🔴</div>"
            "<p>Tocá \"Cargar defectos en vivo\" para consultar Jira/Xray de este período.</p></div>",
            unsafe_allow_html=True,
        )


st.markdown("<div class='section-header'>Detalle por Historia de Usuario</div>",
            unsafe_allow_html=True)

if not datos["detalle"]:
    st.markdown(
        "<div class='empty-state'><div class='icon'>📭</div>"
        "<p>No hay HUs en el período seleccionado.</p></div>",
        unsafe_allow_html=True,
    )
else:
    for r in datos["detalle"]:
        pct_ap = round(int(r["aprobados"] or 0) / int(r["total_tcs"] or 1) * 100)
        color_pct = "#16A34A" if pct_ap >= 70 else "#D97706" if pct_ap >= 40 else "#DC2626"
        tiempo = fmt_duracion(float(r["minutos_revision"])) if r["minutos_revision"] else "En curso"
        fecha = (r["fecha_inicio_proceso"].strftime("%d/%m/%Y %H:%M")
                 if r["fecha_inicio_proceso"] else "—")

        badges = []
        if r["subidos"]:
            badges.append(f'<span class="badge badge-info">↑ {r["subidos"]} Xray</span>')
        if r["con_alucinacion"]:
            badges.append('<span class="badge badge-warn">⚠ alucinación</span>')
        badges_html = " ".join(badges)

        st.markdown(f"""
        <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:6px;
                    padding:14px 20px;margin-bottom:8px;display:flex;
                    justify-content:space-between;align-items:center;gap:16px;">
            <div style="min-width:80px;">
                <span style="font-family:monospace;font-size:12px;background:#E2E8F0;
                             padding:2px 8px;border-radius:3px;color:#4F46E5;">
                    {r['key']}
                </span>
            </div>
            <div style="flex:1;overflow:hidden;">
                <div style="font-size:13px;color:#0F172A;white-space:nowrap;
                            overflow:hidden;text-overflow:ellipsis;"
                     title="{r['titulo']}">{r['titulo']}</div>
                <div style="font-size:11px;color:#64748B;margin-top:2px;">
                    {r['total_tcs'] or 0} test cases · {badges_html}
                </div>
            </div>
            <div style="text-align:right;min-width:120px;">
                <div style="font-size:18px;font-weight:700;
                            font-variant-numeric:tabular-nums;color:{color_pct};">
                    {pct_ap}%
                </div>
                <div style="font-size:11px;color:#64748B;">aprobados</div>
            </div>
            <div style="text-align:right;min-width:90px;">
                <div style="font-size:16px;font-weight:600;color:#4F46E5;
                            font-variant-numeric:tabular-nums;">{tiempo}</div>
                <div style="font-size:11px;color:#64748B;">revisión</div>
            </div>
            <div style="text-align:right;min-width:110px;">
                <div style="font-size:11px;color:#64748B;">{fecha}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

st.markdown(
    f"<p style='font-size:11px;color:#64748B;margin-top:12px;'>"
    f"Período: {fecha_desde.strftime('%d/%m/%Y')} → "
    f"{fecha_hasta.strftime('%d/%m/%Y')} · "
    f"Actualización automática cada 60 s</p>",
    unsafe_allow_html=True,
)


st.markdown("<div class='section-header'>📈 Evolución histórica por cohortes</div>", unsafe_allow_html=True)
st.caption(
    "Lee `seguimiento_hu_metricas` (Postgres) -- lo que ya quedó guardado por "
    "`scripts/procesar_seguimiento_historico.py`. No recalcula nada acá."
)

_snapshots = listar_metricas()

if not _snapshots:
    st.markdown(
        "<div class='empty-state'><div class='icon'>📈</div>"
        "<p>Todavía no hay snapshots guardados en la base -- corré "
        "<code>scripts/procesar_seguimiento_historico.py</code> primero.</p></div>",
        unsafe_allow_html=True,
    )
else:
    _df_hist = pd.DataFrame([{
        "hu_key": s.hu_key,
        "fecha": s.fecha_certificacion_terminada.date() if s.fecha_certificacion_terminada else None,
        "indice_ejecucion_pct": s.indice_ejecucion_pct,
        "indice_cobertura_densidad_pct": s.indice_cobertura_densidad_pct,
        "indice_cobertura_real_pct": s.indice_cobertura_real_pct,
        "test_pass_rate_pct": s.test_pass_rate_pct,
        "num_defectos_detectados": s.num_defectos_detectados,
        "num_defectos_resueltos": s.num_defectos_resueltos,
    } for s in _snapshots])


    _fechas_disponibles = _df_hist["fecha"].dropna()
    _meses_disponibles = sorted({(f.year, f.month) for f in _fechas_disponibles})

    _modo_filtro = st.radio(
        "Ver período", options=["Todo el período", "Mes específico", "Rango personalizado"],
        horizontal=True, key="evolucion_modo_filtro",
    )

    if _modo_filtro == "Mes específico":
        if not _meses_disponibles:
            st.info("No hay HU con fecha para filtrar por mes.")
        else:
            _mes_elegido = st.selectbox(
                "Mes", options=_meses_disponibles, format_func=lambda ym: f"{ym[0]}-{ym[1]:02d}",
                index=len(_meses_disponibles) - 1, key="evolucion_mes_elegido",
            )
            _df_hist = _df_hist[_df_hist["fecha"].apply(
                lambda f: f is not None and (f.year, f.month) == _mes_elegido
            )]
    elif _modo_filtro == "Rango personalizado":
        _col_desde, _col_hasta = st.columns(2)
        _min_fecha = _fechas_disponibles.min() if len(_fechas_disponibles) else date.today()
        _max_fecha = _fechas_disponibles.max() if len(_fechas_disponibles) else date.today()
        with _col_desde:
            _rango_desde = st.date_input("Desde", value=_min_fecha, key="evolucion_rango_desde")
        with _col_hasta:
            _rango_hasta = st.date_input("Hasta", value=_max_fecha, key="evolucion_rango_hasta")
        _df_hist = _df_hist[_df_hist["fecha"].apply(
            lambda f: f is not None and _rango_desde <= f <= _rango_hasta
        )]

    if _df_hist.empty:
        st.markdown(
            "<div class='empty-state'><div class='icon'>🗓️</div>"
            "<p>No hay HU certificadas en ese período -- probá otro rango o mes. "
            "(Ojo: no hay ninguna HU certificada durante todo 2025 -- el histórico "
            "salta de julio 2024 a enero 2026, ver la cohorte 1 más abajo con "
            "'Todo el período'.)</p></div>",
            unsafe_allow_html=True,
        )
    else:
        col_cohorte_a, col_cohorte_b = st.columns([1, 1])
        with col_cohorte_a:
            _tamano_cohorte_vista = st.slider(
                "HU por cohorte", min_value=3, max_value=20, value=10, key="evolucion_tamano_cohorte",
                help="Mismo criterio que el backfill: agrupa de más antigua a más nueva (no por mes calendario).",
            )
        with col_cohorte_b:
            _usar_mediana = st.checkbox(
                "Usar mediana en vez de promedio", value=True, key="evolucion_usar_mediana",
                help=(
                    "La densidad de cobertura en particular tiene outliers extremos (una HU con varios Test "
                    "Plans combinados puede dar miles de %) que distorsionan un promedio simple -- la mediana "
                    "es más representativa de la cohorte. Se puede destildar para comparar."
                ),
            )


        _UMBRAL_GAP_DIAS = 45
        _df_hist = _df_hist.reset_index(drop=True)
        _asignaciones_cohorte = []
        _num_cohorte_actual = 0
        _tamano_cohorte_actual = 0
        _fecha_anterior = None
        for _, _fila_hist in _df_hist.iterrows():
            _fecha_fila = _fila_hist["fecha"]
            _hay_salto = (
                _fecha_fila is not None and _fecha_anterior is not None
                and (_fecha_fila - _fecha_anterior).days > _UMBRAL_GAP_DIAS
            )
            if _tamano_cohorte_actual > 0 and (_tamano_cohorte_actual >= _tamano_cohorte_vista or _hay_salto):
                _num_cohorte_actual += 1
                _tamano_cohorte_actual = 0
            _asignaciones_cohorte.append(_num_cohorte_actual)
            _tamano_cohorte_actual += 1
            if _fecha_fila is not None:
                _fecha_anterior = _fecha_fila
        _df_hist["cohorte"] = _asignaciones_cohorte


        _INDICES_EVOLUCION = [
            ("indice_ejecucion_pct", "Índice de ejecución", "#4F46E5", True),
            ("test_pass_rate_pct", "Test Pass Rate", "#16A34A", True),
            ("indice_cobertura_real_pct", "Cobertura real (IA)", "#16A34A", True),
            ("indice_cobertura_densidad_pct", "Densidad de cobertura", "#8B5CF6", False),
        ]

        _filas_cohorte = []
        for _num_cohorte, _grupo in _df_hist.groupby("cohorte"):
            _fechas_validas = _grupo["fecha"].dropna()
            _rango = (
                f"{_fechas_validas.min().isoformat()} → {_fechas_validas.max().isoformat()}"
                if len(_fechas_validas) else "(sin fecha)"
            )
            _fila = {"cohorte": int(_num_cohorte) + 1, "rango": _rango, "n": len(_grupo)}
            for _col, _etq, _clr, _cal in _INDICES_EVOLUCION:
                _vals = _grupo[_col].dropna()
                if len(_vals):
                    _fila[f"{_col}_valor"] = round(_vals.median() if _usar_mediana else _vals.mean(), 1)
                else:
                    _fila[f"{_col}_valor"] = None
                _fila[f"{_col}_n"] = len(_vals)
            _filas_cohorte.append(_fila)
        _df_cohortes = pd.DataFrame(_filas_cohorte)

        st.caption(
            f"{len(_df_hist)} de {len(_snapshots)} snapshots (según el filtro de período) agrupados en "
            f"{len(_df_cohortes)} cohortes de hasta {_tamano_cohorte_vista} HU cada una (se cortan antes "
            f"si hay más de {_UMBRAL_GAP_DIAS} días sin una nueva HU certificada) · valores mostrados: "
            f"{'mediana' if _usar_mediana else 'promedio'}."
        )

        for _col, _etiqueta, _color, _es_calidad in _INDICES_EVOLUCION:
            _col_valor = f"{_col}_valor"
            _vals_no_nulos = _df_cohortes[_col_valor].dropna()
            st.markdown(
                f"<div style='margin-top:16px;margin-bottom:6px;font-size:12px;font-weight:600;color:#0F172A;'>{_etiqueta}</div>",
                unsafe_allow_html=True,
            )
            if _vals_no_nulos.empty:
                st.markdown("<div class='kpi-sub'>sin datos en ninguna cohorte</div>", unsafe_allow_html=True)
                continue


            _puntos = [
                (i, float(v)) for i, v in enumerate(_df_cohortes[_col_valor]) if v is not None and not pd.isna(v)
            ]
            if len(_puntos) == 1:
                st.markdown(
                    "<div style='font-size:11px;color:#64748B;margin-bottom:6px;'>"
                    "Una sola cohorte con dato -- no se puede calcular tendencia.</div>",
                    unsafe_allow_html=True,
                )
            elif len(_puntos) >= 2:
                _k = len(_puntos)
                _sum_x = sum(p[0] for p in _puntos)
                _sum_y = sum(p[1] for p in _puntos)
                _sum_xy = sum(p[0] * p[1] for p in _puntos)
                _sum_x2 = sum(p[0] ** 2 for p in _puntos)
                _denominador = _k * _sum_x2 - _sum_x ** 2
                if _denominador != 0:
                    _pendiente = (_k * _sum_xy - _sum_x * _sum_y) / _denominador
                    _intercepto = (_sum_y - _pendiente * _sum_x) / _k
                    _valor_inicio_reg = _intercepto
                    _valor_fin_reg = _pendiente * (_k - 1) + _intercepto
                    _delta_tendencia = _valor_fin_reg - _valor_inicio_reg
                    _UMBRAL_ESTABLE = 2.0

                    if _delta_tendencia > _UMBRAL_ESTABLE:
                        _texto_tendencia = (
                            f"↗ {'Mejorando' if _es_calidad else 'Aumentando'} "
                            f"({_delta_tendencia:+.1f} pts, primera → última cohorte)"
                        )
                        _color_tendencia = "#16A34A" if _es_calidad else "#64748B"
                    elif _delta_tendencia < -_UMBRAL_ESTABLE:
                        _texto_tendencia = (
                            f"↘ {'Empeorando' if _es_calidad else 'Disminuyendo'} "
                            f"({_delta_tendencia:+.1f} pts, primera → última cohorte)"
                        )
                        _color_tendencia = "#D97706" if _es_calidad else "#64748B"
                    else:
                        _texto_tendencia = f"→ Estable ({_delta_tendencia:+.1f} pts, primera → última cohorte)"
                        _color_tendencia = "#64748B"

                    st.markdown(
                        f"<div style='font-size:11px;color:{_color_tendencia};margin-bottom:2px;'>{_texto_tendencia}</div>",
                        unsafe_allow_html=True,
                    )


                    _W, _H, _margen = 600, 70, 10
                    _min_val = min(p[1] for p in _puntos)
                    _max_val = max(p[1] for p in _puntos)
                    _rango_real_texto = f"{_min_val:.1f}% – {_max_val:.1f}%"
                    if _max_val == _min_val:
                        _min_val -= 1
                        _max_val += 1
                    else:
                        _colchon = (_max_val - _min_val) * 0.1
                        _min_val -= _colchon
                        _max_val += _colchon
                    _x_paso = (_W - 2 * _margen) / (_k - 1)

                    def _coord(i, v):
                        _x = _margen + i * _x_paso
                        _y = _margen + (_max_val - v) / (_max_val - _min_val) * (_H - 2 * _margen)
                        return _x, _y

                    _puntos_svg = " ".join(f"{_coord(i, v)[0]:.1f},{_coord(i, v)[1]:.1f}" for i, v in _puntos)
                    _x_ini, _y_ini = _coord(0, _valor_inicio_reg)
                    _x_fin, _y_fin = _coord(_k - 1, _valor_fin_reg)
                    _circulos_svg = "".join(
                        f"<circle cx='{_coord(i, v)[0]:.1f}' cy='{_coord(i, v)[1]:.1f}' r='4' fill='{_color}'/>"
                        for i, v in _puntos
                    )
                    _svg = (
                        f"<svg viewBox='0 0 {_W} {_H}' style='width:100%;height:110px;margin-bottom:2px;' preserveAspectRatio='none'>"
                        f"<polyline points='{_puntos_svg}' fill='none' stroke='{_color}' stroke-width='2.5'/>"
                        f"<line x1='{_x_ini:.1f}' y1='{_y_ini:.1f}' x2='{_x_fin:.1f}' y2='{_y_fin:.1f}' "
                        f"stroke='{_color}' stroke-width='1.5' stroke-dasharray='4,3' opacity='0.55'/>"
                        f"{_circulos_svg}"
                        "</svg>"
                    )
                    st.markdown(_svg, unsafe_allow_html=True)
                    st.markdown(
                        f"<div style='font-size:10px;color:#64748B;margin-bottom:8px;'>"
                        f"Eje vertical ajustado a {_rango_real_texto} (no es una escala 0-100%) -- "
                        f"para comparar magnitudes reales, mirá los valores exactos de las barras de abajo.</div>",
                        unsafe_allow_html=True,
                    )

            _maximo = max(float(_vals_no_nulos.max()), 1.0)


            _filas_html = []
            for _, _fila in _df_cohortes.iterrows():
                _valor = _fila[_col_valor]
                _etiqueta_fila = f"Cohorte {_fila['cohorte']} · {_fila['rango']}"
                if _valor is None or pd.isna(_valor):
                    _filas_html.append(
                        "<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>"
                        f"<div style='width:230px;font-size:11px;color:#64748B;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{_etiqueta_fila}</div>"
                        "<div style='flex:1;font-size:11px;color:#64748B;'>sin datos</div></div>"
                    )
                    continue
                _ancho_pct = min(100.0, round(_valor / _maximo * 100, 1))
                _n = int(_fila[f"{_col}_n"])
                _filas_html.append(
                    "<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>"
                    f"<div style='width:230px;font-size:11px;color:#64748B;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{_etiqueta_fila}</div>"
                    "<div style='flex:1;background:#F5F7FB;border-radius:3px;height:18px;'>"
                    f"<div style='width:{_ancho_pct}%;background:{_color};height:100%;border-radius:3px;'></div>"
                    "</div>"
                    "<div style='width:90px;text-align:right;font-size:12px;font-variant-numeric:tabular-nums;color:#0F172A;white-space:nowrap;'>"
                    f"{_valor}% <span style='color:#64748B;font-size:10px;'>(n={_n})</span>"
                    "</div></div>"
                )
            st.markdown("".join(_filas_html), unsafe_allow_html=True)

        with st.expander("Ver tabla de cohortes (valores exactos)"):
            st.dataframe(_df_cohortes, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Descargar cohortes (CSV)",
                data=_df_cohortes.to_csv(index=False).encode("utf-8"),
                file_name="evolucion_por_cohortes.csv",
                mime="text/csv",
                key="descargar_cohortes",
            )
