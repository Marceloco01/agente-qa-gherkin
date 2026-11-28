"""
✅ Validar Mitigación — auditoría cualitativa, defecto por defecto.

Fase 3 §3.3. Esta pantalla existe para que el número del indicador TPD se
pueda cuestionar sin creerle a nadie: cada uno de los 57 defectos reales, con
el caso que el agente habría tenido, el razonamiento del juez y el arbitraje
humano, uno al lado del otro.

Dos decisiones que la hacen auditoría y no vitrina:

1. El veredicto que se muestra como vigente es EXACTAMENTE el que alimenta el
   cálculo. Si la pantalla mostrara el juicio del LLM y el indicador usara el
   humano, se estaría auditando algo distinto de lo que se reporta.
2. Los 12 defectos sin caso propuesto por el agente se muestran igual, con el
   hueco a la vista. Esconderlos dejaría una auditoría donde el agente siempre
   tiene respuesta, que es justo lo que una auditoría tiene que poder desmentir.

Vocabulario: el DATO se llama evitabilidad y sus valores son 'Evitable' /
'Parcialmente evitable' / 'No evitable' --así están en el CSV que se edita a
mano--. La PANTALLA los muestra como mitigación, por definición del indicador
(2026-09-16). La traducción es una sola, `etiqueta_veredicto()`, importada del
caso de uso: acá no se escribe ninguna etiqueta a mano, para que la pantalla
no pueda nombrar una categoría que el archivo no tiene.

Declarativa: el índice de acuerdo, la distribución y el conteo de mitigados
salen de `AuditarEvitabilidad`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from adapters.tesis.csv_tesis_repository import CsvTesisRepository
from application.tesis.auditar_evitabilidad import (


    VEREDICTOS,
    AuditarEvitabilidad,
    etiqueta_veredicto,
)
from frontend.auth import requerir_sesion
from frontend.comun.estilo import aplicar_estilo_institucional

st.set_page_config(page_title="Validar mitigación — NEXUS", page_icon="✅", layout="wide")
requerir_sesion()


aplicar_estilo_institucional()

st.markdown("""
<style>
.section-header{font-size:12px;font-weight:700;letter-spacing:.08em;
 text-transform:uppercase;color:#4F46E5;margin:22px 0 10px;}
.panel{background:#FFF;border:1px solid #E2E8F0;border-radius:6px;
 padding:14px 16px;height:100%;}
.panel h4{margin:0 0 8px;font-size:12.5px;font-weight:700;color:#0F172A;}
.campo{font-size:11px;color:#64748B;text-transform:uppercase;
 letter-spacing:.05em;margin-top:11px;}
.valor{font-size:12.5px;color:#334155;line-height:1.55;}
.gherkin{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:4px;
 padding:9px 12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
 font-size:11.5px;color:#0F172A;white-space:pre-wrap;line-height:1.5;margin-top:4px;}
.tag{display:inline-block;padding:3px 10px;border-radius:3px;font-size:11.5px;
 font-weight:700;}
.t-mitigable{background:#DCFCE7;color:#166534;}
.t-parcial{background:#FEF3C7;color:#92400E;}
.t-no{background:#FEE2E2;color:#991B1B;}
.t-crit{background:#FEE2E2;color:#991B1B;}
.t-alto{background:#FFEDD5;color:#9A3412;}
.t-medio{background:#FEF3C7;color:#92400E;}
.t-bajo{background:#F1F5F9;color:#475569;}
.vacio{background:#F8FAFC;border:1px dashed #CBD5E1;border-radius:5px;
 padding:20px;text-align:center;color:#64748B;font-size:12.5px;}
.limit{background:#F8FAFC;border-left:3px solid #CBD5E1;padding:11px 15px;
 border-radius:3px;font-size:12.5px;color:#334155;line-height:1.55;}
</style>
""", unsafe_allow_html=True)

st.markdown(
    "<h1 style='color:#0F172A;font-size:22px;font-weight:700;"
    "letter-spacing:.02em;margin-bottom:4px;'>✅ Validar mitigación</h1>"
    "<p style='color:#64748B;font-size:13px;margin-top:0;max-width:840px;'>"
    "Auditoría cualitativa del indicador TPD: cada defecto real frente al caso "
    "que el agente habría tenido.</p>",
    unsafe_allow_html=True,
)

_RAIZ = Path(__file__).resolve().parent.parent.parent
_a = AuditarEvitabilidad(CsvTesisRepository(_RAIZ)).ejecutar()
c = _a.cabecera


_CLASE_VEREDICTO = {"Evitable": "t-mitigable", "Parcialmente evitable": "t-parcial",
                    "No evitable": "t-no"}
_CLASE_CRIT = {"Critico": "t-crit", "Crítico": "t-crit", "Alto": "t-alto",
               "Medio": "t-medio", "Bajo": "t-bajo"}


st.markdown("<div class='section-header'>Auditoría defecto por defecto</div>",
            unsafe_allow_html=True)


_OPCIONES = {etiqueta_veredicto(v): v for v in VEREDICTOS}
_f1, _f2 = st.columns([1, 1])
with _f1:
    _elegidas = st.multiselect("Filtrar por veredicto", list(_OPCIONES),
                               default=list(_OPCIONES))
_filtro = [_OPCIONES[e] for e in _elegidas]
with _f2:
    _solo_disc = st.checkbox(
        f"Solo los {c.discrepancias} corregidos por el investigador",
        help="Los casos donde el arbitraje humano cambió el juicio del LLM.")

_lista = [d for d in _a.defectos
          if d.veredicto in _filtro and (not _solo_disc or d.corregido_por_humano)]
if not _lista:
    st.info("Ningún defecto coincide con el filtro.")
    st.stop()

_etiqueta = {
    f"{d.defecto_key} · {d.criticidad} · {etiqueta_veredicto(d.veredicto)}"
    f"{' · corregido' if d.corregido_por_humano else ''} — {d.titulo[:70]}": d
    for d in _lista
}
_sel = _etiqueta[st.selectbox(f"Defecto ({len(_lista)} en el filtro)",
                              list(_etiqueta))]


_izq, _der = st.columns(2)
with _izq:
    _cc = _CLASE_CRIT.get(_sel.criticidad, "t-bajo")
    _tests = "".join(
        f"<div class='campo'>Caso detector histórico · {t.get('test_key', '')}"
        f" · run: {t.get('run_estado') or 's/d'}</div>"
        f"<div class='valor'><strong>{t.get('titulo') or '(sin título)'}</strong></div>"
        + (f"<div class='gherkin'>{t['contenido']}</div>"
           if (t.get("contenido") or "").strip()
           else "<div class='valor' style='color:#94A3B8;'>Sin guion cargado en "
                "Xray — el caso existía como título, sin pasos.</div>")
        for t in _sel.tests_historicos[:3]
    ) or ("<div class='campo'>Caso detector histórico</div>"
          "<div class='valor' style='color:#94A3B8;'>Sin test vinculado.</div>")
    st.markdown(
        f"<div class='panel'><h4>🐞 El defecto real</h4>"
        f"<span class='tag {_cc}'>{_sel.criticidad}</span> "
        f"<span class='tag t-bajo'>{_sel.estado}</span>"
        f"<div class='campo'>Clave</div><div class='valor'>{_sel.defecto_key}</div>"
        f"<div class='campo'>Título</div><div class='valor'>{_sel.titulo}</div>"
        f"<div class='campo'>Descripción</div>"
        f"<div class='valor'>{_sel.descripcion or '(sin descripción registrada en Jira)'}</div>"
        f"<div class='campo'>HU vinculada</div>"
        f"<div class='valor'>{', '.join(_sel.hu_keys) or '—'}</div>"
        f"{_tests}</div>", unsafe_allow_html=True)
with _der:
    if _sel.caso_agente:
        _cuerpo = (
            f"<div class='campo'>Caso propuesto</div>"
            f"<div class='valor'><strong>{_sel.caso_agente}</strong></div>"
            f"<div class='campo'>Por qué habría atrapado el defecto</div>"
            f"<div class='valor'>{_sel.justificacion}</div>"
            f"<div class='campo'>Confianza del juez</div>"
            f"<div class='valor'>{_sel.confianza or 's/d'} · "
            f"<code>{_sel.modelo_juez}</code></div>"
        )
    else:
        _cuerpo = (
            "<div class='vacio'><strong>Sin caso preventivo propuesto por el "
            "agente.</strong><br>El juez no encontró entre los casos de Gio "
            "ninguno que anticipara este defecto."
            + (f"<br><br><span style='font-size:11.5px;'>{_sel.motivo_no_evitable}</span>"
               if _sel.motivo_no_evitable else "")
            + "</div>"
        )
    st.markdown(f"<div class='panel'><h4>🤖 El caso de Gio</h4>{_cuerpo}</div>",
                unsafe_allow_html=True)


st.markdown("<div class='section-header'>Arbitraje</div>", unsafe_allow_html=True)
_a1, _a2, _a3 = st.columns([1, 1, 2])
_a1.markdown(
    f"<div class='campo' style='margin-top:0;'>Veredicto del juez LLM</div>"
    f"<span class='tag {_CLASE_VEREDICTO.get(_sel.veredicto_llm, 't-bajo')}'>"
    f"{etiqueta_veredicto(_sel.veredicto_llm) or '—'}</span>", unsafe_allow_html=True)
_a2.markdown(
    f"<div class='campo' style='margin-top:0;'>Validación humana (vigente)</div>"
    f"<span class='tag {_CLASE_VEREDICTO.get(_sel.veredicto_humano, 't-bajo')}'>"
    f"{etiqueta_veredicto(_sel.veredicto_humano) or '(sin arbitrar)'}</span>",
    unsafe_allow_html=True)
with _a3:
    if _sel.corregido_por_humano:
        st.warning(f"El investigador **corrigió** el juicio del LLM: "
                   f"{etiqueta_veredicto(_sel.veredicto_llm)} → "
                   f"{etiqueta_veredicto(_sel.veredicto_humano)}.")
    elif _sel.veredicto_humano:
        st.success("El arbitraje humano **confirmó** el juicio del LLM.")
    else:
        st.info("Sin arbitrar: este defecto usa el juicio del LLM.")

st.markdown("<div class='campo'>Nota del investigador para la defensa oral</div>",
            unsafe_allow_html=True)
if _sel.comentario_humano:
    st.markdown(f"<div class='valor'>{_sel.comentario_humano}</div>",
                unsafe_allow_html=True)
else:
    st.caption("Sin nota registrada para este defecto.")
st.caption(
    "Las notas y los veredictos se editan en "
    "`evitabilidad_defectos_retro__<modelo>.csv`, columnas `validacion_humana` "
    "y `comentario_humano`. No se escriben desde acá: es la fuente que alimenta "
    "el indicador y un guardado a medias desde la pantalla dejaría el número "
    "reportado distinto del archivo."
)
