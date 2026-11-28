"""
Capa común de los paneles operativos — estilos, filtros y queries.

Sale de `pages/1_📊_Dashboard.py`, que concentraba en 1.208 líneas dos cosas
distintas: los indicadores del AGENTE (Vera, Gio, alucinaciones) y los del
EQUIPO QA (volumen, defectos, detalle por HU). Se separaron en dos páginas
--"Indicadores de IA" e "Indicadores de QA"-- y todo lo que las dos necesitan
vive acá: el CSS, los filtros de la barra lateral y la capa de consultas.

El código se movió por rangos de línea, SIN retipearlo, para no introducir
diferencias silenciosas. Los únicos cambios son mecánicos y están acá
declarados:
  - el bloque de filtros pasó de correr suelto a ser `filtros_sidebar()`, que
    devuelve (desde, hasta, key_hu) en vez de dejar variables globales;
  - las claves de los widgets se parametrizan con un prefijo, porque ahora hay
    dos páginas que los usan y compartir clave hace que una pise el estado de
    la otra;
  - los helpers perdieron el guion bajo inicial: dejaron de ser privados de un
    módulo para ser la interfaz que las dos páginas consumen.

`1_📊_Dashboard.py` y `5_🎯_Seguimiento.py` quedan fuera del router y se pueden
borrar cuando haya permiso; no se borran desde acá.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import text

from application.seguimiento.motor import ejecutar_seguimiento
from frontend.auth import obtener_credenciales, requerir_sesion
from infrastructure.config import cargar_configuracion_vera
from infrastructure.db.conexion import obtener_sesion
from infrastructure.db.seguimiento_metricas import listar_metricas


def aplicar_estilos() -> None:
    st.markdown("""
    <style>
    /* Base */
    [data-testid="stAppViewContainer"] {
        background-color: #F5F7FB;
        color: #0F172A;
    }
    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E2E8F0;
    }
    [data-testid="stSidebar"] * {
        color: #0F172A !important;
    }
    
    /* KPI cards */
    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-left: 3px solid #4F46E5;
        border-radius: 6px;
        padding: 20px 24px;
        margin-bottom: 8px;
    }
    .kpi-label {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #64748B;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 36px;
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        color: #0F172A;
        line-height: 1;
    }
    .kpi-sub {
        font-size: 12px;
        color: #64748B;
        margin-top: 4px;
    }
    .kpi-accent { color: #4F46E5; }
    
    /* Section headers */
    .section-header {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #64748B;
        border-bottom: 1px solid #E2E8F0;
        padding-bottom: 8px;
        margin: 28px 0 16px 0;
    }
    
    /* Metric secondary cards */
    .metric-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 6px;
        padding: 16px 20px;
        margin-bottom: 8px;
    }
    .metric-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .metric-name { font-size: 13px; color: #64748B; }
    .metric-val  { font-size: 20px; font-weight: 600;
                   font-variant-numeric: tabular-nums; color: #0F172A; }
    
    /* Tabla detalle */
    .detail-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
    }
    .detail-table th {
        text-align: left;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #64748B;
        border-bottom: 1px solid #E2E8F0;
        padding: 8px 12px;
    }
    .detail-table td {
        padding: 10px 12px;
        border-bottom: 1px solid #FFFFFF;
        color: #0F172A;
    }
    .detail-table tr:hover td { background: #F1F5F9; }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 3px;
        font-size: 11px;
        font-weight: 600;
    }
    .badge-ok   { background: #DCFCE7; color: #16A34A; }
    .badge-warn { background: #FEF3C7; color: #D97706; }
    .badge-err  { background: #FEE2E2; color: #DC2626; }
    .badge-info { background: #E0E7FF; color: #4F46E5; }
    .key-chip {
        font-family: monospace;
        font-size: 12px;
        background: #E2E8F0;
        padding: 2px 6px;
        border-radius: 3px;
        color: #4F46E5;
    }
    .empty-state {
        text-align: center;
        padding: 60px 20px;
        color: #64748B;
    }
    .empty-state .icon { font-size: 32px; margin-bottom: 12px; }
    .empty-state p { font-size: 14px; margin: 0; }
    </style>
    """, unsafe_allow_html=True)


def fmt_duracion(minutos: float | None) -> str:
    """Formatea minutos en 'Xh Ym' o 'Xm' o '—' si no hay dato."""
    if minutos is None:
        return "—"
    minutos = round(minutos)
    if minutos < 1:
        return "< 1 min"
    if minutos < 60:
        return f"{minutos} min"
    h, m = divmod(minutos, 60)
    return f"{h}h {m}m" if m else f"{h}h"


def badge(texto: str, tipo: str) -> str:
    return f'<span class="badge badge-{tipo}">{texto}</span>'


_DESENLACES_ALUCINACION = [
    ("editada", "Editada", "ok", "#16A34A"),
    ("rechazada", "Rechazada", "err", "#DC2626"),
    ("aceptada", "Aceptada tal cual", "warn", "#D97706"),
    ("pendiente", "Pendiente de revisión", "info", "#4F46E5"),
]


def render_desenlace_alucinaciones(desenlace: dict[str, int]) -> None:
    total = sum(desenlace.values())
    if total == 0:
        st.markdown(
            "<div class='empty-state'><div class='icon'>✅</div>"
            "<p>Ningún test case fue marcado con una posible alucinación en este período.</p></div>",
            unsafe_allow_html=True,
        )
        return
    filas_html = []
    for clave, etiqueta, tipo_badge, color in _DESENLACES_ALUCINACION:
        cantidad = desenlace.get(clave, 0)
        pct = round(cantidad / total * 100) if total else 0
        fila = (
            "<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;'>"
            f"<div style='width:160px;font-size:12px;color:#0F172A;'>{badge(etiqueta, tipo_badge)}</div>"
            "<div style='flex:1;background:#F1F5F9;border-radius:3px;height:20px;'>"
            f"<div style='width:{pct}%;background:{color};height:20px;border-radius:3px;'></div></div>"
            f"<div style='width:90px;text-align:right;font-size:12px;color:#64748B;'>{cantidad} ({pct}%)</div>"
            "</div>"
        )
        filas_html.append(fila)
    st.markdown("".join(filas_html), unsafe_allow_html=True)
    st.caption(
        f"{total} test cases fueron marcados con una posible alucinación en algún momento de este período "
        "(distinto del % vigente de arriba, que solo cuenta los que siguen marcados ahora mismo)."
    )


_BUCKETS_SCORE_VERA = [(0, 20), (21, 40), (41, 60), (61, 80), (81, 100)]


def render_distribucion_scores_vera(serie: list[dict], umbral: int) -> None:
    total = len(serie)
    if total == 0:
        return
    filas_html = []
    for piso, techo in _BUCKETS_SCORE_VERA:
        cantidad = sum(1 for fila in serie if piso <= (fila["vera_score"] or -1) <= techo)
        pct = round(cantidad / total * 100) if total else 0


        if piso >= umbral:
            color = "#16A34A"
        elif techo < umbral:
            color = "#DC2626"
        else:
            color = "#D97706"
        etiqueta = f"{piso}-{techo}"
        fila = (
            "<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;'>"
            f"<div style='width:70px;font-size:12px;color:#0F172A;font-variant-numeric:tabular-nums;'>{etiqueta}</div>"
            "<div style='flex:1;background:#F1F5F9;border-radius:3px;height:20px;'>"
            f"<div style='width:{pct}%;background:{color};height:20px;border-radius:3px;'></div></div>"
            f"<div style='width:90px;text-align:right;font-size:12px;color:#64748B;'>{cantidad} ({pct}%)</div>"
            "</div>"
        )
        filas_html.append(fila)
    st.markdown("".join(filas_html), unsafe_allow_html=True)
    st.caption(f"{total} HU evaluadas por Vera en el período · umbral de aprobación: {umbral}.")


def render_evolucion_scores_vera(serie: list[dict], tamano_cohorte: int, umbral: int) -> None:
    if len(serie) < 2:
        st.markdown(
            "<div style='font-size:12px;color:#64748B;'>Hacen falta al menos 2 HU evaluadas en el "
            "período para mostrar una evolución.</div>",
            unsafe_allow_html=True,
        )
        return


    _GAP_MAXIMO_DIAS = 45
    cohortes: list[list[dict]] = []
    actual: list[dict] = []
    fecha_anterior = None
    for fila in serie:
        fecha_actual = fila["fecha_creacion"]
        hay_salto = (
            fecha_anterior is not None
            and (fecha_actual - fecha_anterior).days > _GAP_MAXIMO_DIAS
        )
        if actual and (len(actual) >= tamano_cohorte or hay_salto):
            cohortes.append(actual)
            actual = []
        actual.append(fila)
        fecha_anterior = fecha_actual
    if actual:
        cohortes.append(actual)

    filas_cohorte = []
    for i, grupo in enumerate(cohortes):
        scores = [f["vera_score"] for f in grupo if f["vera_score"] is not None]
        promedio = round(sum(scores) / len(scores), 1) if scores else None
        rango = f"{grupo[0]['fecha_creacion'].date()} → {grupo[-1]['fecha_creacion'].date()}"
        filas_cohorte.append({"cohorte": i + 1, "rango": rango, "n": len(grupo), "avg_score": promedio})

    if len(filas_cohorte) == 1:
        st.markdown(
            "<div style='font-size:11px;color:#64748B;margin-bottom:6px;'>"
            "Una sola cohorte en el período -- no se puede calcular tendencia.</div>",
            unsafe_allow_html=True,
        )
    else:


        puntos = [(i, f["avg_score"]) for i, f in enumerate(filas_cohorte) if f["avg_score"] is not None]
        if len(puntos) >= 2:
            k = len(puntos)
            sum_x = sum(p[0] for p in puntos)
            sum_y = sum(p[1] for p in puntos)
            sum_xy = sum(p[0] * p[1] for p in puntos)
            sum_x2 = sum(p[0] ** 2 for p in puntos)
            denominador = k * sum_x2 - sum_x ** 2
            if denominador != 0:
                pendiente = (k * sum_xy - sum_x * sum_y) / denominador
                intercepto = (sum_y - pendiente * sum_x) / k
                valor_inicio = intercepto
                valor_fin = pendiente * (k - 1) + intercepto
                delta = valor_fin - valor_inicio
                umbral_estable = 2.0

                if delta > umbral_estable:
                    texto = f"↗ Mejorando ({delta:+.1f} pts, primera → última cohorte)"
                    color_tendencia = "#16A34A"
                elif delta < -umbral_estable:
                    texto = f"↘ Empeorando ({delta:+.1f} pts, primera → última cohorte)"
                    color_tendencia = "#D97706"
                else:
                    texto = f"→ Estable ({delta:+.1f} pts, primera → última cohorte)"
                    color_tendencia = "#64748B"

                st.markdown(
                    f"<div style='font-size:11px;color:{color_tendencia};margin-bottom:10px;'>{texto}</div>",
                    unsafe_allow_html=True,
                )


    filas_html = []
    for f in filas_cohorte:
        avg = f["avg_score"]
        if avg is None:
            continue
        color = "#16A34A" if avg >= umbral else "#D97706" if avg >= umbral - 15 else "#DC2626"
        etiqueta = f"Cohorte {f['cohorte']} · {f['rango']} ({f['n']} HU)"
        fila = (
            "<div style='margin-bottom:8px;'>"
            f"<div style='font-size:11px;color:#64748B;margin-bottom:2px;'>{etiqueta}</div>"
            "<div style='display:flex;align-items:center;gap:10px;'>"
            "<div style='flex:1;background:#F1F5F9;border-radius:3px;height:16px;'>"
            f"<div style='width:{avg}%;background:{color};height:16px;border-radius:3px;'></div></div>"
            f"<div style='width:40px;text-align:right;font-size:12px;color:#0F172A;font-variant-numeric:tabular-nums;'>{avg}</div>"
            "</div></div>"
        )
        filas_html.append(fila)
    st.markdown("".join(filas_html), unsafe_allow_html=True)


_RE_SEVERIDAD = re.compile(r"(Menor|Mediano|Mayor|Grave):\s*(\d+)/(\d+)")


_NIVELES_SEVERIDAD_DASH = [
    ("Grave", "Crítica", "#DC2626"),
    ("Mayor", "Alta", "#D97706"),
    ("Mediano", "Media", "#F59E0B"),
    ("Menor", "Baja", "#16A34A"),
]


def agregar_defectos_por_severidad(textos: list[str]) -> dict[str, dict[str, int]]:
    """Suma resueltos/detectados por nivel a partir de varios textos compactos."""
    acumulado = {nivel: {"resueltos": 0, "detectados": 0} for nivel, _, _ in _NIVELES_SEVERIDAD_DASH}
    for texto in textos:
        if not texto:
            continue
        for nivel, resueltos, detectados in _RE_SEVERIDAD.findall(texto):
            acumulado[nivel]["resueltos"] += int(resueltos)
            acumulado[nivel]["detectados"] += int(detectados)
    return acumulado


def render_barras_severidad(acumulado: dict[str, dict[str, int]]) -> None:
    max_detectados = max((datos["detectados"] for datos in acumulado.values()), default=0)
    if max_detectados == 0:
        st.markdown(
            "<div class='empty-state'><div class='icon'>✅</div>"
            "<p>Sin defectos detectados en este período.</p></div>",
            unsafe_allow_html=True,
        )
        return
    filas_html = []
    for nivel, etiqueta, color in _NIVELES_SEVERIDAD_DASH:
        detectados = acumulado[nivel]["detectados"]
        resueltos = acumulado[nivel]["resueltos"]
        pct_ancho = round(detectados / max_detectados * 100) if max_detectados else 0
        fila = (
            "<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;'>"
            f"<div style='width:64px;font-size:12px;color:#0F172A;'>{etiqueta}</div>"
            "<div style='flex:1;background:#F1F5F9;border-radius:3px;height:20px;'>"
            f"<div style='width:{pct_ancho}%;background:{color};height:20px;border-radius:3px;'></div></div>"
            f"<div style='width:110px;text-align:right;font-size:12px;color:#64748B;'>{resueltos}/{detectados} resueltos</div>"
            "</div>"
        )
        filas_html.append(fila)
    st.markdown("".join(filas_html), unsafe_allow_html=True)


def filtros_sidebar(prefijo: str = "panel") -> tuple:
    """Filtros de período y HU. Devuelve (desde, hasta, key_hu)."""
    with st.sidebar:
        st.markdown("### 🔍 Filtros")
        st.markdown("---")

        hoy = datetime.now(timezone.utc).date()
        hace_30 = hoy - timedelta(days=30)

        vista_periodo = st.radio(
            "Período",
            ["Todo el período", "Mes específico", "Rango personalizado"],
            key=f"{prefijo}_vista_periodo",
        )

        if vista_periodo == "Todo el período":
            fecha_desde = date(2000, 1, 1)
            fecha_hasta = hoy
        elif vista_periodo == "Mes específico":
            _mes_elegido = st.date_input(
                "Mes", value=hoy.replace(day=1), max_value=hoy, key=f"{prefijo}_mes_elegido",
            )
            fecha_desde = _mes_elegido.replace(day=1)
            _siguiente_mes = (
                fecha_desde.replace(year=fecha_desde.year + 1, month=1)
                if fecha_desde.month == 12
                else fecha_desde.replace(month=fecha_desde.month + 1)
            )
            fecha_hasta = min(_siguiente_mes - timedelta(days=1), hoy)
        else:
            fecha_desde = st.date_input("Desde", value=hace_30, max_value=hoy, key=f"{prefijo}_desde")
            fecha_hasta = st.date_input("Hasta", value=hoy, max_value=hoy, key=f"{prefijo}_hasta")

        if fecha_desde > fecha_hasta:
            st.error("'Desde' no puede ser mayor que 'Hasta'.")
            st.stop()

        key_hu_filtro = st.text_input(
            "HU específica (opcional)",
            placeholder="ej. PROJ-13",
        ).strip().upper() or None

        st.markdown("---")
        st.markdown(
            "<span style='font-size:11px;color:#64748B;'>"
            "Datos desde PostgreSQL en tiempo real"
            "</span>",
            unsafe_allow_html=True,
        )


    return fecha_desde, fecha_hasta, key_hu_filtro


@st.cache_data(ttl=60, show_spinner=False)
def cargar_datos(desde: str, hasta: str, key_hu: str | None) -> dict:
    """
    Carga todas las métricas del Dashboard en una sola apertura de sesión.
    Se cachea 60 segundos para no golpear la BD en cada rerun de Streamlit.
    """
    filtro_fecha_hu = "AND hu.fecha_creacion::date BETWEEN :desde AND :hasta"
    filtro_fecha_tc = "AND tc.fecha_creacion::date BETWEEN :desde AND :hasta"
    filtro_key = "AND hu.key = :key_hu" if key_hu else ""

    params: dict = {"desde": desde, "hasta": hasta}
    if key_hu:
        params["key_hu"] = key_hu

    with obtener_sesion() as sesion:


        volumen = sesion.execute(text(f"""
            SELECT
                COUNT(DISTINCT hu.key)                          AS total_hus,
                COUNT(tc.id)                                    AS total_tcs,
                ROUND(COUNT(tc.id)::numeric /
                    NULLIF(COUNT(DISTINCT hu.key), 0), 1)       AS promedio_tcs_por_hu
            FROM historias_usuario hu
            LEFT JOIN test_cases tc ON tc.hu_key = hu.key
            WHERE hu.key NOT IN (
                SELECT DISTINCT test_plan_key FROM historias_usuario
                WHERE test_plan_key IS NOT NULL
            )
            {filtro_fecha_hu}
            {filtro_key}
        """), params).mappings().one()


        calidad = sesion.execute(text(f"""
            SELECT
                COUNT(*)                                            AS total,
                SUM(CASE WHEN estado = 'aprobado'
                          OR estado = 'subido_a_xray' THEN 1 ELSE 0 END) AS aprobados,
                SUM(CASE WHEN estado = 'rechazado'   THEN 1 ELSE 0 END) AS rechazados,
                SUM(CASE WHEN alucinacion_detectada = true THEN 1 ELSE 0 END) AS con_alucinacion,
                ROUND(
                    SUM(CASE WHEN estado = 'aprobado'
                              OR estado = 'subido_a_xray' THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*), 0) * 100, 1
                )                                                   AS pct_aprobados,
                ROUND(
                    SUM(CASE WHEN alucinacion_detectada = true THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*), 0) * 100, 1
                )                                                   AS pct_alucinacion,
                ROUND(AVG(version_contenido), 1)                    AS avg_regeneraciones
            FROM test_cases tc
            JOIN historias_usuario hu ON hu.key = tc.hu_key
            WHERE hu.key NOT IN (
                SELECT DISTINCT test_plan_key FROM historias_usuario
                WHERE test_plan_key IS NOT NULL
            )
            {filtro_fecha_tc}
            {filtro_key}
        """), params).mappings().one()


        eficiencia = sesion.execute(text(f"""
            SELECT
                ROUND(AVG(max_actualizacion_hu - inicio_proceso), 1)
                    AS avg_min_revision_hu,
                ROUND(AVG(avg_min_tc), 1)
                    AS avg_min_por_tc,
                SUM(subidos)    AS subidos,
                SUM(total_tcs)  AS total_tcs
            FROM (
                SELECT
                    hu.key,
                    EXTRACT(EPOCH FROM (
                        MAX(tc.fecha_actualizacion) - hu.fecha_inicio_proceso
                    )) / 60                                         AS max_actualizacion_hu,
                    EXTRACT(EPOCH FROM hu.fecha_inicio_proceso) / 60
                        AS inicio_proceso,
                    ROUND(AVG(
                        EXTRACT(EPOCH FROM (
                            tc.fecha_actualizacion - tc.fecha_creacion
                        )) / 60
                    ), 1)                                           AS avg_min_tc,
                    SUM(CASE WHEN tc.estado = 'subido_a_xray'
                             THEN 1 ELSE 0 END)                     AS subidos,
                    COUNT(tc.id)                                    AS total_tcs
                FROM test_cases tc
                JOIN historias_usuario hu ON hu.key = tc.hu_key
                WHERE hu.key NOT IN (
                    SELECT DISTINCT test_plan_key FROM historias_usuario
                    WHERE test_plan_key IS NOT NULL
                )
                AND hu.fecha_inicio_proceso IS NOT NULL
                {filtro_fecha_tc}
                {filtro_key}
                GROUP BY hu.key, hu.fecha_inicio_proceso
            ) sub
        """), params).mappings().one()


        tipos_cobertura_filas = sesion.execute(text(f"""
            SELECT tc.tipo_cobertura AS tipo, COUNT(*) AS cantidad
            FROM test_cases tc
            JOIN historias_usuario hu ON hu.key = tc.hu_key
            WHERE hu.key NOT IN (
                SELECT DISTINCT test_plan_key FROM historias_usuario
                WHERE test_plan_key IS NOT NULL
            )
            AND tc.tipo_cobertura IS NOT NULL
            {filtro_fecha_tc}
            {filtro_key}
            GROUP BY tc.tipo_cobertura
        """), params).mappings().all()


        vera = sesion.execute(text(f"""
            SELECT
                COUNT(*) FILTER (WHERE vera_aprobada IS NOT NULL)      AS total_evaluadas,
                COUNT(*) FILTER (WHERE vera_aprobada = false)          AS bloqueadas,
                ROUND(AVG(vera_score), 1)                              AS avg_score,
                ROUND(
                    COUNT(*) FILTER (WHERE vera_aprobada = false)::numeric
                    / NULLIF(COUNT(*) FILTER (WHERE vera_aprobada IS NOT NULL), 0) * 100, 1
                )                                                       AS pct_bloqueadas
            FROM historias_usuario hu
            WHERE hu.key NOT IN (
                SELECT DISTINCT test_plan_key FROM historias_usuario
                WHERE test_plan_key IS NOT NULL
            )
            {filtro_fecha_hu}
            {filtro_key}
        """), params).mappings().one()


        vera_serie_filas = sesion.execute(text(f"""
            SELECT hu.key AS key, hu.vera_score AS vera_score, hu.fecha_creacion AS fecha_creacion
            FROM historias_usuario hu
            WHERE hu.key NOT IN (
                SELECT DISTINCT test_plan_key FROM historias_usuario
                WHERE test_plan_key IS NOT NULL
            )
            AND hu.vera_score IS NOT NULL
            {filtro_fecha_hu}
            {filtro_key}
            ORDER BY hu.fecha_creacion ASC
        """), params).mappings().all()


        desenlace_alucinaciones_filas = sesion.execute(text(f"""
            SELECT
                CASE
                    WHEN tc.estado = 'rechazado' THEN 'rechazada'
                    WHEN tc.estado IN ('aprobado','subido_a_xray')
                         AND tc.version_contenido > tc.version_contenido_al_detectar_alucinacion
                        THEN 'editada'
                    WHEN tc.estado IN ('aprobado','subido_a_xray') THEN 'aceptada'
                    ELSE 'pendiente'
                END AS desenlace,
                COUNT(*) AS cantidad
            FROM test_cases tc
            JOIN historias_usuario hu ON hu.key = tc.hu_key
            WHERE hu.key NOT IN (
                SELECT DISTINCT test_plan_key FROM historias_usuario
                WHERE test_plan_key IS NOT NULL
            )
            AND tc.alucinacion_detectada_alguna_vez = true
            {filtro_fecha_tc}
            {filtro_key}
            GROUP BY desenlace
        """), params).mappings().all()


        detalle = sesion.execute(text(f"""
            SELECT
                hu.key,
                hu.titulo,
                hu.fecha_inicio_proceso,
                COUNT(tc.id)                                        AS total_tcs,
                SUM(CASE WHEN tc.estado IN ('aprobado','subido_a_xray')
                         THEN 1 ELSE 0 END)                         AS aprobados,
                SUM(CASE WHEN tc.estado = 'subido_a_xray'
                         THEN 1 ELSE 0 END)                         AS subidos,
                SUM(CASE WHEN tc.alucinacion_detectada = true
                         THEN 1 ELSE 0 END)                         AS con_alucinacion,
                ROUND(AVG(tc.version_contenido), 1)                 AS avg_regen,
                ROUND(
                    EXTRACT(EPOCH FROM (
                        MAX(tc.fecha_actualizacion) - hu.fecha_inicio_proceso
                    )) / 60, 0
                )                                                   AS minutos_revision
            FROM historias_usuario hu
            LEFT JOIN test_cases tc ON tc.hu_key = hu.key
            WHERE hu.key NOT IN (
                SELECT DISTINCT test_plan_key FROM historias_usuario
                WHERE test_plan_key IS NOT NULL
            )
            {filtro_fecha_hu}
            {filtro_key}
            GROUP BY hu.key, hu.titulo, hu.fecha_inicio_proceso
            ORDER BY hu.fecha_inicio_proceso DESC NULLS LAST
        """), params).mappings().all()


    if eficiencia and eficiencia["avg_min_revision_hu"] is not None:
        avg_min_hu = float(eficiencia["avg_min_revision_hu"])
        avg_min_tc = float(eficiencia["avg_min_por_tc"] or 0)
        total_tcs = int(eficiencia["total_tcs"] or 0)
        subidos = int(eficiencia["subidos"] or 0)
        pct_subidos = round(subidos / total_tcs * 100, 1) if total_tcs else 0.0
    else:
        avg_min_hu = None
        avg_min_tc = None
        pct_subidos = 0.0

    tipos_cobertura = {"camino_feliz": 0, "borde": 0, "error": 0}
    for fila in tipos_cobertura_filas:
        if fila["tipo"] in tipos_cobertura:
            tipos_cobertura[fila["tipo"]] = int(fila["cantidad"])

    desenlace_alucinaciones = {"rechazada": 0, "editada": 0, "aceptada": 0, "pendiente": 0}
    for fila in desenlace_alucinaciones_filas:
        if fila["desenlace"] in desenlace_alucinaciones:
            desenlace_alucinaciones[fila["desenlace"]] = int(fila["cantidad"])

    return {
        "volumen": dict(volumen),
        "calidad": dict(calidad),
        "avg_min_hu": avg_min_hu,
        "avg_min_tc": avg_min_tc,
        "pct_subidos": pct_subidos,
        "tipos_cobertura": tipos_cobertura,
        "vera": dict(vera),
        "vera_serie": [dict(r) for r in vera_serie_filas],
        "desenlace_alucinaciones": desenlace_alucinaciones,
        "detalle": [dict(r) for r in detalle],
    }


@st.cache_data(ttl=60, show_spinner=False)
def obtener_keys_hu_periodo(desde: str, hasta: str, key_hu: str | None) -> list[str]:
    """
    Keys de HU de ESTE agente (historias_usuario) en el período -- para la
    pestaña "En vivo" del estado de defectos, que arma un JQL `key in
    (...)` con esto y lo pasa a `ejecutar_seguimiento()` (mismo motor que
    `5_🎯_Seguimiento.py`). Separada de `cargar_datos()` porque esto se
    usa bajo demanda (botón), no en cada carga de la página.
    """
    filtro_fecha_hu = "AND hu.fecha_creacion::date BETWEEN :desde AND :hasta"
    filtro_key = "AND hu.key = :key_hu" if key_hu else ""
    params: dict = {"desde": desde, "hasta": hasta}
    if key_hu:
        params["key_hu"] = key_hu
    with obtener_sesion() as sesion:
        filas = sesion.execute(text(f"""
            SELECT DISTINCT hu.key
            FROM historias_usuario hu
            WHERE hu.key NOT IN (
                SELECT DISTINCT test_plan_key FROM historias_usuario
                WHERE test_plan_key IS NOT NULL
            )
            {filtro_fecha_hu}
            {filtro_key}
        """), params).scalars().all()
    return list(filas)
