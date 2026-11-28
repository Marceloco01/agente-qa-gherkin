"""
Gráficos en SVG inline, sin dependencias nuevas.

El proyecto no tiene plotly, altair ni matplotlib, y no se los agrega por dos
gráficos: `5_🎯_Seguimiento.py` ya dice en su propio código que evita esa
dependencia a propósito, y las barras del Dashboard están hechas a mano por lo
mismo. Acá se sigue esa línea con SVG, que además da control exacto sobre las
especificaciones de marca (topes redondeados de 4px anclados a la línea base,
separación de 2px entre rellenos, etiquetas directas selectivas).

Esto es capa de PRESENTACIÓN: convierte números ya calculados en geometría. No
calcula ningún indicador -- los valores llegan resueltos desde el caso de uso.
Vive en un módulo aparte y no en la página para que la regla "cero cálculos en
la vista" se pueda verificar leyendo la página, sin tener que distinguir a ojo
una cuenta de negocio de un `x * ancho / total`.

Paleta: validada con el validador del sistema de diseño (categorical, modo
claro) -- #2a78d6 / #eb6834, ΔE CVD 24.7 y visión normal 33.6, ambos por
encima del piso. Semántica constante en toda la fase: AZUL es el trabajo
funcional y lo que aporta NEXUS; NARANJA es la sobrecarga normativa y el
proceso manual previo.
"""

from __future__ import annotations

import html
from math import cos, pi, sin

AZUL = "#2a78d6"
NARANJA = "#eb6834"
TINTA = "#0F172A"
TINTA_SUAVE = "#64748B"
SUPERFICIE = "#FFFFFF"
REJILLA = "#E2E8F0"


def _t(texto: str) -> str:
    return html.escape(str(texto), quote=True)


def donut(segmentos: list[dict], titulo: str = "", subtitulo: str = "") -> str:
    """
    Anillo de proporciones. `segmentos`: [{"etiqueta", "valor", "color"}].

    Los arcos se separan con un anillo de superficie de 2px en vez de pegarse:
    dos rellenos que se tocan se leen como uno solo, sobre todo impresos o en
    visión con deficiencia de color.
    """
    total = sum(s["valor"] for s in segmentos) or 1
    cx = cy = 96
    radio, grosor = 78, 30
    partes, leyenda = [], []
    angulo = -pi / 2
    for s in segmentos:
        frac = s["valor"] / total
        barrido = frac * 2 * pi
        fin = angulo + barrido
        largo = 1 if barrido > pi else 0
        x1, y1 = cx + radio * cos(angulo), cy + radio * sin(angulo)
        x2, y2 = cx + radio * cos(fin), cy + radio * sin(fin)
        partes.append(
            f'<path d="M {x1:.2f} {y1:.2f} A {radio} {radio} 0 {largo} 1 '
            f'{x2:.2f} {y2:.2f}" fill="none" stroke="{s["color"]}" '
            f'stroke-width="{grosor}" stroke-linecap="butt">'
            f'<title>{_t(s["etiqueta"])}: {s["valor"]} ({frac * 100:.0f}%)</title></path>'
        )

        partes.append(
            f'<line x1="{cx}" y1="{cy}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{SUPERFICIE}" stroke-width="2"/>'
        )


        angulo = fin
        leyenda.append(
            f'<div style="display:flex;align-items:center;gap:7px;margin:5px 0;">'
            f'<span style="width:11px;height:11px;border-radius:2px;'
            f'background:{s["color"]};display:inline-block;flex:none;"></span>'
            f'<span style="font-size:12.5px;color:{TINTA};">'
            f'<b style="font-variant-numeric:tabular-nums;">{s["valor"]}</b> '
            f'({frac * 100:.0f}%) &middot; {_t(s["etiqueta"])}</span></div>'
        )
    centro = (
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="26" '
        f'font-weight="700" fill="{TINTA}">{total}</text>'
        f'<text x="{cx}" y="{cy + 15}" text-anchor="middle" font-size="10.5" '
        f'fill="{TINTA_SUAVE}">casos</text>'
    )
    enc = (f'<div style="font-size:12.5px;font-weight:700;color:{TINTA};">'
           f'{_t(titulo)}</div>'
           f'<div style="font-size:11px;color:{TINTA_SUAVE};margin-bottom:6px;">'
           f'{_t(subtitulo)}</div>') if titulo else ""


    return (
        f'{enc}<div style="display:flex;align-items:center;gap:20px;'
        f'flex-wrap:wrap;">'
        f'<svg viewBox="0 0 192 192" width="176" height="176" '
        f'style="flex:0 0 auto;" role="img" '
        f'aria-label="{_t(titulo)}">{"".join(partes)}{centro}</svg>'
        f'<div style="flex:1 1 180px;min-width:180px;">'
        f'{"".join(leyenda)}</div></div>'
    )


def barras_agrupadas(
    grupos: list[dict],
    series: list[dict],
    maximo: float = 100.0,
    unidad: str = "%",
) -> str:
    """
    Barras agrupadas con UNA sola escala.

    `grupos`: [{"etiqueta", "valores": [v_serie0, v_serie1], "nota"}]
    `series`: [{"nombre", "color"}]

    Una sola escala a propósito: mezclar porcentajes con conteos en un mismo
    eje --o peor, poner dos ejes-- es el error más común de los tableros y hace
    que dos alturas iguales signifiquen cosas distintas. Si hay dos unidades,
    son dos gráficos.
    """

    fmt = ".1f" if unidad == "%" else ".0f"
    ancho_barra, sep_serie, sep_grupo = 30, 4, 46
    alto, base_y, margen_izq = 200, 168, 44
    ancho_grupo = len(series) * ancho_barra + (len(series) - 1) * sep_serie
    total_ancho = margen_izq + len(grupos) * (ancho_grupo + sep_grupo) + 12

    piezas = []

    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = base_y - frac * (base_y - 24)
        piezas.append(
            f'<line x1="{margen_izq - 8}" y1="{y:.1f}" x2="{total_ancho - 8}" '
            f'y2="{y:.1f}" stroke="{REJILLA}" stroke-width="1"/>'
            f'<text x="{margen_izq - 12}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'font-size="9.5" fill="{TINTA_SUAVE}">{frac * maximo:.0f}{unidad}</text>'
        )
    x = margen_izq
    for g in grupos:
        for i, (valor, serie) in enumerate(zip(g["valores"], series)):
            bx = x + i * (ancho_barra + sep_serie)
            if valor <= 0:


                piezas.append(
                    f'<rect x="{bx}" y="{base_y - 3}" width="{ancho_barra}" '
                    f'height="3" rx="1.5" fill="{serie["color"]}">'
                    f'<title>{_t(g["etiqueta"])} · {_t(serie["nombre"])}: '
                    f'{valor:{fmt}}{unidad}</title></rect>'
                    f'<text x="{bx + ancho_barra / 2:.1f}" y="{base_y - 8}" '
                    f'text-anchor="middle" font-size="10" font-weight="700" '
                    f'fill="{serie["color"]}">{valor:{fmt}}</text>'
                )
                continue
            h = valor / maximo * (base_y - 24)
            piezas.append(
                f'<rect x="{bx}" y="{base_y - h:.1f}" width="{ancho_barra}" '
                f'height="{h:.1f}" rx="4" fill="{serie["color"]}" '
                f'stroke="{SUPERFICIE}" stroke-width="2">'
                f'<title>{_t(g["etiqueta"])} · {_t(serie["nombre"])}: '
                f'{valor:{fmt}}{unidad}</title></rect>'

                f'<text x="{bx + ancho_barra / 2:.1f}" y="{base_y - h - 6:.1f}" '
                f'text-anchor="middle" font-size="10.5" font-weight="700" '
                f'fill="{TINTA}">{valor:{fmt}}</text>'
            )
        piezas.append(
            f'<text x="{x + ancho_grupo / 2:.1f}" y="{base_y + 15}" '
            f'text-anchor="middle" font-size="11" font-weight="700" '
            f'fill="{TINTA}">{_t(g["etiqueta"])}</text>'
        )
        if g.get("nota"):
            piezas.append(
                f'<text x="{x + ancho_grupo / 2:.1f}" y="{base_y + 28}" '
                f'text-anchor="middle" font-size="9.5" fill="{TINTA_SUAVE}">'
                f'{_t(g["nota"])}</text>'
            )
        x += ancho_grupo + sep_grupo
    piezas.append(
        f'<line x1="{margen_izq - 8}" y1="{base_y}" x2="{total_ancho - 8}" '
        f'y2="{base_y}" stroke="{TINTA_SUAVE}" stroke-width="1"/>'
    )
    leyenda = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'margin-right:16px;font-size:12px;color:{TINTA};">'
        f'<span style="width:11px;height:11px;border-radius:2px;'
        f'background:{s["color"]};display:inline-block;"></span>'
        f'{_t(s["nombre"])}</span>' for s in series
    )


    escala = 1.5
    return (
        f'<div style="margin-bottom:8px;">{leyenda}</div>'
        f'<svg viewBox="0 0 {total_ancho} {alto + 34}" '
        f'width="{total_ancho * escala:.0f}" height="{(alto + 34) * escala:.0f}" '
        f'style="max-width:100%;display:block;" role="img">'
        f'{"".join(piezas)}</svg>'
    )


def barra_apilada_100(segmentos: list[dict], alto: int = 46) -> str:
    """
    Barra horizontal 100%: cómo se reparte un total entre categorías.

    `segmentos`: [{"etiqueta", "valor", "color"}].

    Se separan con un hueco de 2px de superficie en vez de pegarse: dos
    rellenos que se tocan se leen como uno solo. La etiqueta va DENTRO del
    segmento solo si entra --debajo del 7% el texto se sale y pisa al vecino,
    así que en ese caso va afuera, con una guía--. Eso, más la leyenda, es el
    apoyo que el validador de paleta exige para el color con contraste bajo.
    """
    total = sum(s["valor"] for s in segmentos) or 1
    ancho = 1000.0
    piezas, leyenda, fuera = [], [], []
    x = 0.0
    for s in segmentos:
        frac = s["valor"] / total
        w = frac * ancho
        piezas.append(
            f'<rect x="{x:.2f}" y="0" width="{max(0.0, w - 2):.2f}" height="{alto}" '
            f'rx="3" fill="{s["color"]}">'
            f'<title>{_t(s["etiqueta"])}: {s["valor"]} ({frac * 100:.1f}%)</title></rect>'
        )
        if frac >= 0.07:
            piezas.append(
                f'<text x="{x + w / 2 - 1:.2f}" y="{alto / 2 + 1:.1f}" '
                f'text-anchor="middle" dominant-baseline="middle" font-size="13" '
                f'font-weight="800" fill="#FFFFFF">{frac * 100:.1f}%</text>'
            )
        else:
            fuera.append((x + w / 2, frac, s["color"]))
        leyenda.append(
            f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'margin:0 16px 6px 0;font-size:12px;color:{TINTA};">'
            f'<span style="width:11px;height:11px;border-radius:2px;'
            f'background:{s["color"]};display:inline-block;"></span>'
            f'<b style="font-variant-numeric:tabular-nums;">{s["valor"]}</b> '
            f'({frac * 100:.1f}%) {_t(s["etiqueta"])}</span>'
        )
        x += w


    _SEPARACION_MINIMA = 62.0
    partes_fuera, ultimo_x, renglon = [], None, 0
    for cx, frac, color in fuera:
        if ultimo_x is not None and cx - ultimo_x < _SEPARACION_MINIMA:
            renglon = 1 - renglon
        else:
            renglon = 0
        dy = renglon * 15
        partes_fuera.append(
            f'<line x1="{cx:.1f}" y1="{alto}" x2="{cx:.1f}" y2="{alto + 9 + dy}" '
            f'stroke="{color}" stroke-width="1.5"/>'
            f'<text x="{cx:.1f}" y="{alto + 21 + dy}" text-anchor="middle" '
            f'font-size="11" font-weight="700" fill="{color}">{frac * 100:.1f}%</text>'
        )
        ultimo_x = cx
    alto_total = alto + (41 if renglon or len(fuera) > 1 else 26 if fuera else 2)
    return (
        f'<div style="margin-bottom:9px;">{"".join(leyenda)}</div>'
        f'<svg viewBox="0 0 {ancho} {alto_total}" width="100%" '
        f'height="{alto_total}" preserveAspectRatio="none" '
        f'role="img">{"".join(piezas)}{"".join(partes_fuera)}</svg>'
    )


def barras_horizontales(filas: list[dict], color: str = AZUL) -> str:
    """
    Barras horizontales: un valor por categoría, con la etiqueta al final.

    Horizontal y no vertical porque las categorías acá son frases --motivos de
    rechazo-- y rotar texto para que entre bajo una barra vertical lo vuelve
    ilegible.
    """
    maximo = max((f["valor"] for f in filas), default=1) or 1
    alto_fila, sep = 26, 8
    ancho_etiqueta, ancho_barra = 260, 520
    total_alto = len(filas) * (alto_fila + sep)
    piezas = []
    for i, f in enumerate(filas):
        y = i * (alto_fila + sep)
        w = max(3.0, f["valor"] / maximo * ancho_barra)
        piezas.append(
            f'<text x="{ancho_etiqueta - 10}" y="{y + alto_fila / 2 + 1:.1f}" '
            f'text-anchor="end" dominant-baseline="middle" font-size="12" '
            f'fill="{TINTA}">{_t(f["etiqueta"])}</text>'
            f'<rect x="{ancho_etiqueta}" y="{y}" width="{w:.1f}" '
            f'height="{alto_fila}" rx="3" fill="{color}">'
            f'<title>{_t(f["etiqueta"])}: {f["valor"]}</title></rect>'
            f'<text x="{ancho_etiqueta + w + 8:.1f}" y="{y + alto_fila / 2 + 1:.1f}" '
            f'dominant-baseline="middle" font-size="12" font-weight="700" '
            f'fill="{TINTA}">{f["valor"]}'
            + (f'<tspan fill="{TINTA_SUAVE}" font-weight="400"> · {f["nota"]}</tspan>'
               if f.get("nota") else "")
            + '</text>'
        )
    return (
        f'<svg viewBox="0 0 {ancho_etiqueta + ancho_barra + 110} {total_alto}" '
        f'width="100%" height="{total_alto}" role="img">{"".join(piezas)}</svg>'
    )
