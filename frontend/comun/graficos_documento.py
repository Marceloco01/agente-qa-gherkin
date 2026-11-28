"""
Gráficos del tablero de Resultados -- SVG inline, tipografía grande y paleta
institucional.

Por qué es un módulo aparte y no se tocó `graficos.py`: esas funciones las
consumen el Resumen ejecutivo y Pre-Test / Post-Test, que tienen sus propios
tamaños y su propia semántica de color (azul = NEXUS, naranja = proceso
manual). Cambiarlas para esta pantalla habría repintado dos pantallas que
nadie pidió cambiar. Acá viven las formas nuevas (cajas, curvas de cuantiles, barras
apiladas) con la escala tipográfica definida en la revisión de diseño.

PALETA en colores neutros:

    #334155 gris pizarra  ·  #1D6FA3 azul  ·  #CBD5E1 gris claro (remanente)
    Además del tono, se distinguen por luminosidad (L* 27, 45 y 85), así que
    siguen separándose con cualquier tipo de daltonismo.

El blanco sobre el gris pizarra da 10.35:1, por encima del mínimo AA para
texto (4.5:1), así que las bandas de sección llevan texto blanco sin reservas.

SEMÁNTICA FIJA en toda la pantalla, y no se negocia por gráfico:
    ACENTO   = el proceso CON el agente
    AZUL     = el proceso SIN el agente, manual
    GRIS     = el resto de un total (defectos no corregidos), nunca una serie

Es capa de PRESENTACIÓN: convierte números ya resueltos en geometría. No
calcula ningún indicador; los cuartiles, los totales y las series ordenadas
llegan hechos desde `CalcularResultadosDocumento`.
"""

from __future__ import annotations

import html

ACENTO = "#334155"
ACENTO_OSCURO = "#1E293B"
AZUL = "#1D6FA3"
GRIS_RESTO = "#CBD5E1"
BLANCO = "#FFFFFF"
TINTA = "#14181F"
TINTA_SUAVE = "#5B6472"
SUPERFICIE = "#FFFFFF"
REJILLA = "#E2E8F0"


T_EJE = 15
T_ETIQUETA = 17
T_NOTA = 14
T_VALOR = 17
T_LEYENDA = 16


def _t(texto: str) -> str:
    return html.escape(str(texto), quote=True)


def leyenda(series: list[dict]) -> str:
    """Leyenda horizontal. Siempre presente: dos series nunca se distinguen
    solo por color."""
    return '<div style="margin:0 0 10px;display:flex;flex-wrap:wrap;gap:22px;">' + "".join(
        f'<span style="display:inline-flex;align-items:center;gap:9px;'
        f'font-size:{T_LEYENDA}px;color:{TINTA};font-weight:600;">'
        f'<span style="width:16px;height:16px;border-radius:3px;'
        f'background:{s["color"]};display:inline-block;flex:none;"></span>'
        f'{_t(s["nombre"])}</span>' for s in series
    ) + "</div>"


def _rejilla(x0: float, x1: float, base_y: float, tope_y: float,
             maximo: float, unidad: str, pasos=(0, 0.25, 0.5, 0.75, 1.0)) -> list[str]:
    """Rejilla recesiva con su eje rotulado. Línea sólida, nunca punteada:
    el punteado se lee como umbral o proyección, y esto es solo una guía."""
    piezas = []
    for frac in pasos:
        y = base_y - frac * (base_y - tope_y)
        piezas.append(
            f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" '
            f'stroke="{REJILLA}" stroke-width="1"/>'
            f'<text x="{x0 - 10}" y="{y + 5:.1f}" text-anchor="end" '
            f'font-size="{T_EJE}" fill="{TINTA_SUAVE}" '
            f'style="font-variant-numeric:tabular-nums;">'
            f'{frac * maximo:.0f}{unidad}</text>'
        )
    return piezas


def _svg(ancho: float, alto: float, piezas: list[str], etiqueta: str,
         escala: float = 1.0) -> str:
    """
    Tamaño natural, no fluido.

    Un SVG estirado al 100% del contenedor escala su propia tipografía: el
    mismo gráfico en una columna ancha y en una angosta renderiza las
    etiquetas a tamaños distintos. Con un ancho natural y `max-width:100%`, la
    letra mide lo mismo en toda la pantalla, que es lo que hace que dos
    gráficos puestos al lado se lean como un par.
    """
    return (
        f'<svg viewBox="0 0 {ancho:.0f} {alto:.0f}" '
        f'width="{ancho * escala:.0f}" height="{alto * escala:.0f}" '
        f'style="max-width:100%;height:auto;display:block;" role="img" '
        f'aria-label="{_t(etiqueta)}">{"".join(piezas)}</svg>'
    )


def barras_comparativas(grupos: list[dict], series: list[dict],
                        maximo: float = 100.0, unidad: str = "%",
                        decimales: int = 2) -> str:
    """
    Barras agrupadas con UNA sola escala.

    `grupos`: [{"etiqueta", "valores": [v0, v1], "nota"}]
    `series`: [{"nombre", "color"}]

    Una sola escala a propósito. Mezclar porcentajes con conteos en un eje --o
    peor, poner dos ejes-- hace que dos alturas iguales signifiquen cosas
    distintas. Si hay dos unidades, son dos gráficos.
    """
    fmt = f".{decimales}f"
    ancho_barra, sep_serie, sep_grupo = 74, 10, 72
    margen_izq, tope_y, base_y = 74, 46, 300
    ancho_grupo = len(series) * ancho_barra + (len(series) - 1) * sep_serie
    total = margen_izq + len(grupos) * (ancho_grupo + sep_grupo) + 20

    piezas = _rejilla(margen_izq - 14, total - 14, base_y, tope_y, maximo, unidad)
    x = margen_izq
    for g in grupos:
        for i, (valor, serie) in enumerate(zip(g["valores"], series)):
            bx = x + i * (ancho_barra + sep_serie)
            if valor is None:


                piezas.append(
                    f'<text x="{bx + ancho_barra / 2:.1f}" y="{base_y - 13}" '
                    f'text-anchor="middle" font-size="{T_VALOR}" '
                    f'font-weight="700" fill="{TINTA_SUAVE}">—</text>'
                    f'<rect x="{bx}" y="{base_y - 4}" width="{ancho_barra}" '
                    f'height="4" rx="2" fill="{REJILLA}">'
                    f'<title>{_t(g["etiqueta"])} · {_t(serie["nombre"])}: '
                    f'sin defectos registrados</title></rect>'
                )
                continue
            etq = f'{_t(g["etiqueta"])} · {_t(serie["nombre"])}: {valor:{fmt}}{unidad}'
            if valor <= 0:


                piezas.append(
                    f'<rect x="{bx}" y="{base_y - 4}" width="{ancho_barra}" '
                    f'height="4" rx="2" fill="{serie["color"]}">'
                    f'<title>{etq}</title></rect>'
                    f'<text x="{bx + ancho_barra / 2:.1f}" y="{base_y - 13}" '
                    f'text-anchor="middle" font-size="{T_VALOR}" font-weight="700" '
                    f'fill="{serie["color"]}">{valor:{fmt}}</text>'
                )
                continue
            h = valor / maximo * (base_y - tope_y)
            piezas.append(
                f'<rect x="{bx}" y="{base_y - h:.1f}" width="{ancho_barra}" '
                f'height="{h:.1f}" rx="5" fill="{serie["color"]}" '
                f'stroke="{SUPERFICIE}" stroke-width="2">'
                f'<title>{etq}</title></rect>'
                f'<text x="{bx + ancho_barra / 2:.1f}" y="{base_y - h - 11:.1f}" '
                f'text-anchor="middle" font-size="{T_VALOR}" font-weight="700" '
                f'fill="{TINTA}" style="font-variant-numeric:tabular-nums;">'
                f'{valor:{fmt}}{unidad}</text>'
            )
        piezas.append(
            f'<text x="{x + ancho_grupo / 2:.1f}" y="{base_y + 26}" '
            f'text-anchor="middle" font-size="{T_ETIQUETA}" font-weight="700" '
            f'fill="{TINTA}">{_t(g["etiqueta"])}</text>'
        )
        if g.get("nota"):
            piezas.append(
                f'<text x="{x + ancho_grupo / 2:.1f}" y="{base_y + 48}" '
                f'text-anchor="middle" font-size="{T_NOTA}" fill="{TINTA_SUAVE}">'
                f'{_t(g["nota"])}</text>'
            )
        x += ancho_grupo + sep_grupo
    piezas.append(
        f'<line x1="{margen_izq - 14}" y1="{base_y}" x2="{total - 14}" '
        f'y2="{base_y}" stroke="{TINTA_SUAVE}" stroke-width="1.5"/>'
    )


    return leyenda(series) + _svg(total, base_y + 60, piezas, "Barras comparativas")


def cajas_bigotes(cajas: list[dict], maximo: float = 100.0,
                  unidad: str = "%") -> str:
    """
    Diagrama de cajas (Tukey). `cajas`: [{"etiqueta","color","caja"}].

    `caja` es un objeto con minimo/q1/mediana/q3/maximo/media/atipicos/n, ya
    calculado en el caso de uso. Los bigotes llegan al dato más extremo dentro
    de 1,5 RIC y lo de afuera son puntos: estirar el bigote hasta el mínimo
    absoluto escondería justamente los ciclos que hay que mirar.

    Se rotula solo la mediana. Poner los cinco números al lado de cada caja es
    la versión en texto de la tabla, y la tabla ya está abajo.
    """
    ancho_caja, sep = 96, 128
    margen_izq, tope_y, base_y = 74, 42, 320
    total = margen_izq + len(cajas) * ancho_caja + (len(cajas) - 1) * sep + 90

    def y(v: float) -> float:
        return base_y - (v / maximo) * (base_y - tope_y)

    piezas = _rejilla(margen_izq - 14, total - 14, base_y, tope_y, maximo, unidad)
    x = margen_izq
    for item in cajas:
        c, color = item["caja"], item["color"]
        cx = x + ancho_caja / 2
        y_q1, y_q3, y_med = y(c.q1), y(c.q3), y(c.mediana)


        ALTO_MINIMO = 10.0
        degenerada = (y_q1 - y_q3) < ALTO_MINIMO
        alto = max(ALTO_MINIMO, y_q1 - y_q3)
        if degenerada:
            y_q3 = y_med - alto / 2

        piezas.append(
            f'<line x1="{cx}" y1="{y(c.maximo):.1f}" x2="{cx}" y2="{y_q3:.1f}" '
            f'stroke="{color}" stroke-width="2"/>'
            f'<line x1="{cx}" y1="{y_q1:.1f}" x2="{cx}" y2="{y(c.minimo):.1f}" '
            f'stroke="{color}" stroke-width="2"/>'
            f'<line x1="{cx - 26}" y1="{y(c.maximo):.1f}" x2="{cx + 26}" '
            f'y2="{y(c.maximo):.1f}" stroke="{color}" stroke-width="2"/>'
            f'<line x1="{cx - 26}" y1="{y(c.minimo):.1f}" x2="{cx + 26}" '
            f'y2="{y(c.minimo):.1f}" stroke="{color}" stroke-width="2"/>'
        )
        piezas.append(
            f'<rect x="{x}" y="{y_q3:.1f}" width="{ancho_caja}" height="{alto:.1f}" '
            f'rx="4" fill="{color}" stroke="{SUPERFICIE}" stroke-width="2">'
            f'<title>{_t(item["etiqueta"])} · n = {c.n} · '
            f'mín {c.minimo:.1f}{unidad} · Q1 {c.q1:.1f}{unidad} · '
            f'mediana {c.mediana:.1f}{unidad} · Q3 {c.q3:.1f}{unidad} · '
            f'máx {c.maximo:.1f}{unidad}</title></rect>'
        )


        piezas.append(
            "" if degenerada else
            f'<line x1="{x}" y1="{y_med:.1f}" x2="{x + ancho_caja}" '
            f'y2="{y_med:.1f}" stroke="{BLANCO}" stroke-width="3.5"/>'
        )
        piezas.append(


            f'<circle cx="{cx}" cy="{y(c.media):.1f}" r="5.5" fill="{BLANCO}" '
            f'stroke="{color}" stroke-width="2.5"><title>Media '
            f'{c.media:.2f}{unidad}</title></circle>'
        )
        for a in c.atipicos:
            piezas.append(
                f'<circle cx="{cx}" cy="{y(a):.1f}" r="5" fill="{color}" '
                f'stroke="{SUPERFICIE}" stroke-width="2" opacity="0.85">'
                f'<title>Atípico: {a:.1f}{unidad}</title></circle>'
            )
        piezas.append(
            f'<text x="{x + ancho_caja + 12}" y="{y_med + 6:.1f}" '
            f'font-size="{T_VALOR}" font-weight="700" fill="{TINTA}" '
            f'style="font-variant-numeric:tabular-nums;">'
            f'{c.mediana:.1f}{unidad}</text>'
            f'<text x="{cx}" y="{base_y + 26}" text-anchor="middle" '
            f'font-size="{T_ETIQUETA}" font-weight="700" fill="{TINTA}">'
            f'{_t(item["etiqueta"])}</text>'
            f'<text x="{cx}" y="{base_y + 48}" text-anchor="middle" '
            f'font-size="{T_NOTA}" fill="{TINTA_SUAVE}">n = {c.n} ciclos</text>'
        )
        x += ancho_caja + sep
    piezas.append(
        f'<line x1="{margen_izq - 14}" y1="{base_y}" x2="{total - 14}" '
        f'y2="{base_y}" stroke="{TINTA_SUAVE}" stroke-width="1.5"/>'
    )
    leyendas = [{"nombre": c["etiqueta"], "color": c["color"]} for c in cajas]
    return leyenda(leyendas) + _svg(total, base_y + 60, piezas, "Diagrama de cajas")


def curva_cuantiles(serie_a: tuple[float, ...], serie_b: tuple[float, ...],
                  nombre_a: str, nombre_b: str,
                  color_a: str = AZUL, color_b: str = ACENTO,
                  maximo: float = 100.0, unidad: str = "%",
                  rotulo_x: str = "") -> str:
    """
    Dos curvas de cuantiles: cada periodo con sus ciclos ordenados de menor a
    mayor valor.

    OJO con lo que este gráfico NO es: el eje X **no es el tiempo** y la
    posición i de una curva **no es el mismo ciclo** que la posición i de la
    otra. Los periodos tienen ciclos distintos (muestras independientes). Lo
    que sí muestra es en qué parte de la distribución se separan los dos
    procesos: por ejemplo, cuántos ciclos quedan por debajo del 100 %.

    Sin marcador en cada punto: son 60 por serie y sesenta discos son ruido.
    El valor de cada punto se consulta al pasar el mouse (hay un área
    transparente por ciclo) y está entero en la tabla de abajo.
    """
    margen_izq, margen_der, tope_y, base_y = 74, 26, 42, 300
    ancho_util = 1060
    total = margen_izq + ancho_util + margen_der
    n = max(len(serie_a), len(serie_b))
    paso = ancho_util / max(1, n - 1)

    def px(i: int) -> float:
        return margen_izq + i * paso

    def py(v: float) -> float:
        return base_y - (v / maximo) * (base_y - tope_y)

    piezas = _rejilla(margen_izq - 14, total - margen_der, base_y, tope_y,
                      maximo, unidad)


    if len(serie_a) == len(serie_b) and serie_a:
        arriba = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(serie_b))
        abajo = " ".join(
            f"{px(i):.1f},{py(v):.1f}"
            for i, v in reversed(list(enumerate(serie_a)))
        )
        piezas.append(
            f'<polygon points="{arriba} {abajo}" fill="{color_b}" opacity="0.10"/>'
        )
    for serie, color in ((serie_a, color_a), (serie_b, color_b)):
        if not serie:
            continue
        puntos = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(serie))
        piezas.append(
            f'<polyline points="{puntos}" fill="none" stroke="{color}" '
            f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
        )


    for i in range(n):
        va = serie_a[i] if i < len(serie_a) else None
        vb = serie_b[i] if i < len(serie_b) else None
        detalle = " · ".join(
            f"{nom}: {val:.1f}{unidad}"
            for nom, val in ((nombre_a, va), (nombre_b, vb)) if val is not None
        )
        piezas.append(
            f'<rect x="{px(i) - paso / 2:.1f}" y="{tope_y}" '
            f'width="{paso:.1f}" height="{base_y - tope_y}" fill="transparent">'
            f'<title>Percentil {100 * (i + 1) / n:.0f} · {detalle}</title></rect>'
        )
    piezas.append(
        f'<line x1="{margen_izq - 14}" y1="{base_y}" x2="{total - margen_der}" '
        f'y2="{base_y}" stroke="{TINTA_SUAVE}" stroke-width="1.5"/>'
        f'<text x="{margen_izq}" y="{base_y + 26}" font-size="{T_NOTA}" '
        f'fill="{TINTA_SUAVE}">1</text>'
        f'<text x="{total - margen_der}" y="{base_y + 26}" text-anchor="end" '
        f'font-size="{T_NOTA}" fill="{TINTA_SUAVE}">{n}</text>'
        f'<text x="{margen_izq + ancho_util / 2:.0f}" y="{base_y + 48}" '
        f'text-anchor="middle" font-size="{T_NOTA}" fill="{TINTA_SUAVE}">'
        f'{_t(rotulo_x)}</text>'
    )
    series = [{"nombre": nombre_a, "color": color_a},
              {"nombre": nombre_b, "color": color_b}]
    return leyenda(series) + _svg(total, base_y + 60, piezas, "Curvas de cuantiles")


def barras_apiladas(grupos: list[dict], nombre_relleno: str,
                    color_relleno: str, nombre_resto: str,
                    maximo: int = 30) -> str:
    """
    Barras apiladas: de cada total, cuánto se cubrió y cuánto quedó.

    `grupos`: [{"etiqueta", "relleno": int, "resto": int, "nota"}]

    El gris NO es una tercera categoría: es el remanente del total. Por eso no
    entra en la paleta categórica ni se valida contra ella -- es la forma
    estándar de "lo destacado y el resto", y evita gastar un segundo color
    saturado en algo que no es una identidad.

    Los dos tramos se separan con 2px de superficie: dos rellenos que se tocan
    se leen como uno solo, sobre todo impresos o en visión con deficiencia de
    color. La etiqueta va DENTRO del tramo solo si entra.
    """
    ancho_barra, sep = 86, 54
    margen_izq, tope_y, base_y = 74, 46, 300
    total_ancho = margen_izq + len(grupos) * (ancho_barra + sep) + 20
    piezas = _rejilla(margen_izq - 14, total_ancho - 14, base_y, tope_y,
                      float(maximo), "")

    def alto_de(v: int) -> float:
        return v / maximo * (base_y - tope_y) if maximo else 0.0

    x = margen_izq
    for g in grupos:
        relleno, resto = int(g["relleno"]), int(g["resto"])
        total = relleno + resto
        if total <= 0:


            piezas.append(
                f'<line x1="{x}" y1="{base_y}" x2="{x + ancho_barra}" '
                f'y2="{base_y}" stroke="{TINTA_SUAVE}" stroke-width="3"/>'
                f'<text x="{x + ancho_barra / 2:.1f}" y="{base_y - 14}" '
                f'text-anchor="middle" font-size="{T_VALOR}" font-weight="700" '
                f'fill="{TINTA_SUAVE}">—</text>'
            )
        else:
            h_rel, h_res = alto_de(relleno), alto_de(resto)
            y_res = base_y - h_rel - h_res
            if resto:
                piezas.append(
                    f'<rect x="{x}" y="{y_res:.1f}" width="{ancho_barra}" '
                    f'height="{max(0.0, h_res - 2):.1f}" rx="4" fill="{GRIS_RESTO}">'
                    f'<title>{_t(g["etiqueta"])} · {_t(nombre_resto)}: {resto}'
                    f'</title></rect>'
                )
                if h_res >= 30:
                    piezas.append(
                        f'<text x="{x + ancho_barra / 2:.1f}" '
                        f'y="{y_res + h_res / 2 + 5:.1f}" text-anchor="middle" '
                        f'font-size="{T_VALOR}" font-weight="700" fill="{TINTA}">'
                        f'{resto}</text>'
                    )
            if relleno:
                piezas.append(
                    f'<rect x="{x}" y="{base_y - h_rel:.1f}" width="{ancho_barra}" '
                    f'height="{h_rel:.1f}" rx="4" fill="{color_relleno}">'
                    f'<title>{_t(g["etiqueta"])} · {_t(nombre_relleno)}: {relleno}'
                    f'</title></rect>'
                )
                if h_rel >= 30:
                    piezas.append(
                        f'<text x="{x + ancho_barra / 2:.1f}" '
                        f'y="{base_y - h_rel / 2 + 6:.1f}" text-anchor="middle" '
                        f'font-size="{T_VALOR}" font-weight="700" fill="{BLANCO}">'
                        f'{relleno}</text>'
                    )
            piezas.append(
                f'<text x="{x + ancho_barra / 2:.1f}" '
                f'y="{base_y - h_rel - h_res - 11:.1f}" text-anchor="middle" '
                f'font-size="{T_NOTA}" font-weight="700" fill="{TINTA_SUAVE}" '
                f'style="font-variant-numeric:tabular-nums;">{total}</text>'
            )
        piezas.append(
            f'<text x="{x + ancho_barra / 2:.1f}" y="{base_y + 26}" '
            f'text-anchor="middle" font-size="{T_ETIQUETA}" font-weight="700" '
            f'fill="{TINTA}">{_t(g["etiqueta"])}</text>'
        )
        if g.get("nota"):
            piezas.append(
                f'<text x="{x + ancho_barra / 2:.1f}" y="{base_y + 48}" '
                f'text-anchor="middle" font-size="{T_NOTA}" fill="{TINTA_SUAVE}">'
                f'{_t(g["nota"])}</text>'
            )
        x += ancho_barra + sep
    piezas.append(
        f'<line x1="{margen_izq - 14}" y1="{base_y}" x2="{total_ancho - 14}" '
        f'y2="{base_y}" stroke="{TINTA_SUAVE}" stroke-width="1.5"/>'
    )
    series = [{"nombre": nombre_relleno, "color": color_relleno},
              {"nombre": nombre_resto, "color": GRIS_RESTO}]
    return leyenda(series) + _svg(total_ancho, base_y + 60, piezas, "Barras apiladas")
