"""
🏠 NEXUS Command Center — pantalla de entrada, resumen y navegación.

Fase 2 §2.1. La regla funcional que define esta pantalla es negativa y vale
más que la lista de lo que sí muestra: **Command Center no calcula ni
reemplaza los dashboards analíticos**. Por eso acá NO hay gráficos de
cobertura, ni Pre-Test/Post-Test, ni indicadores completos de QA o de IA, ni
análisis histórico -- todo eso tiene pantalla propia y duplicarlo es la vía
más rápida a que dos pantallas muestren números distintos del mismo dato.

La versión anterior de esta página sí mostraba los resultados del estudio
(cobertura, defectos anticipados, afirmaciones sin respaldo). Se sacaron: son
exactamente "métricas que ya tienen una pantalla propia" y ahora viven en
Evaluación de la tesis > Resumen ejecutivo, que es adonde apunta el acceso.

Sobre el estado de las conexiones: Jira y Xray se validan de verdad contra la
red al iniciar sesión (`frontend/auth.py`), así que acá se reporta ESE
resultado con su hora, en vez de disparar dos llamadas HTTP en cada rerun de
Streamlit -- que es lo que pasaría si se chequeara en vivo, porque Streamlit
reejecuta el script entero ante cualquier interacción. Para el chequeo en
vivo está el botón, explícito y bajo demanda. PostgreSQL sí se chequea en
cada carga: es un `SELECT 1` contra una conexión local, no cuesta nada.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from sqlalchemy import text

from frontend.auth import obtener_credenciales, requerir_sesion
from frontend.comun.estilo import aplicar_estilo_institucional
from infrastructure.db.conexion import obtener_sesion

st.set_page_config(page_title="NEXUS Command Center", page_icon="🏠", layout="wide")
requerir_sesion()


aplicar_estilo_institucional()

st.markdown("""
<style>
.section-header{font-size:12px;font-weight:700;letter-spacing:.08em;
 text-transform:uppercase;color:#4F46E5;margin:24px 0 10px;}
.tarjeta{background:#FFF;border:1px solid #E2E8F0;border-radius:6px;
 padding:14px 16px;height:100%;}
.tarjeta .t{font-size:14px;font-weight:700;color:#0F172A;margin-bottom:2px;}
.tarjeta .d{font-size:11.5px;color:#64748B;line-height:1.45;}
.estado{display:flex;align-items:center;gap:8px;padding:9px 12px;
 border:1px solid #E2E8F0;border-radius:5px;background:#FFF;font-size:12.5px;
 color:#334155;margin-bottom:6px;}
.estado .v{margin-left:auto;font-size:11.5px;color:#64748B;}
.alerta{border-left:3px solid;padding:9px 13px;border-radius:3px;
 font-size:12.5px;margin-bottom:6px;line-height:1.5;}
.alerta.roja{background:#FEF2F2;border-color:#DC2626;color:#7F1D1D;}
.alerta.ambar{background:#FFF7ED;border-color:#F59E0B;color:#7C2D12;}
.vacio{background:#F8FAFC;border:1px dashed #CBD5E1;border-radius:5px;
 padding:16px;text-align:center;color:#64748B;font-size:12.5px;}
</style>
""", unsafe_allow_html=True)

_UMBRAL_PROCESO_COLGADO_H = 6
_UMBRAL_SIN_ACTIVIDAD_D = 14
_LIMITE_RECIENTES = 8


@st.cache_data(ttl=60, show_spinner=False)
def _cargar_estado() -> dict:


    excluir_tp = """
        hu.key NOT IN (
            SELECT DISTINCT test_plan_key FROM historias_usuario
            WHERE test_plan_key IS NOT NULL
        )
    """
    with obtener_sesion() as sesion:
        tot = sesion.execute(text(f"""
            SELECT
                COUNT(DISTINCT hu.key)                                   AS hus,
                COUNT(tc.id)                                             AS casos,
                COUNT(tc.id) FILTER (WHERE tc.estado = 'subido_a_xray')  AS en_xray,
                MAX(GREATEST(hu.fecha_actualizacion, tc.fecha_actualizacion)) AS ultima
            FROM historias_usuario hu
            LEFT JOIN test_cases tc ON tc.hu_key = hu.key
            WHERE {excluir_tp}
        """)).mappings().one()

        recientes = sesion.execute(text(f"""
            SELECT
                hu.key,
                COALESCE(hu.fecha_fin_proceso, hu.fecha_actualizacion) AS fecha,
                hu.vera_score,
                hu.vera_aprobada,
                hu.vera_motivo_bloqueo,
                hu.fecha_inicio_proceso,
                hu.fecha_fin_proceso,
                COUNT(tc.id)                                            AS casos,
                COUNT(tc.id) FILTER (WHERE tc.estado = 'subido_a_xray')  AS en_xray,
                COUNT(tc.id) FILTER (WHERE tc.alucinacion_detectada)     AS alucinaciones
            FROM historias_usuario hu
            LEFT JOIN test_cases tc ON tc.hu_key = hu.key
            WHERE {excluir_tp}
            GROUP BY hu.key, hu.fecha_fin_proceso, hu.fecha_actualizacion,
                     hu.vera_score, hu.vera_aprobada, hu.vera_motivo_bloqueo,
                     hu.fecha_inicio_proceso
            ORDER BY fecha DESC NULLS LAST
            LIMIT :limite
        """), {"limite": _LIMITE_RECIENTES}).mappings().all()


        problemas = sesion.execute(text(f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE hu.vera_aprobada IS FALSE
                )                                                        AS bloqueadas,
                COUNT(*) FILTER (
                    WHERE hu.fecha_inicio_proceso IS NOT NULL
                      AND hu.fecha_fin_proceso IS NULL
                      AND hu.fecha_inicio_proceso < NOW() - (:horas || ' hours')::interval
                )                                                        AS colgadas
            FROM historias_usuario hu
            WHERE {excluir_tp}
        """), {"horas": _UMBRAL_PROCESO_COLGADO_H}).mappings().one()

        con_alucinacion = sesion.execute(text(f"""
            SELECT COUNT(DISTINCT tc.hu_key) AS n
            FROM test_cases tc
            JOIN historias_usuario hu ON hu.key = tc.hu_key
            WHERE tc.alucinacion_detectada AND {excluir_tp}
        """)).mappings().one()

    return {
        "hus": int(tot["hus"] or 0),
        "casos": int(tot["casos"] or 0),
        "en_xray": int(tot["en_xray"] or 0),
        "ultima": tot["ultima"],
        "recientes": [dict(r) for r in recientes],
        "bloqueadas": int(problemas["bloqueadas"] or 0),
        "colgadas": int(problemas["colgadas"] or 0),
        "hu_con_alucinacion": int(con_alucinacion["n"] or 0),
    }


def _estado_postgres() -> tuple[str, str]:
    try:
        with obtener_sesion() as sesion:
            sesion.execute(text("SELECT 1"))
        return "ok", "responde"
    except Exception as exc:
        return "error", str(exc).splitlines()[0][:90]


def _verificar_en_vivo() -> dict:
    """Chequeo real contra Jira y Xray. Solo cuando el usuario lo pide."""
    from frontend.auth import _validar_jira, _validar_xray

    cred = obtener_credenciales() or {}
    salida = {}
    try:
        ok, detalle = _validar_jira(cred.get("jira_base_url", ""),
                                    cred.get("jira_email", ""),
                                    cred.get("jira_api_token", ""))
        salida["jira"] = ("ok" if ok else "error", detalle)
    except Exception as exc:
        salida["jira"] = ("error", str(exc)[:90])
    try:
        ok, detalle = _validar_xray(cred.get("xray_client_id", ""),
                                    cred.get("xray_client_secret", ""))
        salida["xray"] = ("ok" if ok else "error", detalle)
    except Exception as exc:
        salida["xray"] = ("error", str(exc)[:90])
    salida["momento"] = datetime.now(timezone.utc)
    return salida


def _semaforo(estado: str) -> str:
    return {"ok": "🟢 Operativo", "aviso": "🟡 Advertencia"}.get(estado, "🔴 Error")


def _hace(momento) -> str:
    if momento is None:
        return "sin registro"
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - momento
    if delta < timedelta(minutes=1):
        return "hace instantes"
    if delta < timedelta(hours=1):
        return f"hace {int(delta.total_seconds() // 60)} min"
    if delta < timedelta(days=1):
        return f"hace {int(delta.total_seconds() // 3600)} h"
    return f"hace {delta.days} d"


try:
    E = _cargar_estado()
    _bd_estado, _bd_detalle = _estado_postgres()
except Exception as exc:


    st.markdown(
        "<h1 style='color:#0F172A;font-size:23px;font-weight:700;margin-bottom:4px;'>"
        "🏠 NEXUS Command Center</h1>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='alerta roja'><strong>🔴 PostgreSQL no responde.</strong> "
        f"NEXUS no puede leer su propio estado.<br><code>{str(exc)[:220]}</code></div>",
        unsafe_allow_html=True)
    st.page_link("pages/2_⚙️_Configuracion.py", label="Revisar credenciales", icon="🔑")
    st.stop()

st.markdown(
    "<h1 style='color:#0F172A;font-size:23px;font-weight:700;"
    "letter-spacing:.02em;margin-bottom:4px;'>🏠 NEXUS Command Center</h1>"
    "<p style='color:#64748B;font-size:13px;margin-top:0;max-width:760px;'>"
    "Plataforma de diseño de pruebas asistido por IA: Vera evalúa la calidad de "
    "la Historia de Usuario y Gio genera los casos en Gherkin contra los "
    "criterios de aceptación, con revisión humana antes de subirlos a Xray."
    "</p>", unsafe_allow_html=True,
)
st.caption(f"Últimos datos: {_hace(E['ultima'])}"
           + (f" · {E['ultima']:%d/%m/%Y %H:%M} UTC" if E["ultima"] else ""))


st.markdown("<div class='section-header'>Accesos principales</div>",
            unsafe_allow_html=True)

_ACCESOS = [
    ("vista_trabajar_con_ia.py", "✨", "Generar casos",
     "Analizar una HU con Vera y generar sus casos con Gio."),
    ("pages/14_📋_Resumen_Ejecutivo.py", "🧪", "Evaluación de la tesis",
     "Los resultados del estudio Pre-Test / Post-Test."),
    ("pages/10_🔍_Revisar_Cobertura.py", "🤖", "Impacto de la IA",
     "Qué aporta el agente frente al trabajo humano e histórico."),
    ("pages/12_🤖_Indicadores_IA.py", "📊", "Calidad Operativa",
     "Los indicadores que se miran cada semana."),
]
for col, (ruta, icono, titulo, desc) in zip(st.columns(4), _ACCESOS):
    with col:
        st.markdown(
            f"<div class='tarjeta'><div class='t'>{icono} {titulo}</div>"
            f"<div class='d'>{desc}</div></div>", unsafe_allow_html=True)
        try:
            st.page_link(ruta, label="Ir", icon="→")
        except Exception:
            st.caption("(ruta no disponible)")


st.markdown("<div class='section-header'>Estado de la plataforma</div>",
            unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("HUs procesadas", f"{E['hus']:,}".replace(",", "."))
m2.metric("Casos generados", f"{E['casos']:,}".replace(",", "."))
m3.metric("Casos enviados a Xray", f"{E['en_xray']:,}".replace(",", "."))
m3.caption(f"{E['en_xray'] / E['casos'] * 100:.0f}% del total" if E["casos"] else "—")
m4.metric("Última ejecución", _hace(E["ultima"]))

izq, der = st.columns([3, 1])
with der:
    verificar = st.button("🔄 Verificar conexiones", use_container_width=True,
                          help="Chequea Jira y Xray contra la red, ahora mismo.")
if verificar:
    st.session_state["cc_verificacion"] = _verificar_en_vivo()

_viva = st.session_state.get("cc_verificacion")

with izq:
    st.markdown(
        f"<div class='estado'><span>🗄️ <strong>PostgreSQL</strong></span>"
        f"<span>{_semaforo(_bd_estado)}</span>"
        f"<span class='v'>{_bd_detalle}</span></div>", unsafe_allow_html=True)
    for clave, icono, nombre in (("jira", "🧩", "Jira"), ("xray", "🧪", "Xray")):
        if _viva:
            estado, detalle = _viva[clave]
            nota = f"verificado {_hace(_viva['momento'])}"
        else:


            estado, detalle = "ok", "validado al iniciar sesión"
            nota = "usá Verificar para chequear ahora"
        st.markdown(
            f"<div class='estado'><span>{icono} <strong>{nombre}</strong></span>"
            f"<span>{_semaforo(estado)}</span>"
            f"<span class='v'>{detalle} · {nota}</span></div>",
            unsafe_allow_html=True)


st.markdown("<div class='section-header'>Últimas HUs procesadas</div>",
            unsafe_allow_html=True)

if not E["recientes"]:
    st.markdown(
        "<div class='vacio'>Todavía no se procesó ninguna HU. "
        "Empezá en <strong>Generar casos</strong>.</div>", unsafe_allow_html=True)
else:
    def _estado_hu(r: dict) -> str:
        """
        El estado sale del dato, no de un campo que nadie escribe. El orden
        importa: primero lo que impide continuar, después lo que continuó.
        """
        if r["fecha_inicio_proceso"] and not r["fecha_fin_proceso"]:
            return "⏳ En proceso"
        if r["vera_aprobada"] is False:
            return "🔴 Bloqueada por Vera"
        if not r["casos"]:
            return "🟡 Sin casos"
        if r["alucinaciones"]:
            return f"🟡 {r['alucinaciones']} con alucinación"
        if r["en_xray"] == r["casos"]:
            return "🟢 En Xray"
        if r["en_xray"]:
            return f"🟡 {r['en_xray']} de {r['casos']} en Xray"
        return "🔵 Generada"

    cab = st.columns([1.4, 1.1, 1, 1, 1.7, 0.9])
    for col, txt in zip(cab, ("HU", "Fecha", "Score Vera", "Casos", "Estado", "Acción")):
        col.markdown(f"<div style='font-size:11px;font-weight:700;color:#64748B;"
                     f"text-transform:uppercase;letter-spacing:.05em;'>{txt}</div>",
                     unsafe_allow_html=True)
    st.markdown("<hr style='margin:4px 0 8px;border:none;border-top:1px solid #E2E8F0;'>",
                unsafe_allow_html=True)

    for r in E["recientes"]:
        c = st.columns([1.4, 1.1, 1, 1, 1.7, 0.9])
        c[0].markdown(f"**{r['key']}**")
        c[1].write(f"{r['fecha']:%d/%m/%Y}" if r["fecha"] else "—")
        c[2].write(str(r["vera_score"]) if r["vera_score"] is not None else "—")
        c[3].write(str(r["casos"]))
        c[4].write(_estado_hu(r))
        if c[5].button("Ver", key=f"cc_ver_{r['key']}", use_container_width=True):

            st.session_state["hu_precargada"] = r["key"]
            st.switch_page("vista_trabajar_con_ia.py")


alertas: list[tuple[str, str]] = []

if _bd_estado != "ok":
    alertas.append(("roja", f"<strong>PostgreSQL no responde.</strong> {_bd_detalle}"))
if _viva:
    for clave, nombre, pagina in (("jira", "Jira", "Configuración"),
                                  ("xray", "Xray", "Configuración")):
        estado, detalle = _viva[clave]
        if estado != "ok":
            alertas.append(("roja", f"<strong>Conexión con {nombre} fallando.</strong> "
                                    f"{detalle} — revisar credenciales en {pagina}."))
if E["colgadas"]:
    alertas.append(("ambar", f"<strong>{E['colgadas']} HU quedaron en proceso</strong> "
                             f"hace más de {_UMBRAL_PROCESO_COLGADO_H} h sin terminar. "
                             "Probablemente el procesamiento falló a mitad de camino."))
if E["bloqueadas"]:
    alertas.append(("ambar", f"<strong>{E['bloqueadas']} HU bloqueadas por Vera.</strong> "
                             "No alcanzan el umbral de calidad; hay que mejorar la HU "
                             "antes de generar casos."))
if E["hu_con_alucinacion"]:
    alertas.append(("ambar", f"<strong>{E['hu_con_alucinacion']} HU tienen casos con "
                             "alucinación detectada.</strong> Conviene revisarlos antes "
                             "de subirlos a Xray."))
if E["ultima"]:
    _ref = E["ultima"] if E["ultima"].tzinfo else E["ultima"].replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - _ref > timedelta(days=_UMBRAL_SIN_ACTIVIDAD_D):
        alertas.append(("ambar", f"<strong>Sin actividad hace {_hace(E['ultima'])}.</strong> "
                                 "Los indicadores de esta pantalla pueden estar desactualizados."))

if alertas:
    st.markdown("<div class='section-header'>Alertas</div>", unsafe_allow_html=True)
    for tipo, texto in alertas:
        st.markdown(f"<div class='alerta {tipo}'>{texto}</div>", unsafe_allow_html=True)
else:
    st.markdown("<div class='section-header'>Alertas</div>", unsafe_allow_html=True)
    st.markdown("<div class='vacio'>🟢 Sin alertas. Conexiones operativas y "
                "ninguna HU trabada.</div>", unsafe_allow_html=True)
