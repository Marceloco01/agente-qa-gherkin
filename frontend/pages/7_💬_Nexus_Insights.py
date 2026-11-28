"""
Nexus Insights — chat real sobre todo el universo analítico de NEXUS.

NEXUS Fase 3. Decisión de diseño (2026-09-02):
- Alcance: "todo el universo analítico de NEXUS, incluyendo calidad +
  pruebas + defectos + Vera + Gio + IA vs tradicional + adopción +
  histórico + tendencias." Es decir, TODO el sistema. La primera versión
  (misma noche) no tenía selector de período -- el contexto era siempre el
  histórico completo. El usuario probó el chat con datos reales, y al
  preguntar por una tendencia le pidió acotarla a un rango ("quiero el
  rango de junio 2026 para delante solamente"): se agregó un selector de
  período en el sidebar, MISMO patrón (Todo el período / Mes específico /
  Rango personalizado) que `1_📊_Dashboard.py`/`5_🎯_Seguimiento.py`, para
  que el usuario pueda acotar TODO el contexto (calidad, Gio, Vera,
  desenlace, pruebas/tendencias/defectos) a un rango -- salvo el corpus
  cerrado del análisis retrospectivo (IA vs. tradicional, 43 HU fijas de la tesis, no
  tiene fecha por HU y no depende del período) y el corte fijo de Adopción
  IA (que se INTERSECTA con el período elegido, nunca se corre hacia
  atrás del corte real).
- "Nora puede desaparecer como agente independiente y convertirse en una
  capacidad de interpretación dentro de Nexus Insights": el botón "Analizar
  con Nora" de `1_📊_Dashboard.py` se retiró (ver el comentario que quedó
  ahí) -- esta página es ahora la única superficie de interpretación con IA
  del sistema. `application/interpretar_dashboard.py` y
  `LLMProvider.interpretar_dashboard()` NO se borraron (documentación
  histórica de la Fase 1 de esta capacidad), pero ya no se llaman desde
  ningún lado.
- Ubicación: "Nueva página propia" -- no una sección más de Dashboard.
- UX (capturada al analizar la viabilidad de NEXUS, ver
  documentación de diseño, Fase 1): las respuestas se presentan como un
  pipeline de mensajes secuenciales (pasos "info"/"hallazgo"/"resumen"), no
  un bloque de texto plano, y el chat marca explícitamente cuando encuentra
  algo digno de atención.

A diferencia de Nora (una sola pasada por período, sin memoria), esto es un
chat real con preguntas de seguimiento -- ver
`ports/llm_provider.py::LLMProvider.chat_nexus_insights()` para el contrato
completo, incluida la estrategia de control de costo (contexto cacheado 60s,
recalculado solo al pedirlo explícitamente; historial truncado a los últimos
turnos, y los turnos de Nexus Insights se compactan a su paso "resumen").

Convención de UI de chat reusada de `frontend/streamlit_app.py` (chat QA<->
Agente): `st.text_input` + `st.button`, NO `st.chat_input`/`st.chat_message`
(no se usan en ningún otro lado del proyecto, así que no se introducen acá
para mantener un solo estilo de chat en toda la app).
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import text

from application.chat_nexus_insights import ChatNexusInsights
from frontend.auth import requerir_sesion
from frontend.comun.estilo import aplicar_estilo_institucional
from infrastructure.db.conexion import obtener_sesion
from infrastructure.db.seguimiento_metricas import listar_metricas
from infrastructure.fabrica_llm import crear_llm_provider

st.set_page_config(
    page_title="Nexus Insights — Agente QA",
    page_icon="💬",
    layout="wide",
)
requerir_sesion()


aplicar_estilo_institucional()


st.markdown("""
<style>
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
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #64748B;
}
.empty-state .icon { font-size: 32px; margin-bottom: 12px; }
.empty-state p { font-size: 14px; margin: 0; }

/* Turno del usuario */
.ni-turno-usuario {
    background: #EEF2FF;
    border-radius: 8px;
    padding: 10px 16px;
    margin: 10px 0 14px 0;
    font-size: 13px;
    color: #0F172A;
}

/* Pasos del pipeline de Nexus Insights */
.ni-paso {
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 8px;
    font-size: 13px;
    line-height: 1.55;
}
.ni-paso-info {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 3px solid #64748B;
    color: #0F172A;
}
.ni-paso-hallazgo {
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    border-left: 3px solid #D97706;
    color: #7C4A03;
}
.ni-paso-resumen {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 3px solid #4F46E5;
    color: #0F172A;
    font-weight: 500;
}
.ni-paso-etiqueta {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 4px;
    display: block;
}
.ni-paso-info .ni-paso-etiqueta { color: #64748B; }
.ni-paso-hallazgo .ni-paso-etiqueta { color: #D97706; }
.ni-paso-resumen .ni-paso-etiqueta { color: #4F46E5; }
</style>
""", unsafe_allow_html=True)


with st.sidebar:
    st.markdown("### 🔍 Filtros")
    st.markdown("---")

    _hoy_ni = datetime.now(timezone.utc).date()
    _hace_30_ni = _hoy_ni - timedelta(days=30)

    _vista_periodo_ni = st.radio(
        "Período",
        ["Todo el período", "Mes específico", "Rango personalizado"],
        key="ni_vista_periodo",
    )

    if _vista_periodo_ni == "Todo el período":
        fecha_desde = date(2000, 1, 1)
        fecha_hasta = _hoy_ni
        periodo_label = "todo el histórico"
    elif _vista_periodo_ni == "Mes específico":
        _mes_elegido_ni = st.date_input(
            "Mes", value=_hoy_ni.replace(day=1), max_value=_hoy_ni, key="ni_mes_elegido",
        )
        fecha_desde = _mes_elegido_ni.replace(day=1)
        _siguiente_mes_ni = (
            fecha_desde.replace(year=fecha_desde.year + 1, month=1)
            if fecha_desde.month == 12
            else fecha_desde.replace(month=fecha_desde.month + 1)
        )
        fecha_hasta = min(_siguiente_mes_ni - timedelta(days=1), _hoy_ni)
        periodo_label = f"{fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')}"
    else:
        fecha_desde = st.date_input("Desde", value=_hace_30_ni, max_value=_hoy_ni, key="ni_desde")
        fecha_hasta = st.date_input("Hasta", value=_hoy_ni, max_value=_hoy_ni, key="ni_hasta")
        periodo_label = f"{fecha_desde.strftime('%d/%m/%Y')} → {fecha_hasta.strftime('%d/%m/%Y')}"

    if fecha_desde > fecha_hasta:
        st.error("'Desde' no puede ser mayor que 'Hasta'.")
        st.stop()

    st.markdown("---")
    st.markdown(
        "<span style='font-size:11px;color:#64748B;'>"
        "El corpus cerrado del análisis retrospectivo (IA vs. tradicional) y el corte de "
        "Adopción IA no se acotan hacia atrás de este filtro -- ver el "
        "detalle en cada respuesta.</span>",
        unsafe_allow_html=True,
    )


FECHA_CORTE_ADOPCION_IA = date(2026, 9, 2)


_ARCHIVO_RETRO = Path(__file__).resolve().parent.parent.parent / "retro" / "retro_resultado_57hu.csv"


_MAX_TURNOS_HISTORIAL = 6


_GAP_MAXIMO_DIAS = 45
_TAMANO_COHORTE_TENDENCIA = 10
_UMBRAL_ESTABLE = 2.0


_RE_SEVERIDAD = re.compile(r"(Menor|Mediano|Mayor|Grave):\s*(\d+)/(\d+)")


def _agregar_defectos_por_severidad(textos: list[str]) -> dict[str, dict[str, int]]:
    """Suma resueltos/detectados por nivel a partir de varios textos compactos."""
    acumulado = {nivel: {"resueltos": 0, "detectados": 0} for nivel in ("Grave", "Mayor", "Mediano", "Menor")}
    for texto in textos:
        if not texto:
            continue
        for nivel, resueltos, detectados in _RE_SEVERIDAD.findall(texto):
            acumulado[nivel]["resueltos"] += int(resueltos)
            acumulado[nivel]["detectados"] += int(detectados)
    return acumulado


def _calcular_tendencia(pares: list[tuple[datetime | None, float | None]]) -> str | None:
    """
    Etiqueta de tendencia (Mejorando/Empeorando/Estable) sobre una serie
    cronológica de (fecha, valor): cohortes de tamaño fijo cortadas antes de
    tiempo si hay un salto de más de `_GAP_MAXIMO_DIAS` entre dos mediciones
    consecutivas, regresión lineal simple por posición de cohorte -- mismo
    método y mismos umbrales que
    `1_📊_Dashboard.py::_render_evolucion_scores_vera`.

    Devuelve None si no hay datos suficientes (menos de 2 cohortes con
    promedio) -- el caller decide cómo mostrar eso ("sin datos
    suficientes").
    """
    pares_validos = sorted(
        ((f, v) for f, v in pares if v is not None and f is not None),
        key=lambda p: p[0],
    )
    if len(pares_validos) < 2:
        return None

    cohortes: list[list[float]] = []
    actual: list[float] = []
    fecha_anterior = None
    for fecha, valor in pares_validos:
        hay_salto = fecha_anterior is not None and (fecha - fecha_anterior).days > _GAP_MAXIMO_DIAS
        if actual and (len(actual) >= _TAMANO_COHORTE_TENDENCIA or hay_salto):
            cohortes.append(actual)
            actual = []
        actual.append(valor)
        fecha_anterior = fecha
    if actual:
        cohortes.append(actual)

    promedios = [sum(c) / len(c) for c in cohortes]
    if len(promedios) < 2:
        return None

    k = len(promedios)
    puntos = list(enumerate(promedios))
    sum_x = sum(p[0] for p in puntos)
    sum_y = sum(p[1] for p in puntos)
    sum_xy = sum(p[0] * p[1] for p in puntos)
    sum_x2 = sum(p[0] ** 2 for p in puntos)
    denominador = k * sum_x2 - sum_x ** 2
    if denominador == 0:
        return None

    pendiente = (k * sum_xy - sum_x * sum_y) / denominador
    intercepto = (sum_y - pendiente * sum_x) / k
    valor_inicio = intercepto
    valor_fin = pendiente * (k - 1) + intercepto
    delta = valor_fin - valor_inicio

    if delta > _UMBRAL_ESTABLE:
        return f"↗ Mejorando ({delta:+.1f} pts, primera → última cohorte de {k})"
    if delta < -_UMBRAL_ESTABLE:
        return f"↘ Empeorando ({delta:+.1f} pts, primera → última cohorte de {k})"
    return f"→ Estable ({delta:+.1f} pts, primera → última cohorte de {k})"


@st.cache_data(ttl=60, show_spinner=False)
def _cargar_contexto_nexus_insights(desde: str, hasta: str, periodo_label: str) -> dict:
    """
    Arma el dict de contexto completo que consume
    `LLMProvider.chat_nexus_insights()` (vía
    `adapters/llm/ollama_provider.py::_formatear_contexto_nexus_insights`,
    que define la forma EXACTA de cada bloque -- este dict tiene que
    calzar con lo que esa función lee).

    Cacheado 60s por combinación de (desde, hasta), NO recalculado en cada
    mensaje del chat (ver el control de costo documentado en
    `LLMProvider.chat_nexus_insights()`) -- el botón "Actualizar datos" de
    la página fuerza un recálculo antes de tiempo.

    Selector de período agregado (2026-09-02, mismo
    día que se probó el chat con datos reales) -- ver el sidebar de la
    página para el selector de 3 opciones (mismo patrón que Dashboard/
    Seguimiento). `desde`/`hasta` acotan calidad, Gio, Vera, desenlace de
    alucinaciones, y el histórico de `seguimiento_hu_metricas` (pruebas/
    tendencias/defectos). DOS excepciones deliberadas, documentadas en cada
    bloque más abajo: el corpus del análisis retrospectivo (IA vs. tradicional) es un
    corpus CERRADO de 43 HU de la tesis sin fecha por HU, así que no se
    acota por período; y Adopción IA usa la INTERSECCIÓN de
    `FECHA_CORTE_ADOPCION_IA` con el período elegido (nunca se corre hacia
    atrás del corte real, aunque el usuario pida un rango anterior).

    Args:
        desde, hasta: fechas ISO (`str(date)`) del período elegido en el
            sidebar -- strings, no `date`, porque son las que se bindean
            directo como parámetro SQL (mismo patrón que
            `1_📊_Dashboard.py::_cargar_datos()`).
        periodo_label: texto ya formateado para mostrarle al LLM y al
            usuario (ej. "01/06/2026 → 02/09/2026" o "todo el histórico") --
            se calcula una sola vez en el sidebar y se pasa acá en vez de
            recalcularlo, así queda parte de la cache key.
    """
    excluir_test_plans = """
        hu.key NOT IN (
            SELECT DISTINCT test_plan_key FROM historias_usuario
            WHERE test_plan_key IS NOT NULL
        )
    """
    filtro_fecha_hu = "AND hu.fecha_creacion::date BETWEEN :desde AND :hasta"
    filtro_fecha_tc = "AND tc.fecha_creacion::date BETWEEN :desde AND :hasta"
    params_periodo = {"desde": desde, "hasta": hasta}

    with obtener_sesion() as sesion:


        volumen = sesion.execute(text(f"""
            SELECT
                COUNT(DISTINCT hu.key)                          AS total_hus,
                COUNT(tc.id)                                    AS total_tcs
            FROM historias_usuario hu
            LEFT JOIN test_cases tc ON tc.hu_key = hu.key
            WHERE {excluir_test_plans}
            {filtro_fecha_hu}
        """), params_periodo).mappings().one()

        calidad_sql = sesion.execute(text(f"""
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
            WHERE {excluir_test_plans}
            {filtro_fecha_tc}
        """), params_periodo).mappings().one()

        eficiencia = sesion.execute(text(f"""
            SELECT
                ROUND(AVG(max_actualizacion_hu - inicio_proceso), 1) AS avg_min_revision_hu,
                ROUND(AVG(avg_min_tc), 1)                            AS avg_min_por_tc
            FROM (
                SELECT
                    EXTRACT(EPOCH FROM (
                        MAX(tc.fecha_actualizacion) - hu.fecha_inicio_proceso
                    )) / 60                                         AS max_actualizacion_hu,
                    EXTRACT(EPOCH FROM hu.fecha_inicio_proceso) / 60 AS inicio_proceso,
                    ROUND(AVG(
                        EXTRACT(EPOCH FROM (
                            tc.fecha_actualizacion - tc.fecha_creacion
                        )) / 60
                    ), 1)                                           AS avg_min_tc
                FROM test_cases tc
                JOIN historias_usuario hu ON hu.key = tc.hu_key
                WHERE {excluir_test_plans}
                AND hu.fecha_inicio_proceso IS NOT NULL
                {filtro_fecha_tc}
                GROUP BY hu.key, hu.fecha_inicio_proceso
            ) sub
        """), params_periodo).mappings().one()


        tipos_cobertura_filas = sesion.execute(text(f"""
            SELECT tc.tipo_cobertura AS tipo, COUNT(*) AS cantidad
            FROM test_cases tc
            JOIN historias_usuario hu ON hu.key = tc.hu_key
            WHERE {excluir_test_plans}
            AND tc.tipo_cobertura IS NOT NULL
            {filtro_fecha_tc}
            GROUP BY tc.tipo_cobertura
        """), params_periodo).mappings().all()


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
            WHERE {excluir_test_plans}
            {filtro_fecha_hu}
        """), params_periodo).mappings().one()


        desenlace_filas = sesion.execute(text(f"""
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
            WHERE {excluir_test_plans}
            AND tc.alucinacion_detectada_alguna_vez = true
            {filtro_fecha_tc}
            GROUP BY desenlace
        """), params_periodo).mappings().all()


        _fecha_desde_dt = date.fromisoformat(desde)
        _fecha_hasta_dt = date.fromisoformat(hasta)
        _fecha_desde_adopcion = max(_fecha_desde_dt, FECHA_CORTE_ADOPCION_IA)
        _fecha_hasta_adopcion = max(_fecha_hasta_dt, _fecha_desde_adopcion)
        params_adopcion = {"desde": str(_fecha_desde_adopcion), "hasta": str(_fecha_hasta_adopcion)}

        adopcion_volumen = sesion.execute(text(f"""
            SELECT
                COUNT(DISTINCT hu.key) AS total_hus,
                COUNT(tc.id)           AS total_tcs
            FROM historias_usuario hu
            LEFT JOIN test_cases tc ON tc.hu_key = hu.key
            WHERE {excluir_test_plans}
            AND hu.fecha_creacion::date BETWEEN :desde AND :hasta
        """), params_adopcion).mappings().one()

        adopcion_calidad = sesion.execute(text(f"""
            SELECT
                ROUND(
                    SUM(CASE WHEN estado = 'aprobado'
                              OR estado = 'subido_a_xray' THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*), 0) * 100, 1
                )                                                   AS pct_aprobados,
                ROUND(
                    SUM(CASE WHEN alucinacion_detectada = true THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*), 0) * 100, 1
                )                                                   AS pct_alucinacion
            FROM test_cases tc
            JOIN historias_usuario hu ON hu.key = tc.hu_key
            WHERE {excluir_test_plans}
            AND tc.fecha_creacion::date BETWEEN :desde AND :hasta
        """), params_adopcion).mappings().one()

    tipos_cobertura = {"camino_feliz": 0, "borde": 0, "error": 0}
    for fila in tipos_cobertura_filas:
        if fila["tipo"] in tipos_cobertura:
            tipos_cobertura[fila["tipo"]] = int(fila["cantidad"])

    desenlace_alucinaciones = {"rechazada": 0, "editada": 0, "aceptada": 0, "pendiente": 0}
    for fila in desenlace_filas:
        if fila["desenlace"] in desenlace_alucinaciones:
            desenlace_alucinaciones[fila["desenlace"]] = int(fila["cantidad"])

    calidad = {
        "total_hus": int(volumen["total_hus"] or 0),
        "total_tcs": int(volumen["total_tcs"] or 0),
        "total_evaluados": int(calidad_sql["total"] or 0),
        "aprobados": int(calidad_sql["aprobados"] or 0),
        "rechazados": int(calidad_sql["rechazados"] or 0),
        "con_alucinacion": int(calidad_sql["con_alucinacion"] or 0),
        "pct_aprobados": float(calidad_sql["pct_aprobados"]) if calidad_sql["pct_aprobados"] is not None else None,
        "pct_alucinacion": float(calidad_sql["pct_alucinacion"]) if calidad_sql["pct_alucinacion"] is not None else None,
        "avg_regeneraciones": float(calidad_sql["avg_regeneraciones"]) if calidad_sql["avg_regeneraciones"] is not None else None,
        "avg_min_hu": float(eficiencia["avg_min_revision_hu"]) if eficiencia["avg_min_revision_hu"] is not None else None,
        "avg_min_tc": float(eficiencia["avg_min_por_tc"]) if eficiencia["avg_min_por_tc"] is not None else None,
    }


    snapshots = listar_metricas(desde=_fecha_desde_dt, hasta=_fecha_hasta_dt)

    def _promedio(valores: list[float]) -> float | None:
        return round(sum(valores) / len(valores), 1) if valores else None

    valores_ejecucion = [s.indice_ejecucion_pct for s in snapshots if s.indice_ejecucion_pct is not None]
    valores_pass_rate = [s.test_pass_rate_pct for s in snapshots if s.test_pass_rate_pct is not None]
    valores_densidad = [s.indice_cobertura_densidad_pct for s in snapshots if s.indice_cobertura_densidad_pct is not None]
    valores_cobertura_real = [s.indice_cobertura_real_pct for s in snapshots if s.indice_cobertura_real_pct is not None]

    pruebas = {
        "n": len(snapshots),
        "avg_indice_ejecucion": _promedio(valores_ejecucion),
        "avg_pass_rate": _promedio(valores_pass_rate),
        "avg_densidad_cobertura": _promedio(valores_densidad),
        "avg_cobertura_real": _promedio(valores_cobertura_real),
        "n_cobertura_real": len(valores_cobertura_real),
    }

    tendencias = {
        "ejecucion": _calcular_tendencia(
            [(s.fecha_certificacion_terminada, s.indice_ejecucion_pct) for s in snapshots]
        ),
        "pass_rate": _calcular_tendencia(
            [(s.fecha_certificacion_terminada, s.test_pass_rate_pct) for s in snapshots]
        ),
    }

    textos_severidad = [s.defectos_por_severidad for s in snapshots if s.defectos_por_severidad]
    defectos = _agregar_defectos_por_severidad(textos_severidad)


    ia_vs_tradicional: dict = {}
    if _ARCHIVO_RETRO.exists():
        df_retro = pd.read_csv(_ARCHIVO_RETRO)
        total_retro = len(df_retro)
        if total_retro:
            n_superior = int((df_retro["veredicto"] == "SUPERIOR").sum())
            n_equivalente = int((df_retro["veredicto"] == "EQUIVALENTE").sum())
            n_inferior = int((df_retro["veredicto"] == "INFERIOR").sum())
            avg_indice_ejecucion = None
            if "indice_ejecucion_pct" in df_retro.columns and df_retro["indice_ejecucion_pct"].notna().any():
                avg_indice_ejecucion = round(float(df_retro["indice_ejecucion_pct"].dropna().mean()), 1)
            ia_vs_tradicional = {
                "superior": n_superior,
                "pct_superior": round(n_superior / total_retro * 100, 1),
                "equivalente": n_equivalente,
                "pct_equivalente": round(n_equivalente / total_retro * 100, 1),
                "inferior": n_inferior,
                "pct_inferior": round(n_inferior / total_retro * 100, 1),
                "avg_indice_ejecucion": avg_indice_ejecucion,
            }

    adopcion = {
        "fecha_corte": FECHA_CORTE_ADOPCION_IA.strftime("%d/%m/%Y"),
        "periodo_efectivo": f"{_fecha_desde_adopcion.strftime('%d/%m/%Y')} → {_fecha_hasta_adopcion.strftime('%d/%m/%Y')}",
        "total_hus": int(adopcion_volumen["total_hus"] or 0),
        "total_tcs": int(adopcion_volumen["total_tcs"] or 0),
        "pct_aprobados": float(adopcion_calidad["pct_aprobados"]) if adopcion_calidad["pct_aprobados"] is not None else None,
        "pct_alucinacion": float(adopcion_calidad["pct_alucinacion"]) if adopcion_calidad["pct_alucinacion"] is not None else None,
    }

    return {
        "periodo_label": periodo_label,
        "calidad": calidad,
        "gio": tipos_cobertura,
        "vera": dict(vera),
        "desenlace_alucinaciones": desenlace_alucinaciones,
        "pruebas": pruebas,
        "tendencias": tendencias,
        "defectos": defectos,
        "ia_vs_tradicional": ia_vs_tradicional,
        "adopcion": adopcion,
    }


st.markdown(
    "<span style='display:inline-block;font-size:10px;font-weight:700;"
    "letter-spacing:0.08em;text-transform:uppercase;color:#4F46E5;"
    "background:#E0E7FF;padding:3px 10px;border-radius:3px;margin-bottom:8px;'>"
    "💬 Nexus Insights</span><br>",
    unsafe_allow_html=True,
)
st.markdown(
    "<h1 style='color:#0F172A;font-size:22px;font-weight:700;"
    "letter-spacing:0.02em;margin-bottom:4px;'>💬 Nexus Insights</h1>"
    f"<p style='color:#64748B;font-size:13px;margin-top:0;'>"
    f"Chat con IA sobre todo el universo analítico de NEXUS: calidad, pruebas, "
    f"defectos, Vera, Gio, IA vs. proceso tradicional, adopción, histórico y "
    f"tendencias · Período: <b>{periodo_label}</b></p>",
    unsafe_allow_html=True,
)

if "nexus_insights_conversacion" not in st.session_state:
    st.session_state.nexus_insights_conversacion = []


_periodo_fingerprint = (str(fecha_desde), str(fecha_hasta))
if st.session_state.get("nexus_insights_periodo_fingerprint") != _periodo_fingerprint:
    st.session_state.nexus_insights_periodo_fingerprint = _periodo_fingerprint
    st.session_state.nexus_insights_conversacion = []

col_refrescar, col_limpiar, col_spacer = st.columns([1, 1, 3])
with col_refrescar:
    if st.button("🔄 Actualizar datos", key="ni_actualizar_datos"):
        _cargar_contexto_nexus_insights.clear()
        st.rerun()
with col_limpiar:
    if st.button("🧹 Limpiar conversación", key="ni_limpiar_conversacion"):
        st.session_state.nexus_insights_conversacion = []
        st.rerun()

contexto = _cargar_contexto_nexus_insights(str(fecha_desde), str(fecha_hasta), periodo_label)

if not contexto["calidad"]["total_hus"]:
    st.markdown(
        "<div class='empty-state'><div class='icon'>📭</div>"
        "<p>Todavía no hay datos en el sistema para que Nexus Insights analice.<br>"
        "Generá test cases desde la página de Inicio para empezar a acumular histórico.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

st.markdown("<div class='section-header'>Conversación</div>", unsafe_allow_html=True)

if not st.session_state.nexus_insights_conversacion:
    st.markdown(
        "<div class='empty-state'><div class='icon'>💬</div>"
        "<p>Preguntale algo a Nexus Insights sobre el sistema -- por ejemplo, "
        "\"¿cómo viene la tasa de aprobación últimamente?\" o "
        "\"¿qué tan seguido se editan los test cases con alucinación antes de aprobarlos?\".</p>"
        "</div>",
        unsafe_allow_html=True,
    )

_ETIQUETAS_PASO = {"info": "Info", "hallazgo": "⚠ Hallazgo", "resumen": "Resumen"}

for turno in st.session_state.nexus_insights_conversacion:
    if turno["rol"] == "usuario":
        st.markdown(
            f"<div class='ni-turno-usuario'>🧑 <b>Tú:</b> {turno['texto']}</div>",
            unsafe_allow_html=True,
        )
    else:
        for paso in turno["pasos"]:
            tipo = paso.get("tipo", "info")
            clase = f"ni-paso-{tipo}" if tipo in ("info", "hallazgo", "resumen") else "ni-paso-info"
            etiqueta = _ETIQUETAS_PASO.get(tipo, "Info")
            st.markdown(
                f"<div class='ni-paso {clase}'>"
                f"<span class='ni-paso-etiqueta'>🤖 Nexus Insights · {etiqueta}</span>"
                f"{paso.get('texto', '')}"
                "</div>",
                unsafe_allow_html=True,
            )

st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)

_version_input = len(st.session_state.nexus_insights_conversacion)
pregunta = st.text_input(
    "Preguntale a Nexus Insights",
    key=f"ni_pregunta_{_version_input}",
    placeholder="Ej: ¿la cobertura de pruebas viene mejorando o empeorando?",
)

if st.button("Preguntar", key="ni_boton_preguntar", disabled=not pregunta.strip()):
    try:
        llm_provider = crear_llm_provider()
    except ValueError as exc:
        st.error(str(exc))
    else:


        historial_llm = []
        for turno in st.session_state.nexus_insights_conversacion[-_MAX_TURNOS_HISTORIAL:]:
            if turno["rol"] == "usuario":
                historial_llm.append({"rol": "usuario", "texto": turno["texto"]})
            else:
                _resumen = next(
                    (p["texto"] for p in reversed(turno["pasos"]) if p.get("tipo") == "resumen"),
                    turno["pasos"][-1]["texto"] if turno["pasos"] else "",
                )
                historial_llm.append({"rol": "nexus", "texto": _resumen})

        pregunta_enviada = pregunta.strip()
        with st.spinner("Nexus Insights está pensando..."):
            try:
                pasos = ChatNexusInsights(llm_provider).ejecutar(contexto, historial_llm, pregunta_enviada)
            except Exception as exc:
                st.error(f"Nexus Insights no pudo responder: {exc}")
                pasos = None

        if pasos is not None:
            st.session_state.nexus_insights_conversacion.append({"rol": "usuario", "texto": pregunta_enviada})
            st.session_state.nexus_insights_conversacion.append({
                "rol": "nexus",
                "pasos": [{"tipo": p.tipo, "texto": p.texto} for p in pasos],
            })
            st.rerun()

st.markdown(
    f"<p style='font-size:11px;color:#64748B;margin-top:20px;'>"
    f"Contexto agregado de <b>{periodo_label}</b>, actualizado cada 60 s "
    f"(o al tocar \"Actualizar datos\"). Nexus Insights no ve HU ni test cases "
    f"individuales -- solo estos resúmenes agregados. El corpus del análisis retrospectivo "
    f"(IA vs. tradicional) es un corpus cerrado de la tesis y no cambia con "
    f"el período elegido.</p>",
    unsafe_allow_html=True,
)
