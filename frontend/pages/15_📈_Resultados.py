"""
📈 Resultados -- qué cambió en el proceso de pruebas al incorporar el agente.

Tablero de los tres indicadores del proceso, medidos sobre los mismos 60
ciclos de prueba antes y después del agente. Es la pantalla de cabecera de la
app: reemplazó al antiguo "Resumen ejecutivo".

ATENCIÓN -- no mide lo mismo que "Pre-Test / Post-Test", y la diferencia es
deliberada:

| | Pre-Test / Post-Test | Esta pantalla |
|---|---|---|
| Unidad | 61 historias de usuario | 60 ciclos de prueba |
| Estado de defectos | los que el agente habría mitigado (contrafáctico) | corregidos / detectados, medido en los dos periodos |
| Origen | el corpus operativo (CSV del proyecto) | `resultados_documento_60ciclos.csv` |

Las dos lecturas son correctas en su marco y NO dan el mismo número. Quien
compare las dos pantallas sin saberlo va a creer que una está mal.

Declarativa, como el resto de las pantallas de evaluación: no calcula ni un
ratio. Todo --índices, cuartiles, series ordenadas, totales por severidad--
llega resuelto desde `CalcularResultadosDocumento`.

Vocabulario de pantalla: los dos periodos se rotulan "Sin el agente" y "Con el
agente", no con la jerga del método: la pantalla describe la herramienta,
no el diseño experimental con que se la evaluó.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from adapters.tesis.csv_resultados_documento import CsvResultadosDocumento
from application.tesis.calcular_resultados_documento import CalcularResultadosDocumento
from frontend.auth import requerir_sesion
from frontend.comun.estilo import aplicar_estilo_institucional
from frontend.comun.graficos_documento import (
    AZUL,
    ACENTO,
    barras_apiladas,
    barras_comparativas,
    cajas_bigotes,
    curva_cuantiles,
)

st.set_page_config(page_title="Resultados — NEXUS", page_icon="📈", layout="wide")
requerir_sesion()
aplicar_estilo_institucional()

SIN, CON = "Sin el agente", "Con el agente"
_SERIES = [{"nombre": SIN, "color": AZUL}, {"nombre": CON, "color": ACENTO}]

_RAIZ = Path(__file__).resolve().parent.parent.parent
r = CalcularResultadosDocumento(CsvResultadosDocumento(_RAIZ)).ejecutar()

st.markdown(
    "<div class='titulo-banda'><h1>Resultados del proceso de pruebas</h1>"
    f"<p>Los tres indicadores del proceso sobre los mismos "
    f"{r.total_ciclos} ciclos de prueba, antes y después de incorporar el "
    "agente. Cada ciclo se midió de las dos formas, así que la comparación es "
    "sobre el mismo trabajo.</p></div>",
    unsafe_allow_html=True,
)


st.markdown("<div class='seccion'>Los tres indicadores</div>",
            unsafe_allow_html=True)


def _tarjeta(col, nombre, pre, post, det_pre, det_post, dif) -> None:
    """Dibuja. No calcula: la diferencia viene resuelta del caso de uso."""
    with col:
        st.markdown(
            f"<div class='kpi'><div class='nombre'>{nombre}</div>"
            f"<div class='par'><span>{SIN}</span><b>{pre:.2f}%</b></div>"
            f"<div class='det'>{det_pre}</div>"
            f"<div class='par' style='margin-top:12px;'><span>{CON}</span>"
            f"<b>{post:.2f}%</b></div>"
            f"<div class='det'>{det_post}</div>"
            f"<div class='delta'>{dif:+.2f} pp</div></div>",
            unsafe_allow_html=True,
        )


_d = r.defectos
for _col, _t in zip(st.columns(3), (
    (r.ejecuciones.nombre, r.ejecuciones.valor_pre, r.ejecuciones.valor_post,
     f"{r.ejecuciones.numerador_pre} de {r.ejecuciones.denominador_pre} casos ejecutados",
     f"{r.ejecuciones.numerador_post} de {r.ejecuciones.denominador_post} casos ejecutados",
     r.ejecuciones.diferencia_pp),
    ("Estado de defectos", _d.estado_pre, _d.estado_post,
     f"{_d.corregidos_pre} de {_d.detectados_pre} defectos corregidos",
     f"{_d.corregidos_post} de {_d.detectados_post} defectos corregidos",
     _d.diferencia_pp),
    (r.cobertura.nombre, r.cobertura.valor_pre, r.cobertura.valor_post,
     f"{r.cobertura.numerador_pre} de {r.cobertura.denominador_pre} situaciones cubiertas",
     f"{r.cobertura.numerador_post} de {r.cobertura.denominador_post} situaciones cubiertas",
     r.cobertura.diferencia_pp),
)):
    _tarjeta(_col, *_t)


def _bloque_indicador(ind) -> None:
    """Los tres gráficos de un indicador: nivel, distribución y brecha."""
    st.markdown(f"<div class='seccion'>{ind.nombre}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<p class='fuente'>{ind.numerador_rotulo.lower()} sobre "
        f"{ind.denominador_rotulo.lower()}, en {r.total_ciclos} ciclos por "
        f"periodo.</p>",
        unsafe_allow_html=True,
    )
    _c1, _c2 = st.columns([1, 1.25], gap="large")
    with _c1:
        st.markdown("<div class='sub'>Nivel alcanzado</div>", unsafe_allow_html=True)
        st.markdown(
            barras_comparativas(
                [{"etiqueta": SIN, "valores": [ind.valor_pre, None],
                  "nota": f"{ind.numerador_pre} de {ind.denominador_pre}"},
                 {"etiqueta": CON, "valores": [None, ind.valor_post],
                  "nota": f"{ind.numerador_post} de {ind.denominador_post}"}],
                _SERIES,
            ),
            unsafe_allow_html=True,
        )
    with _c2:
        st.markdown(f"<div class='sub'>Cómo se reparte entre los "
                    f"{r.total_ciclos} ciclos</div>", unsafe_allow_html=True)
        st.markdown(
            cajas_bigotes(
                [{"etiqueta": SIN, "color": AZUL, "caja": ind.caja_pre},
                 {"etiqueta": CON, "color": ACENTO, "caja": ind.caja_post}],
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            f"Línea blanca: la mediana. Punto: el promedio. La caja contiene a "
            f"la mitad central de los ciclos y los bigotes llegan al valor más "
            f"extremo que sigue siendo normal; los puntos sueltos son los "
            f"ciclos que se salen. La dispersión entre ciclos bajó de "
            f"{ind.desviacion_pre:.2f} a {ind.desviacion_post:.2f} puntos: no "
            f"solo sube el promedio, el proceso se vuelve más parejo."
        )
    st.markdown("<div class='sub'>Ciclo por ciclo</div>", unsafe_allow_html=True)
    st.markdown(
        curva_cuantiles(
            ind.curva_pre, ind.curva_post, SIN, CON,
            rotulo_x=f"{r.total_ciclos} ciclos por periodo, cada periodo ordenado "
                     f"de menor a mayor — el eje no es una línea de tiempo",
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        "Cada curva ordena los ciclos de su periodo de menor a mayor. Son "
        "ciclos distintos en cada periodo, así que se compara la distribución "
        "(percentil contra percentil), no un ciclo contra otro."
    )


_bloque_indicador(r.ejecuciones)


st.markdown("<div class='seccion'>Estado de defectos</div>", unsafe_allow_html=True)
st.markdown(
    "<p class='fuente'>Defectos corregidos sobre defectos detectados, por "
    "nivel de severidad, de menor a mayor criticidad.</p>",
    unsafe_allow_html=True,
)

_e1, _e2 = st.columns(2, gap="large")
for _col, _titulo, _color, _llave in ((_e1, SIN, AZUL, "pre"), (_e2, CON, ACENTO, "post")):
    with _col:
        st.markdown(f"<div class='sub'>{_titulo}</div>", unsafe_allow_html=True)
        st.markdown(
            barras_apiladas(
                [{"etiqueta": f.severidad,
                  "relleno": getattr(f, f"corregidos_{_llave}"),
                  "resto": getattr(f, f"no_corregidos_{_llave}"),
                  "nota": (f"{getattr(f, f'estado_{_llave}'):.2f}%"
                           if getattr(f, f"estado_{_llave}") is not None else "—")}
                 for f in _d.por_severidad],
                "Corregidos", _color, "No corregidos",
                maximo=_d.maximo_severidad,
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            f"La altura total de cada barra son los defectos detectados en ese "
            f"nivel; el porcentaje de abajo es cuántos se corrigieron. En total, "
            f"{getattr(_d, f'corregidos_{_llave}')} de "
            f"{getattr(_d, f'detectados_{_llave}')} "
            f"({getattr(_d, f'estado_{_llave}'):.2f}%). Las dos columnas usan la "
            f"misma escala, así que la diferencia de altura es diferencia real "
            f"de volumen."
        )

st.markdown("<div class='sub'>Los dos periodos, nivel por nivel</div>",
            unsafe_allow_html=True)
_g1, _g2 = st.columns([1.6, 1], gap="large")
with _g1:
    st.markdown(
        barras_comparativas(
            [{"etiqueta": f.severidad, "valores": [f.estado_pre, f.estado_post],
              "nota": f"{f.detectados_pre} vs {f.detectados_post} detectados"}
             for f in _d.por_severidad],
            _SERIES,
        ),
        unsafe_allow_html=True,
    )
    st.caption("“—” marca un nivel que no registró defectos en ese periodo: no "
               "hubo nada que corregir, así que el porcentaje no existe y no se "
               "dibuja como 0%.")
with _g2:
    st.markdown("<div class='sub'>Volumen total</div>", unsafe_allow_html=True)
    st.markdown(
        barras_apiladas(
            [{"etiqueta": SIN, "relleno": _d.corregidos_pre,
              "resto": _d.no_corregidos_pre,
              "nota": f"{_d.estado_pre:.2f}% corregidos"},
             {"etiqueta": CON, "relleno": _d.corregidos_post,
              "resto": _d.no_corregidos_post,
              "nota": f"{_d.estado_post:.2f}% corregidos"}],
            "Corregidos", ACENTO, "No corregidos",
            maximo=_d.maximo_detectados,
        ),
        unsafe_allow_html=True,
    )

st.markdown(
    f"<div class='nota'><b>Los ciclos sin defectos no entran en el promedio.</b> "
    f"De los {_d.total_ciclos} ciclos, {_d.ciclos_con_defectos_pre} registraron "
    f"defectos sin el agente y {_d.ciclos_con_defectos_post} con el agente. En "
    f"los {_d.ciclos_sin_defectos_pre} y {_d.ciclos_sin_defectos_post} "
    f"restantes no hubo defecto que corregir, así que el porcentaje no se "
    f"define: no se cuentan como 0% ni como 100%. El volumen detectado bajó de "
    f"<b>{_d.detectados_pre}</b> a <b>{_d.detectados_post}</b> defectos.</div>",
    unsafe_allow_html=True,
)

_bloque_indicador(r.cobertura)


st.markdown("<div class='seccion'>Detalle por ciclo</div>", unsafe_allow_html=True)
st.markdown(
    "<p class='fuente'>Los mismos datos de todos los gráficos de arriba, ciclo "
    "por ciclo: ningún valor de esta pantalla está disponible solo al pasar el "
    "mouse.</p>",
    unsafe_allow_html=True,
)
_df = pd.DataFrame(r.detalle_por_ciclo)
st.dataframe(_df, use_container_width=True, hide_index=True, height=420)
st.download_button(
    "⬇️ Descargar el detalle (CSV)",
    data=_df.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"resultados_{r.total_ciclos}_ciclos.csv",
    mime="text/csv",
)
