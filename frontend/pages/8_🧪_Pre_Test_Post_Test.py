"""
🧪 Pre-Test / Post-Test — análisis retrospectivo exploratorio (no es el del artículo).

Fase 3 §3.1. Esta pantalla es ESTRICTAMENTE DECLARATIVA: no calcula ni un
ratio. Todo --indicadores, deltas, filtro de sensibilidad por cohorte, tabla
maestra-- sale de `CalcularMetricasTesis`, que consume el corpus a través del
puerto `TesisRepository`.

No es purismo arquitectónico: en este proyecto apareció seis veces el mismo
bug, una pantalla mostrando un agregado calculado sobre un conjunto distinto
del que decía mostrar. Con el cálculo en un solo lugar y la muestra viajando
dentro del propio indicador (`n_muestra`), ese error deja de tener dónde
ocurrir -- acá no hay ninguna operación aritmética que pueda estar mal.

Lo único que esta pantalla decide es cómo se ve un delta según su `sentido`,
que tampoco lo inventa: se lo dice el caso de uso, porque en TPD bajar es
mejorar y en los otros tres es al revés.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from adapters.tesis.csv_tesis_repository import CsvTesisRepository
from application.tesis.calcular_metricas_tesis import CalcularMetricasTesis
from frontend.auth import requerir_sesion
from frontend.comun.estilo import aplicar_estilo_institucional

st.set_page_config(page_title="Pre-Test / Post-Test — NEXUS", page_icon="🧪", layout="wide")
requerir_sesion()


aplicar_estilo_institucional()

st.markdown("""
<style>
.section-header{font-size:12px;font-weight:700;letter-spacing:.08em;
 text-transform:uppercase;color:#4F46E5;margin:24px 0 10px;}
.kpi{background:#FFF;border:1px solid #E2E8F0;border-radius:6px;padding:14px 16px;height:100%;}
.kpi .sigla{font-size:10px;font-weight:800;letter-spacing:.1em;color:#4F46E5;
 background:#EEF2FF;display:inline-block;padding:2px 7px;border-radius:3px;}
.kpi .nombre{font-size:12.5px;font-weight:700;color:#0F172A;margin:7px 0 10px;line-height:1.35;}
.kpi .par{display:flex;justify-content:space-between;font-size:12px;color:#475569;margin:3px 0;}
.kpi .par b{color:#0F172A;font-variant-numeric:tabular-nums;}
.kpi .det{font-size:10.5px;color:#94A3B8;margin-top:1px;}
.kpi .delta{margin-top:10px;font-size:15px;font-weight:800;padding:4px 10px;
 border-radius:4px;display:inline-block;font-variant-numeric:tabular-nums;}
.d-bien{background:#DCFCE7;color:#166534;}
.d-neutro{background:#FEF3C7;color:#92400E;}
.badge{background:#F1F5F9;border:1px solid #E2E8F0;border-radius:5px;
 padding:9px 14px;font-size:12.5px;color:#334155;}
.badge b{color:#0F172A;}
.nota{background:#F8FAFC;border-left:3px solid #CBD5E1;padding:10px 14px;
 border-radius:3px;font-size:12.5px;color:#334155;margin:10px 0;line-height:1.55;}
</style>
""", unsafe_allow_html=True)

st.markdown(
    "<h1 style='color:#0F172A;font-size:22px;font-weight:700;"
    "letter-spacing:.02em;margin-bottom:4px;'>🧪 Pre-Test / Post-Test</h1>"
    "<p style='color:#64748B;font-size:13px;margin-top:0;'>"
    "Análisis exploratorio y retrospectivo: el proceso manual frente a lo que "
    "NEXUS habría hecho sobre las mismas historias. No es la comparación del "
    "artículo, que usa ciclos distintos en cada periodo (ver Resultados).</p>",
    unsafe_allow_html=True,
)

_RAIZ = Path(__file__).resolve().parent.parent.parent
_uso = CalcularMetricasTesis(CsvTesisRepository(_RAIZ))


_previo = _uso.ejecutar()
_opciones = {
    f"{c['nombre']} (N = {c['n']})": c["clave"]
    for c in reversed(_previo.cohortes_disponibles)
}
_f1, _f2 = st.columns([1.3, 2.7])
with _f1:
    _elegida = st.selectbox("Cohorte", list(_opciones), index=0,
                            help="Análisis de sensibilidad: la muestra se "
                                 "recalcula entera, no se filtra la tabla.")
r = _uso.ejecutar(_opciones[_elegida])
with _f2:
    st.markdown(
        f"<div class='badge'>Muestra activa: <b>{r.n_hu} historias</b> · "
        f"<b>{r.n_criterios} criterios</b> · <b>{r.estado_defectos_global.n_muestra} HU auditadas "
        f"para defectos</b><br>"
        f"<span style='font-size:11px;color:#64748B;'>{_elegida} — "
        f"{[c['nota'] for c in r.cohortes_disponibles if c['clave']==r.cohorte_clave][0]}"
        "</span></div>",
        unsafe_allow_html=True,
    )


st.markdown("<div class='section-header'>Indicadores oficiales · las tres "
            "variables dependientes</div>", unsafe_allow_html=True)


def _tarjeta(col, ind) -> None:
    """Dibuja. No calcula: el delta y su signo vienen resueltos del caso de uso."""
    unidad = "" if ind.unidad == "conteo" else "%"
    fmt = "{:.0f}" if ind.unidad == "conteo" else "{:.1f}"


    if ind.delta_etiqueta:
        delta_txt = ind.delta_etiqueta
    elif ind.unidad == "conteo":
        delta_txt = f"{ind.delta_porcentual:+.1f}%"
    else:
        delta_txt = f"{ind.delta_absoluto:+.1f} pts"
    clase = "d-neutro" if ind.sentido == "neutro" else "d-bien"
    with col:
        st.markdown(
            f"<div class='kpi'>"
            f"<span class='sigla'>{ind.sigla}</span>"
            f"<div class='nombre'>{ind.nombre}</div>"
            f"<div class='par'><span>{ind.etiqueta_pre}</span>"
            f"<b>{fmt.format(ind.valor_pre)}{unidad}</b></div>"
            f"<div class='det'>{ind.detalle_pre}</div>"
            f"<div class='par' style='margin-top:7px;'>"
            f"<span>{ind.etiqueta_post}</span>"
            f"<b>{fmt.format(ind.valor_post)}{unidad}</b></div>"
            f"<div class='det'>{ind.detalle_post}</div>"
            f"<div class='delta {clase}'>{delta_txt}</div>"
            f"<div class='det' style='margin-top:6px;'>n = {ind.n_muestra} HU</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


_OFICIALES = (r.indice_cobertura_pruebas, r.indice_ejecutabilidad_estructural,
              r.estado_defectos_global)
for _col, _ind in zip(st.columns(3), _OFICIALES):
    _tarjeta(_col, _ind)


st.markdown("<div class='section-header'>Estado de defectos por severidad</div>",
            unsafe_allow_html=True)
st.dataframe(
    [{"Severidad": d.severidad, "Abiertos": d.abiertos, "Cerrados": d.cerrados,
      "Total detectados": d.total_detectados, "Mitigados": d.mitigados,
      "Estado de defectos (%)": round(d.ratio_estado, 1)}
     for d in r.estado_defectos_por_severidad],
    use_container_width=True, hide_index=True,
)
st.caption("Abiertos + Cerrados puede dar menos que el total: 1 defecto no "
           "tiene estado resuelto en Jira.")


st.markdown("<div class='section-header'>Viabilidad operativa</div>",
            unsafe_allow_html=True)
_e = r.viabilidad_operativa_control
_q1, _q2, _q3 = st.columns([1, 1, 2])
_q1.metric("Pre-Test", f"{_e.valor_pre:.1f}%")
_q1.caption(_e.detalle_pre)
_q2.metric("Post-Test", f"{_e.valor_post:.1f}%", f"{_e.delta_absoluto:+.1f} pts")
_q2.caption(_e.detalle_post)


_q3.caption("Métrica secundaria de capacidad.")

st.markdown("<div class='section-header'>Métricas de control</div>",
            unsafe_allow_html=True)
_c1, _c2 = st.columns(2)
with _c1:
    _d1, _d2 = st.columns(2)
    _d1.metric("DRC Pre", f"{r.drc_pre:.3f}")
    _d2.metric("DRC Post", f"{r.drc_post:.3f}",
               f"{(r.drc_post / r.drc_pre - 1) * 100:+.1f}%" if r.drc_pre else "—")
    st.caption("**Densidad de Requerimiento por Caso** — criterios cubiertos "
               "por caso funcional. La ganancia viene del volumen, no de que "
               "cada caso rinda más.")
with _c2:
    _total = r.total_casos_funcionales_humanos + r.total_casos_normativos
    _e1, _e2 = st.columns(2)
    _e1.metric("Funcionales",
               f"{r.total_casos_funcionales_humanos} "
               f"({r.total_casos_funcionales_humanos / _total * 100:.0f}%)")
    _e2.metric("Cumplimiento normativo",
               f"{r.total_casos_normativos} "
               f"({r.total_casos_normativos / _total * 100:.0f}%)")
    st.caption(f"**{_total} casos históricos.** {r.umbral_hu_gobierno}+ HU con "
               f"el mismo título = normativo. El agente genera **0** "
               f"normativos, así que se lo compara contra los "
               f"{r.total_casos_funcionales_humanos} funcionales.")
    with st.expander("Ver los títulos normativos más repetidos"):
        st.dataframe(
            [{"Verificación": t["titulo"][:95], "Se repite en": f"{t['hu']} HU"}
             for t in r.titulos_gobierno],
            use_container_width=True, hide_index=True)


st.markdown("<div class='section-header'>Detalle HU por HU</div>",
            unsafe_allow_html=True)
_df = pd.DataFrame(r.detalle_por_hu)
st.dataframe(_df, use_container_width=True, hide_index=True)
st.download_button(
    "⬇️ Exportar dataset (CSV) para replicación estadística",
    data=_df.to_csv(index=False).encode("utf-8"),
    file_name=f"prepost_{r.cohorte_clave}_n{r.n_hu}.csv",
    mime="text/csv",
)
st.caption("Una fila por historia, con los dos lados de cada indicador.")


if r.hu_excluidas or r.avisos:


    _n = len(r.avisos) + (1 if r.hu_excluidas else 0)
    with st.expander(f"Salvedades declaradas ({_n})"):
        if r.hu_excluidas:
            st.caption(f"· Excluidas de CRF y TVO por inconsistencia de datos "
                       f"base: {', '.join(r.hu_excluidas)}.")
        for _a in r.avisos:
            st.caption(f"· {_a}")
