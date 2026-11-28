"""
Configuración — Fase 5 (placeholder).

Pantalla de gestión de credenciales y configuración del agente.
Por ahora solo muestra la estructura visual — la funcionalidad real
(leer/escribir credenciales) se implementa en una fase posterior.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from dotenv import set_key

from frontend.auth import (
    actualizar_credenciales_sesion,
    obtener_credenciales,
    requerir_sesion,
    validar_jira,
    validar_xray,
)
from frontend.comun.estilo import aplicar_estilo_institucional

st.set_page_config(
    page_title="Configuración — Agente QA",
    page_icon="⚙️",
    layout="wide",
)
requerir_sesion()


aplicar_estilo_institucional()


_ARCHIVO_ENV = Path(__file__).resolve().parent.parent.parent / ".env"

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
[data-testid="stSidebar"] * { color: #0F172A !important; }

.config-section {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 24px 28px;
    margin-bottom: 16px;
}
.config-section-title {
    font-size: 13px;
    font-weight: 600;
    color: #0F172A;
    margin-bottom: 4px;
}
.config-section-desc {
    font-size: 12px;
    color: #64748B;
    margin-bottom: 20px;
}
.credential-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid #E2E8F0;
}
.credential-row:last-child { border-bottom: none; }
.credential-label {
    font-size: 13px;
    color: #0F172A;
    font-weight: 500;
}
.credential-hint {
    font-size: 11px;
    color: #64748B;
    margin-top: 2px;
}
.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 6px;
}
.dot-ok   { background: #16A34A; }
.dot-warn { background: #D97706; }
.dot-off  { background: #94A3B8; }
.coming-soon {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748B;
    background: #E2E8F0;
    padding: 2px 8px;
    border-radius: 3px;
}
</style>
""", unsafe_allow_html=True)

st.markdown(
    "<h1 style='color:#0F172A;font-size:22px;font-weight:700;"
    "letter-spacing:0.02em;margin-bottom:4px;'>⚙️ Configuración</h1>"
    "<p style='color:#64748B;font-size:13px;margin-top:0;'>"
    "Credenciales y parámetros del agente QA</p>",
    unsafe_allow_html=True,
)

_creds = obtener_credenciales()


def _enmascarar(valor: str, mostrar: int = 4) -> str:
    if len(valor) <= mostrar:
        return "•" * len(valor)
    return "•" * (len(valor) - mostrar) + valor[-mostrar:]


st.success(
    f"🔓 Sesión activa, conectada a Jira como **{st.session_state.auth_jira_nombre}**. "
    "Estas credenciales se validaron de verdad contra ambas APIs al ingresar "
    "(no solo 'no vacío') y viven únicamente en esta sesión del navegador -- "
    "no se escriben a ningún archivo.",
    icon="✅",
)


st.markdown(f"""
<div class="config-section">
    <div class="config-section-title">Jira Cloud</div>
    <div class="config-section-desc">
        Conexión a la instancia de Atlassian para traer Historias de Usuario
        y crear issue links hacia Test Plans.
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">URL de la instancia</div>
            <div class="credential-hint">desde JIRA_BASE_URL en .env -- no es un secreto de sesión</div>
        </div>
        <span><span class="status-dot dot-ok"></span>{_creds['jira_base_url']}</span>
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">Email de la cuenta</div>
            <div class="credential-hint">ingresado en el login de esta sesión</div>
        </div>
        <span><span class="status-dot dot-ok"></span>{_creds['jira_email']}</span>
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">API Token</div>
            <div class="credential-hint">validado con GET /rest/api/3/myself al ingresar</div>
        </div>
        <span><span class="status-dot dot-ok"></span>{_enmascarar(_creds['jira_api_token'])}</span>
    </div>
</div>
""", unsafe_allow_html=True)

with st.expander("Actualizar credenciales de Jira"):
    st.caption(
        "Al guardar se valida de verdad contra `GET /rest/api/3/myself` -- si "
        "Jira lo rechaza, no se guarda nada. Si pasa, se reescribe en tu "
        "`.env` (JIRA_EMAIL / JIRA_API_TOKEN) y esta sesión pasa a usar el "
        "valor nuevo."
    )
    with st.form("form_editar_jira"):
        nuevo_email = st.text_input("Email", value=_creds["jira_email"])
        nuevo_token = st.text_input(
            "API Token", type="password", placeholder="dejar vacío para no cambiarlo",
        )
        guardar_jira = st.form_submit_button("Guardar y validar Jira", type="primary")

    if guardar_jira:
        email_a_validar = nuevo_email.strip() or _creds["jira_email"]
        token_a_validar = nuevo_token.strip() or _creds["jira_api_token"]
        if email_a_validar == _creds["jira_email"] and token_a_validar == _creds["jira_api_token"]:
            st.info("No hay cambios respecto a lo que ya tenías cargado.")
        else:
            with st.spinner("Validando contra Jira..."):
                ok, resultado = validar_jira(_creds["jira_base_url"], email_a_validar, token_a_validar)
            if not ok:
                st.error(f"Jira: {resultado}")
            else:
                set_key(str(_ARCHIVO_ENV), "JIRA_EMAIL", email_a_validar)
                set_key(str(_ARCHIVO_ENV), "JIRA_API_TOKEN", token_a_validar)
                actualizar_credenciales_sesion(
                    {"jira_email": email_a_validar, "jira_api_token": token_a_validar},
                    jira_nombre=resultado,
                )
                st.success(f"Jira actualizado -- conectado como {resultado}.")
                st.rerun()


st.markdown(f"""
<div class="config-section">
    <div class="config-section-title">Xray Cloud</div>
    <div class="config-section-desc">
        Autenticación separada de Jira (Client ID + Client Secret).
        Token con vigencia de 24 h, renovado automáticamente por el agente.
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">Client ID</div>
            <div class="credential-hint">ingresado en el login de esta sesión</div>
        </div>
        <span><span class="status-dot dot-ok"></span>{_enmascarar(_creds['xray_client_id'])}</span>
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">Client Secret</div>
            <div class="credential-hint">validado con /authenticate al ingresar</div>
        </div>
        <span><span class="status-dot dot-ok"></span>{_enmascarar(_creds['xray_client_secret'])}</span>
    </div>
</div>
""", unsafe_allow_html=True)

with st.expander("Actualizar credenciales de Xray"):
    st.caption(
        "Al guardar se valida de verdad contra el endpoint `/authenticate` de "
        "Xray Cloud -- si lo rechaza, no se guarda nada. Si pasa, se reescribe "
        "en tu `.env` (XRAY_CLIENT_ID / XRAY_CLIENT_SECRET) y esta sesión pasa "
        "a usar el valor nuevo."
    )
    with st.form("form_editar_xray"):
        nuevo_client_id = st.text_input(
            "Client ID", type="password", placeholder="dejar vacío para no cambiarlo",
        )
        nuevo_client_secret = st.text_input(
            "Client Secret", type="password", placeholder="dejar vacío para no cambiarlo",
        )
        guardar_xray = st.form_submit_button("Guardar y validar Xray", type="primary")

    if guardar_xray:
        client_id_a_validar = nuevo_client_id.strip() or _creds["xray_client_id"]
        client_secret_a_validar = nuevo_client_secret.strip() or _creds["xray_client_secret"]
        if (
            client_id_a_validar == _creds["xray_client_id"]
            and client_secret_a_validar == _creds["xray_client_secret"]
        ):
            st.info("No hay cambios respecto a lo que ya tenías cargado.")
        else:
            with st.spinner("Validando contra Xray..."):
                ok, resultado = validar_xray(client_id_a_validar, client_secret_a_validar)
            if not ok:
                st.error(f"Xray: {resultado}")
            else:
                set_key(str(_ARCHIVO_ENV), "XRAY_CLIENT_ID", client_id_a_validar)
                set_key(str(_ARCHIVO_ENV), "XRAY_CLIENT_SECRET", client_secret_a_validar)
                actualizar_credenciales_sesion(
                    {"xray_client_id": client_id_a_validar, "xray_client_secret": client_secret_a_validar},
                )
                st.success("Xray actualizado.")
                st.rerun()


st.markdown("""
<div class="config-section">
    <div class="config-section-title">Ollama (LLM local)</div>
    <div class="config-section-desc">
        Modelo de generación y embeddings corriendo localmente.
        No requiere credenciales — solo confirmar que el servidor esté activo.
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">URL del servidor</div>
            <div class="credential-hint">por defecto http://localhost:11434</div>
        </div>
        <span class="coming-soon">edición próximamente</span>
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">Modelo de generación</div>
            <div class="credential-hint">actualmente llama3.1:8b</div>
        </div>
        <span class="coming-soon">edición próximamente</span>
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">Modelo de embeddings</div>
            <div class="credential-hint">actualmente nomic-embed-text (768 dimensiones)</div>
        </div>
        <span class="coming-soon">edición próximamente</span>
    </div>
</div>
""", unsafe_allow_html=True)


st.markdown("""
<div class="config-section">
    <div class="config-section-title">Base de datos</div>
    <div class="config-section-desc">
        PostgreSQL 17 con pgvector 0.8.2 — instalación nativa en Windows.
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">Host / Puerto</div>
            <div class="credential-hint">localhost:5432</div>
        </div>
        <span class="coming-soon">edición próximamente</span>
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">Base de datos</div>
            <div class="credential-hint">agente_qa</div>
        </div>
        <span class="coming-soon">edición próximamente</span>
    </div>
    <div class="credential-row">
        <div>
            <div class="credential-label">Usuario / Contraseña</div>
            <div class="credential-hint">agente_qa_user</div>
        </div>
        <span class="coming-soon">edición próximamente</span>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    "<p style='font-size:11px;color:#64748B;margin-top:24px;'>"
    "Jira y Xray arrancan leyendo el archivo <code style='background:#E2E8F0;"
    "padding:1px 5px;border-radius:3px;'>.env</code> en la raíz del proyecto. "
    "Editar y guardar acá valida contra la API real y reescribe esa misma "
    "variable en <code style='background:#E2E8F0;padding:1px 5px;"
    "border-radius:3px;'>.env</code>. El token/secret nunca se muestran en "
    "texto plano en esta pantalla.</p>",
    unsafe_allow_html=True,
)
