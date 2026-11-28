"""
Login real de la app -- gate de acceso a todas las páginas.

Decisión (adoptada para este diseño, 2026-09-01): esto NO es un usuario y
contraseña propios de la app. Es la validación de que el agente tiene
credenciales REALES y funcionando contra Jira/Xray -- email + API Token de
Jira, Client ID + Client Secret de Xray. Sin credenciales que validen de
verdad contra las dos APIs (no solo "no está vacío"), no se puede usar
ninguna página: "sin eso no se puede usar el agente".

Decisión 2 (2026-09-01, aclarada en revisión): por ahora el agente lo usa una sola
persona (el propio usuario) -- "aún no se puede desplegar" para que lo use
el resto del equipo QA. Con un solo usuario, pedir el formulario manual en
cada `streamlit run` es fricción sin beneficio: las credenciales ya están
en `.env` desde antes de que existiera este login. Por eso el gate
primero intenta un AUTO-LOGIN silencioso leyendo `.env`
(`cargar_configuracion_jira()` / `cargar_configuracion_xray()`) y
validándolo con las mismas llamadas reales de siempre -- si `.env` no
existe, le falta una variable, o Jira/Xray la rechazan, recién ahí cae al
formulario manual como respaldo. Esto deja el diseño listo para el día que
se despliegue para el equipo (ahí el auto-login desde `.env` deja de tener
sentido -- cada persona no puede compartir un solo `.env` -- y el
formulario manual pasa a ser el camino normal, no el respaldo).

`JIRA_BASE_URL` sigue viniendo de `.env` -- no es un secreto, es la URL
fija de la instancia de Jira de la empresa (no cambia por persona ni por
sesión), mismo criterio que ya usa el resto del proyecto para distinguir
config de infraestructura vs. credenciales.

Uso: cada página (`streamlit_app.py` y cada archivo en `frontend/pages/`)
llama a `requerir_sesion()` como primera línea después de
`st.set_page_config(...)`. Si ya hay una sesión válida en
`st.session_state`, no hace nada y la página sigue normal. Si no, intenta
el auto-login desde `.env`; si eso falla, muestra el formulario de login y
corta la ejecución con `st.stop()` -- la página nunca llega a su propio
contenido -- y navegar directo a cualquier página sin sesión válida repite
el mismo flujo.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

from infrastructure.config import cargar_configuracion_jira, cargar_configuracion_xray

_URL_AUTENTICACION_XRAY = "https://xray.cloud.getxray.app/api/v2/authenticate"
_TIMEOUT_SEGUNDOS = 15.0


def _validar_jira(base_url: str, email: str, api_token: str) -> tuple[bool, str]:
    """
    Llamada real a `GET /rest/api/3/myself` -- si el email/token son
    inválidos, Jira responde 401 antes de devolver nada. Si son válidos,
    devuelve el perfil de la cuenta (usamos `displayName` para mostrar
    "conectado como X", no solo un check silencioso).
    """
    try:
        with httpx.Client(auth=(email, api_token), timeout=_TIMEOUT_SEGUNDOS) as cliente:
            resp = cliente.get(f"{base_url}/rest/api/3/myself")
    except httpx.RequestError as exc:
        return False, f"No se pudo conectar a Jira ({base_url}): {exc}"

    if resp.status_code == 200:
        nombre = resp.json().get("displayName", email)
        return True, nombre
    if resp.status_code == 401:
        return False, "Jira rechazó el email/API token (401) -- revisá que estén bien copiados."
    return False, f"Jira respondió {resp.status_code} de forma inesperada."


def _validar_xray(client_id: str, client_secret: str) -> tuple[bool, str]:
    """
    Llamada real a `authenticate` de Xray Cloud -- mismo endpoint que usan
    todos los scripts del proyecto. Si responde 200, el body es el bearer
    token (no hace falta guardarlo acá, cada script/adapter lo vuelve a
    pedir cuando lo necesita).
    """
    try:
        with httpx.Client(timeout=_TIMEOUT_SEGUNDOS) as cliente:
            resp = cliente.post(
                _URL_AUTENTICACION_XRAY,
                json={"client_id": client_id, "client_secret": client_secret},
            )
    except httpx.RequestError as exc:
        return False, f"No se pudo conectar a Xray: {exc}"

    if resp.status_code == 200:
        return True, ""
    if resp.status_code in (400, 401):
        return False, "Xray rechazó el Client ID/Client Secret -- revisá que estén bien copiados."
    return False, f"Xray respondió {resp.status_code} de forma inesperada."


def validar_jira(base_url: str, email: str, api_token: str) -> tuple[bool, str]:
    """Versión pública de `_validar_jira`, para la página de Configuración."""
    return _validar_jira(base_url, email, api_token)


def validar_xray(client_id: str, client_secret: str) -> tuple[bool, str]:
    """Versión pública de `_validar_xray`, para la página de Configuración."""
    return _validar_xray(client_id, client_secret)


def actualizar_credenciales_sesion(cambios: dict, jira_nombre: str | None = None) -> None:
    """
    Reemplaza en la sesión activa solo las credenciales indicadas en
    `cambios` (claves de `auth_credenciales`, p. ej. `jira_email`), después
    de que la página de Configuración las validó contra la API real. Si se
    pasa `jira_nombre`, actualiza también el nombre que muestra la barra
    lateral.
    """
    _inicializar_estado()
    credenciales = dict(st.session_state.auth_credenciales or {})
    credenciales.update(cambios)
    st.session_state.auth_credenciales = credenciales
    if jira_nombre:
        st.session_state.auth_jira_nombre = jira_nombre


def _inicializar_estado() -> None:
    if "auth_sesion_valida" not in st.session_state:
        st.session_state.auth_sesion_valida = False
    if "auth_credenciales" not in st.session_state:
        st.session_state.auth_credenciales = None
    if "auth_jira_nombre" not in st.session_state:
        st.session_state.auth_jira_nombre = None
    if "auth_modo" not in st.session_state:
        st.session_state.auth_modo = None
    if "auth_forzar_manual" not in st.session_state:


        st.session_state.auth_forzar_manual = False


def _cerrar_sesion() -> None:
    st.session_state.auth_sesion_valida = False
    st.session_state.auth_credenciales = None
    st.session_state.auth_jira_nombre = None
    st.session_state.auth_modo = None
    st.session_state.auth_forzar_manual = True


def _intentar_auto_login() -> bool:
    """
    Caso de un solo usuario local: si `.env` ya tiene las 5 variables
    (JIRA_BASE_URL/EMAIL/API_TOKEN + XRAY_CLIENT_ID/SECRET) y son válidas
    de verdad contra las APIs, entra sin pedir el formulario. Si falta
    algo o `.env` tiene credenciales viejas/rotadas, devuelve False y
    `requerir_sesion()` cae al formulario manual.
    """
    try:
        config_jira = cargar_configuracion_jira()
        config_xray = cargar_configuracion_xray()
    except ValueError:
        return False

    with st.spinner("Validando credenciales de .env contra Jira y Xray..."):
        jira_ok, jira_resultado = _validar_jira(config_jira.base_url, config_jira.email, config_jira.api_token)
        xray_ok, xray_resultado = _validar_xray(config_xray.client_id, config_xray.client_secret)

    if not (jira_ok and xray_ok):
        return False

    st.session_state.auth_sesion_valida = True
    st.session_state.auth_jira_nombre = jira_resultado
    st.session_state.auth_modo = "auto"
    st.session_state.auth_credenciales = {
        "jira_base_url": config_jira.base_url,
        "jira_email": config_jira.email,
        "jira_api_token": config_jira.api_token,
        "xray_client_id": config_xray.client_id,
        "xray_client_secret": config_xray.client_secret,
    }
    return True


def _mostrar_formulario_login(base_url: str) -> None:
    st.markdown(
        "<h1 style='color:#0F172A;font-size:22px;font-weight:700;"
        "letter-spacing:0.02em;margin-bottom:4px;'>🔒 Agente QA — Iniciar sesión</h1>"
        "<p style='color:#64748B;font-size:13px;margin-top:0;margin-bottom:24px;'>"
        "Ingresá tus credenciales reales de Jira y Xray. Se validan contra las "
        "APIs antes de dejarte entrar -- no se guardan en ningún archivo, solo "
        "viven en esta sesión del navegador.</p>",
        unsafe_allow_html=True,
    )

    if not st.session_state.auth_forzar_manual:
        st.warning(
            "No se pudo entrar automáticamente con las credenciales de `.env` "
            "(falta alguna variable, o Jira/Xray las rechazó). Completá el "
            "formulario manualmente.",
            icon="⚠️",
        )

    if not base_url:
        st.error(
            "Falta `JIRA_BASE_URL` en tu archivo `.env` -- eso no se pide acá "
            "(no es un secreto, es la URL fija de tu instancia de Jira). "
            "Agregala en `.env` y volvé a correr la app."
        )
        st.stop()

    with st.form("form_login"):
        st.markdown("**Jira Cloud**")
        jira_email = st.text_input("Email", placeholder="tu.usuario@empresa.com")
        jira_token = st.text_input("API Token", type="password")

        st.markdown("**Xray Cloud**")
        xray_client_id = st.text_input("Client ID", type="password")
        xray_client_secret = st.text_input("Client Secret", type="password")

        enviado = st.form_submit_button("Ingresar", type="primary")

    if not enviado:
        st.stop()

    if not (jira_email.strip() and jira_token.strip() and xray_client_id.strip() and xray_client_secret.strip()):
        st.error("Completá los 4 campos -- ninguno puede quedar vacío.")
        st.stop()

    with st.spinner("Validando credenciales contra Jira y Xray..."):
        jira_ok, jira_resultado = _validar_jira(base_url, jira_email.strip(), jira_token.strip())
        xray_ok, xray_resultado = _validar_xray(xray_client_id.strip(), xray_client_secret.strip())

    if not jira_ok:
        st.error(f"Jira: {jira_resultado}")
    if not xray_ok:
        st.error(f"Xray: {xray_resultado}")

    if jira_ok and xray_ok:
        st.session_state.auth_sesion_valida = True
        st.session_state.auth_jira_nombre = jira_resultado
        st.session_state.auth_modo = "manual"
        st.session_state.auth_forzar_manual = False
        st.session_state.auth_credenciales = {
            "jira_base_url": base_url,
            "jira_email": jira_email.strip(),
            "jira_api_token": jira_token.strip(),
            "xray_client_id": xray_client_id.strip(),
            "xray_client_secret": xray_client_secret.strip(),
        }
        st.rerun()

    st.stop()


def requerir_sesion() -> None:
    """
    Llamar como primera línea de cada página, justo después de
    `st.set_page_config(...)`. Si ya hay sesión válida, no hace nada. Si
    no, intenta un auto-login silencioso desde `.env` (caso de un solo
    usuario local, ver docstring del módulo); si eso también falla,
    muestra el formulario de login y corta con `st.stop()` -- el resto de
    la página no se ejecuta.
    """
    _inicializar_estado()

    if not st.session_state.auth_sesion_valida:
        if not st.session_state.auth_forzar_manual and _intentar_auto_login():
            pass
        else:
            base_url = os.getenv("JIRA_BASE_URL", "")
            _mostrar_formulario_login(base_url)
            return

    with st.sidebar:
        etiqueta_modo = (
            "auto, desde .env" if st.session_state.auth_modo == "auto" else "login manual"
        )
        st.markdown(
            f"<div style='font-size:14px;color:#5B6472;margin-bottom:8px;"
            f"line-height:1.45;'>Conectado como "
            f"<b style='color:#14181F;'>{st.session_state.auth_jira_nombre}</b>"
            f"<br>({etiqueta_modo})</div>",
            unsafe_allow_html=True,
        )
        if st.button("Cerrar sesión", key="auth_cerrar_sesion"):
            _cerrar_sesion()
            st.rerun()
        st.markdown("---")


def obtener_credenciales() -> dict:
    """
    Para páginas que necesiten hacer llamadas reales a Jira/Xray (ej. el
    agente de seguimiento) -- devuelve el diccionario validado en el login
    en vez de leer `.env`. Lanza `RuntimeError` si se llama sin sesión
    válida (no debería pasar si la página ya llamó a `requerir_sesion()`
    primero).
    """
    credenciales = st.session_state.get("auth_credenciales")
    if not credenciales:
        raise RuntimeError(
            "obtener_credenciales() llamado sin sesión válida -- "
            "llamá requerir_sesion() antes."
        )
    return credenciales
