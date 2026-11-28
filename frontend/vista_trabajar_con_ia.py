"""
Vista de Fase 2 (Streamlit): ciclo completo.

HU desde Jira -> detección de Test Plan -> LLM genera test cases -> revisión
1x1 (Aprobar / Editar y aprobar / Rechazar) -> chat de feedback si se rechaza
-> subida a Xray de los aprobados.

Regla de esta capa: SOLO vista. No contiene lógica de negocio -- toda la
orquestación real vive en `application/`. Este archivo construye las
dependencias (inyección) y llama a los casos de uso, y mantiene el estado de
la sesión (`st.session_state`) porque Streamlit reejecuta el script completo
en cada interacción.

Fase 2 NO incluye todavía: RAG, verificación de alucinación, base de datos
(el chat de feedback vive solo en memoria de esta sesión -- ver nota en
`domain.models.MensajeFeedback`).

**Reubicado desde `frontend/streamlit_app.py` (2026-09-02)**: el contenido
de este archivo es exactamente el que antes vivía en `streamlit_app.py`, sin
ningún cambio de lógica -- se movió acá para que `streamlit_app.py` pueda
pasar a ser solo el router de `st.navigation()` (necesario para poder
ponerle un título/ícono prolijo a cada pestaña de la barra lateral, en vez
de que Streamlit lo arme automáticamente a partir del nombre de archivo).
Se sigue registrando como la página por defecto (`default=True`) con el
título "Trabajar con IA", así que el comportamiento para quien usa la app
es idéntico a antes -- solo cambió dónde vive el archivo.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from adapters.issue_tracker.jira_cloud_adapter import JiraCloudAdapter
from adapters.issue_tracker.xray_cloud_adapter import XrayCloudAdapter
from adapters.repository.sqlalchemy_repository import SqlAlchemyRepository
from adapters.vector_store.postgres_pgvector import PostgresPgvectorAdapter
from application.agregar_test_case import AgregarTestCase
from application.crear_test_plan import CrearTestPlanParaHU
from application.evaluar_hu import EvaluarHU
from application.generar_casos import GenerarCasos
from application.revisar_test_case import RegenerarTestCase, RevisarTestCase
from application.subir_a_xray import SubirTestCaseAXray
from domain.models import EstadoTestCase
from frontend.auth import obtener_credenciales, requerir_sesion
from frontend.comun.estilo import aplicar_estilo_institucional
from infrastructure.config import cargar_configuracion_rag, cargar_configuracion_vera
from infrastructure.db.conexion import obtener_sesion
from infrastructure.fabrica_llm import crear_llm_provider
from ports.llm_provider import LLMProvider

st.set_page_config(page_title="Agente QA · Vera & Gio — Fase 2", page_icon="🤖", layout="wide")


requerir_sesion()


aplicar_estilo_institucional()


if "nombre_usuario" not in st.session_state:
    st.session_state.nombre_usuario = None
if "resultado_generacion" not in st.session_state:
    st.session_state.resultado_generacion = None
if "test_plans_encontrados" not in st.session_state:
    st.session_state.test_plans_encontrados = []
if "key_test_plan_seleccionado" not in st.session_state:
    st.session_state.key_test_plan_seleccionado = None
if "test_plan_no_encontrado_confirmado" not in st.session_state:
    st.session_state.test_plan_no_encontrado_confirmado = False
if "chat_abierto_para" not in st.session_state:
    st.session_state.chat_abierto_para = None
if "descarte_pendiente_para" not in st.session_state:
    st.session_state.descarte_pendiente_para = None
if "version_formulario_agregar" not in st.session_state:
    st.session_state.version_formulario_agregar = 0


def _construir_issue_tracker() -> JiraCloudAdapter:
    credenciales = obtener_credenciales()
    return JiraCloudAdapter(
        base_url=credenciales["jira_base_url"],
        email=credenciales["jira_email"],
        api_token=credenciales["jira_api_token"],
    )


def _construir_llm_provider() -> LLMProvider:
    """
    Resuelve el proveedor de LLM a través de la fábrica, nunca instanciando
    un adaptador a mano.

    Esta función llegó a construir `OllamaProvider` directamente, con el
    modelo y el host cableados. El efecto era silencioso y feo: esta pantalla
    --la única que arma casos de prueba en el flujo real de Streamlit--
    ignoraba `LLM_PROVIDER` del `.env`, así que corría contra una
    configuración distinta de la del resto del sistema. Un cambio de modelo
    se aplicaba en los scripts y no acá, y los resultados dejaban de ser
    comparables sin que nada fallara.

    Delegar en `infrastructure.fabrica_llm.crear_llm_provider()` cierra ese
    hueco: hay un solo lugar donde se decide el proveedor. Para quien llama
    no cambia nada, sigue recibiendo algo que cumple el puerto `LLMProvider`
    con los mismos métodos `generar_test_cases()`, `generar_caso_individual()`
    y `regenerar_test_case()`.
    """
    return crear_llm_provider()


def _construir_test_management() -> XrayCloudAdapter:
    credenciales = obtener_credenciales()
    return XrayCloudAdapter(
        client_id=credenciales["xray_client_id"],
        client_secret=credenciales["xray_client_secret"],
    )


def _construir_revisar(sesion) -> RevisarTestCase:
    repository, _ = _construir_repository_y_vector_store(sesion)
    return RevisarTestCase(repository=repository)


def _construir_repository_y_vector_store(sesion) -> tuple[SqlAlchemyRepository, PostgresPgvectorAdapter]:
    """
    Construye el Repository y el VectorStore compartiendo la misma sesión
    de SQLAlchemy. Se llama desde dentro de un bloque `with obtener_sesion()`
    para que ambos adapters sean parte del mismo contexto transaccional.
    """
    return SqlAlchemyRepository(sesion), PostgresPgvectorAdapter(sesion)


if not st.session_state.nombre_usuario:
    st.title("🤖 Agente QA")
    st.caption("Con Vera (valida la HU) y Gio (genera los casos de prueba).")
    st.subheader("¿Quién eres?")
    nombre = st.text_input("Tu nombre", placeholder="ej. María")
    if st.button("Continuar", type="primary", disabled=not nombre.strip()):
        st.session_state.nombre_usuario = nombre.strip()
        st.rerun()
    st.stop()


st.title("🤖 Agente QA — Vera & Gio en acción (Fase 2)")
st.caption(f"Conectado como **{st.session_state.nombre_usuario}**")


for _clave, _inicial in (
    ("evaluacion_actual", None),
    ("hu_en_edicion", None),
    ("descripcion_original", None),
    ("forzado_confirmado", False),
    ("hu_evaluada_key", None),
):
    if _clave not in st.session_state:
        st.session_state[_clave] = _inicial


def _limpiar_gate() -> None:
    """
    Borra TODO el estado del gate.

    Existe porque el bug obvio acá es de contaminación entre HU: si se evalúa
    una HU, se la fuerza, y después se escribe otra key, el `forzado_confirmado`
    de la primera haría que la segunda se genere forzada sin que nadie lo
    haya pedido. Lo mismo con una edición: el texto de la HU anterior se
    usaría para generar la siguiente. Por eso se limpia explícitamente en los
    dos puntos de entrada de una HU nueva -- el input y la precarga desde
    Command Center -- en vez de confiar en que cada rama resetee lo suyo.
    """
    st.session_state.evaluacion_actual = None
    st.session_state.hu_en_edicion = None
    st.session_state.descripcion_original = None
    st.session_state.forzado_confirmado = False
    st.session_state.hu_evaluada_key = None
    st.session_state.resultado_generacion = None
    st.session_state.test_plans_encontrados = []
    st.session_state.key_test_plan_seleccionado = None
    st.session_state.test_plan_no_encontrado_confirmado = False
    st.session_state.chat_abierto_para = None


if "hu_precargada" in st.session_state:
    _limpiar_gate()
    st.session_state["key_hu_entrada"] = st.session_state.pop("hu_precargada")

key_hu = st.text_input("Key de la Historia de Usuario", placeholder="ej. PROJ-123",
                       key="key_hu_entrada").strip().upper()


if key_hu and st.session_state.hu_evaluada_key and key_hu != st.session_state.hu_evaluada_key:
    _limpiar_gate()

evaluar = st.button("🔍 Evaluar HU", type="primary", disabled=not key_hu,
                    help="Vera revisa la calidad de la HU. Todavía no genera nada.")

if evaluar:
    try:
        issue_tracker = _construir_issue_tracker()
        llm_provider = _construir_llm_provider()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    try:
        with st.spinner(f"Trayendo {key_hu} desde Jira y evaluándola con Vera..."):
            with obtener_sesion() as sesion:
                repository, _ = _construir_repository_y_vector_store(sesion)
                evaluado = EvaluarHU(
                    llm_provider=llm_provider,
                    repository=repository,
                    issue_tracker=issue_tracker,
                ).ejecutar(key_hu)


            test_plans = issue_tracker.detectar_test_plan(key_hu)
    except Exception as exc:
        st.error(f"No se pudo evaluar {key_hu}: {exc}")
        st.stop()
    finally:
        issue_tracker.cerrar()

    _limpiar_gate()
    st.session_state.evaluacion_actual = evaluado
    st.session_state.hu_evaluada_key = evaluado.hu.key
    st.session_state.descripcion_original = evaluado.hu.descripcion
    st.session_state.test_plans_encontrados = test_plans
    st.session_state.key_test_plan_seleccionado = (
        test_plans[0].key if len(test_plans) == 1 else None
    )
    st.rerun()


_evaluado = st.session_state.evaluacion_actual
if _evaluado is None:
    st.stop()

_hu = _evaluado.hu
_ev = _evaluado.evaluacion

st.divider()
st.subheader(f"{_hu.key} — {_hu.titulo}")


_umbral = cargar_configuracion_vera().umbral_score
_g1, _g2, _g3 = st.columns([1, 1, 2])
_g1.metric("Health Score", f"{_ev.score}/100" if _ev.score is not None else "—")
_g2.metric("Umbral vigente", f"{_umbral}/100")
with _g3:
    if _ev.aprobada:
        st.success("🟢 **Quality Gate: aprobado.** Vera considera que la HU "
                   "tiene contexto suficiente para generar casos.")
    elif _ev.depende_de_imagen:
        st.error("🔴 **Quality Gate: bloqueado por contenido visual.**")
    else:
        st.error("🔴 **Quality Gate: bloqueado.** El score no alcanza el umbral.")

if _evaluado.descripcion_es_pobre:
    st.warning(
        "La descripción de esta HU es muy corta o poco detallada (menos de 50 "
        "caracteres). Los casos generados pueden tener poco contexto."
    )


if not _ev.aprobada:
    st.markdown(f"**Motivo:** {_ev.detalle}")
    if _ev.criterios_faltantes:
        st.markdown("**Lo que Vera no encontró en la HU:**")
        for _falta in _ev.criterios_faltantes:
            st.markdown(f"- {_falta}")


if not _ev.aprobada:
    with st.expander("✏️ Corregir la HU y volver a evaluar", expanded=True):
        st.caption(
            "Lo que escribas acá **no se escribe en Jira**: se usa para "
            "reevaluar y para generar, y queda guardado en NEXUS como la "
            "descripción con la que se trabajó."
        )
        _texto = st.text_area(
            "Descripción y criterios de aceptación",
            value=st.session_state.hu_en_edicion
            if st.session_state.hu_en_edicion is not None
            else (_hu.descripcion or ""),
            height=260,
            key=f"edicion_{_hu.key}",
        )
        _cambio = _texto.strip() != (st.session_state.descripcion_original or "").strip()


        if st.button("🔁 Reevaluar con Vera", type="primary", disabled=not _cambio,
                     help="Habilitado solo si cambiaste el texto."):
            try:
                llm_provider = _construir_llm_provider()
            except ValueError as exc:
                st.error(str(exc))
                st.stop()
            _hu.descripcion = _texto
            try:
                with st.spinner("Reevaluando con Vera..."):
                    with obtener_sesion() as sesion:
                        repository, _ = _construir_repository_y_vector_store(sesion)


                        _nuevo = EvaluarHU(
                            llm_provider=llm_provider,
                            repository=repository,
                        ).reevaluar(_hu)
            except Exception as exc:
                st.error(f"No se pudo reevaluar: {exc}")
                st.stop()
            st.session_state.evaluacion_actual = _nuevo
            st.session_state.hu_en_edicion = _texto
            st.rerun()
        if not _cambio:
            st.caption("Editá el texto para habilitar la reevaluación.")


_puede_forzar = (not _ev.aprobada) and (not _ev.depende_de_imagen)
if _ev.depende_de_imagen:
    st.info(
        "Esta HU manda a una imagen, captura o adjunto, y el agente solo lee "
        "texto. **No se puede forzar la generación acá**: los casos saldrían "
        "de información que el agente no vio. Describí en el campo de arriba "
        "qué muestra esa imagen y reevaluá."
    )
elif _puede_forzar:
    if not st.session_state.forzado_confirmado:
        if st.button("⚠️ Generar igual (forzar)",
                     help="Genera pese al bloqueo. Queda registrado como forzada."):
            st.session_state.forzado_confirmado = True
            st.rerun()
    else:
        st.warning(
            "**Generación forzada activada.** Los casos se van a generar sobre "
            "una HU que Vera bloqueó, y la HU queda marcada como forzada en la "
            "base para poder separarla después en los indicadores."
        )
        if st.button("Cancelar el forzado"):
            st.session_state.forzado_confirmado = False
            st.rerun()


_listo = _ev.aprobada or st.session_state.forzado_confirmado

if _listo and st.session_state.resultado_generacion is None:
    if st.button("✨ Generar casos con Gio", type="primary"):
        try:
            llm_provider = _construir_llm_provider()
            config_rag = cargar_configuracion_rag()
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        try:
            with st.spinner("Buscando casos similares (RAG) y generando con Gio..."):
                with obtener_sesion() as sesion:
                    repository, vector_store = _construir_repository_y_vector_store(sesion)
                    _resultado = GenerarCasos(
                        llm_provider=llm_provider,
                        repository=repository,
                        vector_store=vector_store,
                        top_k=config_rag.top_k,
                    ).ejecutar(
                        _hu,
                        evaluacion=_ev,
                        forzada=bool(st.session_state.forzado_confirmado and not _ev.aprobada),
                        descripcion_usada=st.session_state.hu_en_edicion,
                        descripcion_original=st.session_state.descripcion_original,
                    )
        except Exception as exc:
            st.error(f"No se pudo generar test cases para {_hu.key}: {exc}")
            st.stop()
        st.session_state.resultado_generacion = _resultado
        st.rerun()

resultado = st.session_state.resultado_generacion
if resultado is None:
    st.stop()

if resultado.forzada:
    st.warning(
        f"⚠️ Estos casos se generaron **forzando** el bloqueo de Vera "
        f"(score {resultado.evaluacion_hu.score if resultado.evaluacion_hu else 's/d'} "
        f"< umbral {_umbral}). La HU quedó marcada como forzada."
    )
if st.session_state.hu_en_edicion:
    st.info("📝 Se generó con la descripción **editada en pantalla**, no con la "
            "de Jira. Jira no fue modificado.")
st.caption(f"Contexto RAG: {resultado.casos_similares_usados} casos similares del histórico.")

with st.expander("Ver descripción original de la HU"):
    st.text(resultado.hu.descripcion or "(sin descripción)")


test_plans_encontrados = st.session_state.test_plans_encontrados
key_test_plan = st.session_state.key_test_plan_seleccionado

if key_test_plan:
    info_seleccionada = next((tp for tp in test_plans_encontrados if tp.key == key_test_plan), None)
    if info_seleccionada:
        st.info(f"Test Plan seleccionado: **{info_seleccionada}**")
    else:


        st.info(f"Test Plan seleccionado: **{key_test_plan}**")

elif test_plans_encontrados:
    st.warning(
        f"Se encontraron **{len(test_plans_encontrados)} Test Plan(s)** "
        "vinculados a esta HU. Elige cuál usar para subir los tests:"
    )
    eleccion = st.radio(
        "Test Plan a usar",
        test_plans_encontrados,
        key="eleccion_test_plan",
        index=None,
        format_func=str,
    )
    if eleccion and st.button("Usar este Test Plan", type="primary"):
        st.session_state.key_test_plan_seleccionado = eleccion.key
        st.rerun()

else:
    st.warning(
        "No se encontró ningún Test Plan vinculado a esta HU vía el issue "
        "link \"Será atendido por\". Puedes crear uno nuevo (se vinculará "
        "automáticamente a esta HU), continuar sin vincular los tests a "
        "ningún Test Plan, o cancelar y vincularlo manualmente en Jira."
    )
    if st.button("Continuar sin Test Plan"):
        st.session_state.test_plan_no_encontrado_confirmado = True
        st.rerun()


with st.expander("➕ Crear otro Test Plan", expanded=not test_plans_encontrados and not key_test_plan):
    titulo_test_plan_manual = st.text_input(
        "Título del Test Plan",
        value=f"Test Plan - {resultado.hu.titulo}",
        key="titulo_test_plan_manual",
    )
    if st.button("Crear y vincular a la HU", key="crear_test_plan_nuevo"):
        try:
            issue_tracker = _construir_issue_tracker()
            test_management = _construir_test_management()
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        try:
            project_key = issue_tracker.project_key_de(resultado.hu.key)
            crear_test_plan = CrearTestPlanParaHU(issue_tracker, test_management)
            summary = titulo_test_plan_manual.strip() or f"Test Plan - {resultado.hu.titulo}"
            with st.spinner("Creando Test Plan y vinculándolo a la HU (puede tardar ~30s)..."):
                nuevo_key_test_plan = crear_test_plan.ejecutar(
                    key_hu=resultado.hu.key,
                    summary=summary,
                    project_key=project_key,
                )
        except Exception as exc:
            st.error(f"No se pudo crear el Test Plan: {exc}")
            st.stop()
        finally:
            issue_tracker.cerrar()
            test_management.cerrar()

        st.session_state.key_test_plan_seleccionado = nuevo_key_test_plan
        st.success(f"Test Plan {nuevo_key_test_plan} creado y vinculado a la HU.")
        st.rerun()

if not key_test_plan and not st.session_state.test_plan_no_encontrado_confirmado:
    st.stop()

st.divider()


if not resultado.test_cases:


    st.warning(
        "Gio no generó ningún test case para esta HU, pese a tener luz verde "
        "para hacerlo. Revisá los logs del proveedor de LLM."
    )
    st.stop()

st.subheader(f"🧩 Test cases generados por Gio ({len(resultado.test_cases)})")

revisar = None

for test_case in resultado.test_cases:
    with st.container(border=True):
        col_titulo, col_estado = st.columns([4, 1])
        with col_titulo:
            st.markdown(f"**{test_case.titulo}**")
        with col_estado:
            colores_estado = {
                EstadoTestCase.PENDIENTE: "⏳ Pendiente",
                EstadoTestCase.APROBADO: "✅ Aprobado",
                EstadoTestCase.RECHAZADO: "❌ Rechazado",
                EstadoTestCase.SUBIDO_A_XRAY: "📤 Subido a Xray",
            }
            st.markdown(colores_estado[test_case.estado])

        if test_case.estado == EstadoTestCase.SUBIDO_A_XRAY:
            st.code(test_case.gherkin, language="gherkin")
            st.success(f"Subido a Xray como **{test_case.xray_test_key}**")
            continue


        if test_case.alucinacion_detectada:
            st.warning(
                f"⚠️ Posible alucinación detectada: {test_case.alucinacion_detalle}\n\n"
                "Debes regenerar con un comentario antes de poder aprobar este test case."
            )


        nuevo_gherkin = st.text_area(
            "Gherkin", value=test_case.gherkin,
            key=f"gherkin_{test_case.id}_{test_case.version_contenido}", height=150,
        )

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            gherkin_fue_editado = nuevo_gherkin.strip() != test_case.gherkin.strip()
            if st.button(
                "✅ Aprobar", key=f"aprobar_{test_case.id}",
                disabled=test_case.alucinacion_detectada and not gherkin_fue_editado,
            ):
                with obtener_sesion() as sesion:
                    revisar = _construir_revisar(sesion)
                    if nuevo_gherkin.strip() != test_case.gherkin.strip():
                        revisar.editar_y_aprobar(test_case, nuevo_gherkin)


                        if test_case.alucinacion_detectada:
                            test_case.alucinacion_detectada = False
                            test_case.alucinacion_detalle = None
                            with obtener_sesion() as sesion2:
                                repo2, _ = _construir_repository_y_vector_store(sesion2)
                                repo2.actualizar_alucinacion(test_case.id, False, None)
                    else:
                        revisar.aprobar(test_case)
                st.rerun()
        with col2:
            if st.button("❌ Rechazar", key=f"rechazar_{test_case.id}"):
                with obtener_sesion() as sesion:
                    revisar = _construir_revisar(sesion)
                    revisar.rechazar(test_case)
                st.session_state.chat_abierto_para = test_case.id
                st.rerun()
        with col3:
            if test_case.estado == EstadoTestCase.RECHAZADO:
                if st.button("🗑️ Descartar", key=f"descartar_{test_case.id}"):
                    st.session_state.descarte_pendiente_para = test_case.id
                    st.session_state.chat_abierto_para = None
                    st.rerun()
        with col4:
            pass


        if test_case.estado == EstadoTestCase.RECHAZADO and st.session_state.descarte_pendiente_para == test_case.id:
            st.markdown("**¿Por qué descartas este caso?**")
            motivo_descarte = st.text_input(
                "Motivo (obligatorio)", key=f"motivo_descarte_{test_case.id}",
            )
            col_confirmar, col_cancelar = st.columns(2)
            with col_confirmar:
                if st.button(
                    "Confirmar descarte", key=f"confirmar_descarte_{test_case.id}",
                    disabled=not motivo_descarte.strip(),
                ):
                    with obtener_sesion() as sesion:
                        revisar = _construir_revisar(sesion)
                        revisar.descartar(test_case, motivo_descarte)


                    resultado.test_cases = [
                        tc for tc in resultado.test_cases if tc.id != test_case.id
                    ]
                    st.session_state.descarte_pendiente_para = None
                    st.success(f"Caso '{test_case.titulo}' descartado.")
                    st.rerun()
            with col_cancelar:
                if st.button("Cancelar", key=f"cancelar_descarte_{test_case.id}"):
                    st.session_state.descarte_pendiente_para = None
                    st.rerun()


        mostrar_chat = (
            test_case.estado == EstadoTestCase.RECHAZADO
            and st.session_state.chat_abierto_para == test_case.id
        ) or test_case.alucinacion_detectada

        if mostrar_chat:
            st.markdown("**Historial de feedback:**")
            for mensaje in test_case.historial_feedback:
                if mensaje.autor == "usuario":
                    st.markdown(f"🧑 **Tú:** {mensaje.texto}")
                else:


                    st.markdown(f"🤖 **Agente:** {mensaje.texto}")

            st.divider()
            mensaje_nuevo = st.text_input(
                "Explica qué corregir" + (" (obligatorio: hay una posible alucinación)" if test_case.alucinacion_detectada else ""),
                key=f"chat_input_{test_case.id}_{test_case.version_contenido}",
            )
            if st.button("Enviar y regenerar", key=f"enviar_chat_{test_case.id}", disabled=not mensaje_nuevo.strip()):
                try:
                    llm_provider = _construir_llm_provider()
                    with obtener_sesion() as sesion:
                        repository, _ = _construir_repository_y_vector_store(sesion)
                        regenerar = RegenerarTestCase(llm_provider=llm_provider, repository=repository)
                        with st.spinner("Regenerando con el feedback..."):
                            regenerar.regenerar(test_case, mensaje_nuevo.strip(), resultado.hu.descripcion)
                except Exception as exc:
                    st.error(f"No se pudo regenerar: {exc}")
                    st.stop()
                st.rerun()


st.divider()
st.subheader("➕ Agregar caso de prueba")
st.caption(
    "Como experto QA, agrega un caso que el LLM no haya generado: "
    "escríbelo tú mismo, o descríbele el escenario a la IA para que lo "
    "redacte en Gherkin."
)

version_form = st.session_state.version_formulario_agregar
modo_agregar = st.radio(
    "¿Cómo quieres agregarlo?",
    ["Escribirlo yo mismo", "Que la IA lo redacte"],
    key=f"modo_agregar_{version_form}",
    horizontal=True,
)

if modo_agregar == "Escribirlo yo mismo":
    titulo_manual = st.text_input("Título del caso", key=f"titulo_manual_{version_form}")
    gherkin_manual = st.text_area(
        "Gherkin completo",
        key=f"gherkin_manual_{version_form}",
        height=150,
        placeholder="Scenario: ...\n  Given ...\n  When ...\n  Then ...",
    )
    if st.button("Agregar caso", key=f"agregar_manual_{version_form}", disabled=not gherkin_manual.strip()):
        try:
            nuevo_tc = AgregarTestCase().agregar_manual(
                hu_key=resultado.hu.key, titulo=titulo_manual, gherkin=gherkin_manual,
            )
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        resultado.test_cases.append(nuevo_tc)
        st.session_state.version_formulario_agregar += 1
        st.success(f"Caso '{nuevo_tc.titulo}' agregado. Ya aparece en la lista para revisión.")
        st.rerun()

else:
    descripcion_escenario = st.text_area(
        "Describe el escenario que quieres cubrir",
        key=f"descripcion_escenario_{version_form}",
        placeholder='ej. "que pase si la contraseña tiene menos de 8 caracteres"',
        height=80,
    )
    if st.button(
        "🤖 Generar con IA", key=f"agregar_con_ia_{version_form}",
        disabled=not descripcion_escenario.strip(),
    ):
        try:
            llm_provider = _construir_llm_provider()
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        try:
            with st.spinner("Generando el caso con el LLM..."):
                nuevo_tc = AgregarTestCase(llm_provider).agregar_con_ia(
                    resultado.hu, descripcion_escenario,
                )
        except Exception as exc:
            st.error(f"No se pudo generar el caso: {exc}")
            st.stop()

        resultado.test_cases.append(nuevo_tc)
        st.session_state.version_formulario_agregar += 1
        st.success(f"Caso '{nuevo_tc.titulo}' generado y agregado. Ya aparece en la lista para revisión.")
        st.rerun()


aprobados = [tc for tc in resultado.test_cases if tc.estado == EstadoTestCase.APROBADO]

if aprobados:
    st.divider()
    st.subheader(f"Subir a Xray ({len(aprobados)} aprobado(s) pendiente(s) de subir)")

    with st.expander("Opción avanzada: elegir proyecto destino manualmente"):
        st.caption(
            "Por defecto, el Test se crea en el mismo proyecto donde vive el "
            "Test Plan detectado. Solo cambia esto si necesitas redirigir el "
            "Test a otro proyecto Jira."
        )
        project_key_manual = st.text_input("Project key destino (opcional)", key="project_key_manual")

    if st.button("📤 Subir aprobados a Xray", type="primary"):
        try:
            issue_tracker = _construir_issue_tracker()
            test_management = _construir_test_management()
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        subir = SubirTestCaseAXray(issue_tracker=issue_tracker, test_management=test_management)
        project_destino = project_key_manual.strip() or None

        progreso = st.progress(0.0)
        errores = []
        for i, tc in enumerate(aprobados):
            try:
                subir.ejecutar(tc, key_test_plan=key_test_plan, project_key_destino=project_destino)
            except Exception as exc:


                errores.append((tc.titulo, str(exc)))
            progreso.progress((i + 1) / len(aprobados))

        issue_tracker.cerrar()
        test_management.cerrar()

        if errores:
            for titulo, error in errores:
                st.error(f"Falló la subida de '{titulo}': {error}")
        subidos_ok = len(aprobados) - len(errores)
        if subidos_ok:
            st.success(f"{subidos_ok} test case(s) subido(s) a Xray correctamente.")
        st.rerun()
