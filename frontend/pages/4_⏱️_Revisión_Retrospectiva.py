"""
🔄 Revisión retrospectiva — qué hizo el humano con lo que propuso Gio.

Fase 4.2. Es el contrapeso de todo el resto del tablero: acá no se mide qué
tan bien le fue al agente, sino cuánto de lo que produjo hubo que tirar, por
qué, y cuánto costó revisarlo.

Sobre los tiempos: se reporta SOLO el lado NEXUS, que está medido de verdad.
El tiempo de diseño manual no se estima ni se rellena --las tres fuentes del
proyecto están rotas y el motivo se muestra en pantalla--. Un "ahorro del
X%" contra un número inventado es exactamente el tipo de dato que se cae en
una sustentación.

Declarativa: el cálculo vive en
`application/impacto/AnalizarRevisionRetrospectiva`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from adapters.tesis.csv_tesis_repository import CsvTesisRepository
from application.impacto.analizar_impacto import AnalizarRevisionRetrospectiva
from frontend.auth import requerir_sesion
from frontend.comun.graficos import NARANJA, barras_horizontales
from frontend.comun.estilo import aplicar_estilo_institucional

st.set_page_config(page_title="Revisión retrospectiva — NEXUS", page_icon="🔄",
                   layout="wide")
requerir_sesion()


aplicar_estilo_institucional()

st.markdown("""
<style>
.section-header{font-size:12px;font-weight:700;letter-spacing:.08em;
 text-transform:uppercase;color:#4F46E5;margin:24px 0 10px;}
.nota{background:#F8FAFC;border-left:3px solid #CBD5E1;padding:11px 15px;
 border-radius:3px;font-size:12.5px;color:#334155;line-height:1.55;margin:10px 0;}
.aviso{background:#FFF7ED;border-left:3px solid #F59E0B;padding:11px 15px;
 border-radius:3px;font-size:12.5px;color:#7C2D12;line-height:1.55;margin:10px 0;}
</style>
""", unsafe_allow_html=True)

st.markdown(
    "<h1 style='color:#0F172A;font-size:22px;font-weight:700;"
    "letter-spacing:.02em;margin-bottom:4px;'>🔄 Revisión retrospectiva</h1>"
    "<p style='color:#64748B;font-size:13px;margin-top:0;max-width:840px;'>"
    "Auditoría manual de los casos que propuso Gio: qué se aprobó, qué se "
    "descartó y por qué.</p>", unsafe_allow_html=True,
)

_RAIZ = Path(__file__).resolve().parent.parent.parent
_uso = AnalizarRevisionRetrospectiva(CsvTesisRepository(_RAIZ))
_opciones = {"Completa": "completa", "Estándar": "estandar", "Primario": "primario"}
_sel = st.selectbox("Cohorte", list(_opciones), index=0)
r = _uso.ejecutar(_opciones[_sel])
_t = r.tiempos


_k1, _k2, _k3, _k4 = st.columns(4)
_k1.metric("Casos propuestos por Gio", str(r.total_propuestos))
_k1.caption(f"{r.cohorte_nombre} · {r.n_hu} HU")
_k2.metric("Aprobación humana", f"{r.tasa_aprobacion:.1f}%")
_k2.caption(f"{r.aprobados} de {r.total_propuestos}")
_k3.metric("Tasa de rechazo", f"{r.tasa_rechazo:.1f}%", f"-{r.rechazados} casos",
           delta_color="inverse")
_k3.caption("descartados en la revisión")
if r.ciclo_nexus_segundos_hu:
    _k4.metric("Ciclo NEXUS por HU", f"{r.ciclo_nexus_segundos_hu:.0f} s")
    _k4.caption(f"{_t.generacion_segundos_mediana:.0f} s generar + "
                f"{_t.revision_minutos_mediana_hu * 60:.0f} s revisar")


st.markdown("<div class='section-header'>Por qué se descartaron los "
            f"{r.rechazados} casos</div>", unsafe_allow_html=True)
st.markdown(
    barras_horizontales(
        [{"etiqueta": m.familia, "valor": m.casos, "nota": f"{m.porcentaje:.1f}%"}
         for m in r.motivos],
        color=NARANJA,
    ),
    unsafe_allow_html=True,
)
if r.motivos:
    _top = r.motivos[0]
    st.markdown(
        f"<div class='nota'><strong>El motivo dominante es "
        f"{_top.familia.lower()}: {_top.casos} de {r.rechazados} "
        f"({_top.porcentaje:.1f}%).</strong> En la mayoría son montos, nombres "
        f"de cliente o endpoints concretos que el caso da por ciertos y que no "
        f"aparecen en los criterios de la HU. Es un modo de falla específico y "
        f"accionable —el agente rellena lo que no está especificado— y no un "
        f"rechazo genérico por calidad.</div>", unsafe_allow_html=True)
st.caption(
    "La columna `motivo_rechazo` del corpus es texto libre —34 valores "
    "distintos entre los rechazos— así que la familia se deriva por patrón "
    "sobre ese texto. El motivo original, sin agrupar, está en la tabla."
)


st.markdown("<div class='section-header'>Casos descartados</div>",
            unsafe_allow_html=True)
_df = pd.DataFrame(r.detalle_rechazados)
_fam = st.multiselect("Familia", [m.familia for m in r.motivos], default=[])
if _fam:
    _df = _df[_df["Familia"].isin(_fam)]
st.dataframe(_df, use_container_width=True, hide_index=True)
st.download_button(
    "⬇️ Exportar descartados (CSV)",
    data=_df.to_csv(index=False).encode("utf-8"),
    file_name=f"casos_descartados_{r.n_hu}hu.csv", mime="text/csv",
)


st.markdown("<div class='section-header'>Esfuerzo del ciclo de diseño</div>",
            unsafe_allow_html=True)
_c1, _c2 = st.columns([1, 1.5])
with _c1:
    if _t.generacion_segundos_mediana is not None:
        st.metric("Generación (Gio)", f"{_t.generacion_segundos_mediana:.1f} s")
        st.caption(f"mediana de {_t.generacion_n} corridas")
    if _t.revision_segundos_por_caso is not None:
        st.metric("Revisión humana", f"{_t.revision_segundos_por_caso:.0f} s / caso")
        st.caption(f"{_t.revision_minutos_total:.0f} min para "
                   f"{_t.revision_n_casos} casos en {_t.revision_n_hu} HU")
with _c2:
    st.markdown(
        "<div class='aviso'><strong>No hay comparativa contra el proceso "
        "manual, y no se inventa una.</strong> Para calcular un ahorro haría "
        "falta el tiempo de diseño histórico por HU, y ese dato no existe en "
        f"forma usable: {_t.motivo_sin_dato_humano}</div>",
        unsafe_allow_html=True)
    st.markdown(
        "<div class='nota'>Lo que sí se puede afirmar con lo medido: el agente "
        "propone los casos de una HU en segundos, y revisarlos cuesta "
        f"<strong>{_t.revision_segundos_por_caso:.0f} segundos por caso</strong>. "
        "Comparar eso contra escribirlos desde cero es una afirmación "
        "razonable en dirección, pero no en magnitud — y en una tesis esa "
        "diferencia importa.</div>", unsafe_allow_html=True)
