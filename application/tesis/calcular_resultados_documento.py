"""
Caso de uso: los resultados de la evaluación, listos para dibujar.

Acá vive TODO el cálculo de la pantalla de gráficos: totales por periodo,
índices, cuartiles de las cajas, series ordenadas de las curvas y el desglose
por severidad. La vista recibe el DTO y solo lo dibuja.

Es la misma regla que ya rige `CalcularMetricasTesis` ("cero cálculos en la
vista"), y acá importa más todavía: estos números ya están publicados en la
fuente de resultados. Un promedio calculado al vuelo que no coincida con ella
no es un detalle de presentación: es el tablero contradiciendo a la fuente de
la que salieron sus propios números.

Qué marco usa este caso de uso --y cuál NO--:

- Unidad de medida: **el ciclo de prueba**, 60 por periodo. No son las 61
  historias de usuario del corpus operativo.
- Estado de defectos = **corregidos / detectados**, medido en los dos periodos.
  No es el "defectos que NEXUS habría mitigado" de `CalcularMetricasTesis`,
  que es un contrafáctico y da otro número.
- Severidad ordenada de **menor a mayor** criticidad.
- Los ciclos sin defectos (0/0) **no se imputan**: no son 0% ni 100%, quedan
  fuera del indicador y se declaran aparte. Imputarlos como cero hundiría el
  periodo manual con 38 ciclos que nunca tuvieron un defecto que corregir.
"""

from __future__ import annotations

from dataclasses import dataclass

from ports.resultados_documento import (
    ORDEN_SEVERIDAD,
    CicloMedido,
    ResultadosDocumentoRepository,
)

PRE, POST = "pre", "post"


@dataclass(frozen=True)
class ResumenCaja:
    """Los cinco números de un diagrama de cajas, más sus atípicos."""

    minimo: float
    q1: float
    mediana: float
    q3: float
    maximo: float
    media: float
    atipicos: tuple[float, ...]
    n: int


@dataclass(frozen=True)
class IndicadorDocumento:
    """Un indicador de porcentaje, con sus dos periodos y sus distribuciones."""

    nombre: str
    numerador_rotulo: str
    denominador_rotulo: str
    numerador_pre: int
    denominador_pre: int
    numerador_post: int
    denominador_post: int
    valor_pre: float
    valor_post: float
    diferencia_pp: float
    desviacion_pre: float
    desviacion_post: float
    caja_pre: ResumenCaja
    caja_post: ResumenCaja


    curva_pre: tuple[float, ...]
    curva_post: tuple[float, ...]


@dataclass(frozen=True)
class FilaSeveridad:
    """Un nivel de severidad, con sus dos periodos."""

    severidad: str
    detectados_pre: int
    corregidos_pre: int
    no_corregidos_pre: int
    estado_pre: float | None
    detectados_post: int
    corregidos_post: int
    no_corregidos_post: int
    estado_post: float | None


@dataclass(frozen=True)
class EstadoDefectos:
    """El estado de defectos completo: por severidad, total y ciclos cubiertos."""

    por_severidad: tuple[FilaSeveridad, ...]
    detectados_pre: int
    corregidos_pre: int
    no_corregidos_pre: int
    estado_pre: float
    detectados_post: int
    corregidos_post: int
    no_corregidos_post: int
    estado_post: float
    diferencia_pp: float

    ciclos_con_defectos_pre: int
    ciclos_sin_defectos_pre: int
    ciclos_con_defectos_post: int
    ciclos_sin_defectos_post: int
    total_ciclos: int


    maximo_severidad: int
    maximo_detectados: int


@dataclass(frozen=True)
class ResultadosDocumentoDTO:
    cobertura: IndicadorDocumento
    ejecuciones: IndicadorDocumento
    defectos: EstadoDefectos
    total_ciclos: int
    detalle_por_ciclo: list[dict]


def _pct(num: float, den: float) -> float:
    return num / den * 100 if den else 0.0


def _percentil(ordenados: list[float], p: float) -> float:
    """
    Cuartil por interpolación lineal (el método 7 de Hyndman-Fan).

    Es el que usan `numpy.percentile`, `statistics.quantiles(method="inclusive")`
    y el diagrama de cajas de SPSS, que es el que generó las cajas publicadas.
    Se escribe a mano en vez de importar numpy para no sumar una dependencia a
    la capa de aplicación por tres líneas.
    """
    if not ordenados:
        return 0.0
    if len(ordenados) == 1:
        return ordenados[0]
    pos = (len(ordenados) - 1) * p
    bajo = int(pos)
    alto = min(bajo + 1, len(ordenados) - 1)
    return ordenados[bajo] + (ordenados[alto] - ordenados[bajo]) * (pos - bajo)


def _desviacion(valores: list[float]) -> float:
    """Desviación estándar muestral (n-1), que es la que reporta el documento."""
    n = len(valores)
    if n < 2:
        return 0.0
    media = sum(valores) / n
    return (sum((v - media) ** 2 for v in valores) / (n - 1)) ** 0.5


def _caja(valores: list[float]) -> ResumenCaja:
    """
    Resumen de Tukey: la caja es Q1-Q3 y los bigotes llegan al dato más
    extremo que cae dentro de 1,5 RIC. Lo que queda afuera son atípicos y se
    dibujan como puntos -- estirar el bigote hasta el mínimo absoluto
    escondería exactamente los ciclos que hay que mirar.
    """
    if not valores:
        return ResumenCaja(0, 0, 0, 0, 0, 0, (), 0)
    orden = sorted(valores)
    q1, mediana, q3 = (_percentil(orden, p) for p in (0.25, 0.5, 0.75))
    ric = q3 - q1
    tope_inf, tope_sup = q1 - 1.5 * ric, q3 + 1.5 * ric
    dentro = [v for v in orden if tope_inf <= v <= tope_sup] or orden
    return ResumenCaja(
        minimo=dentro[0], q1=q1, mediana=mediana, q3=q3, maximo=dentro[-1],
        media=sum(orden) / len(orden),
        atipicos=tuple(sorted({v for v in orden if v < tope_inf or v > tope_sup})),
        n=len(orden),
    )


def _techo(valor: int) -> int:
    """Sube el tope del eje al siguiente múltiplo de 4 (la rejilla va en cuartos)."""
    return max(4, -(-valor // 4) * 4)


class CalcularResultadosDocumento:
    def __init__(self, repositorio: ResultadosDocumentoRepository):
        self._repo = repositorio

    def ejecutar(self) -> ResultadosDocumentoDTO:
        ciclos = list(self._repo.obtener_ciclos())
        return ResultadosDocumentoDTO(
            cobertura=self._indicador(
                ciclos,
                nombre="Cobertura de pruebas",
                numerador_rotulo="Situaciones cubiertas",
                denominador_rotulo="Situaciones identificadas",
                campo_num="situaciones_cubiertas",
                campo_den="situaciones_identificadas",
            ),
            ejecuciones=self._indicador(
                ciclos,
                nombre="Ejecución de pruebas",
                numerador_rotulo="Casos ejecutados",
                denominador_rotulo="Casos especificados",
                campo_num="casos_ejecutados",
                campo_den="casos_especificados",
            ),
            defectos=self._defectos(ciclos),
            total_ciclos=len(ciclos),
            detalle_por_ciclo=self._detalle(ciclos),
        )


    def _indicador(
        self, ciclos: list[CicloMedido], *, nombre: str,
        numerador_rotulo: str, denominador_rotulo: str,
        campo_num: str, campo_den: str,
    ) -> IndicadorDocumento:
        def num(c: CicloMedido, lado: str) -> int:
            return getattr(c, f"{campo_num}_{lado}")

        def den(c: CicloMedido, lado: str) -> int:
            return getattr(c, f"{campo_den}_{lado}")

        tot_num = {l: sum(num(c, l) for c in ciclos) for l in (PRE, POST)}
        tot_den = {l: sum(den(c, l) for c in ciclos) for l in (PRE, POST)}


        valor = {l: _pct(tot_num[l], tot_den[l]) for l in (PRE, POST)}
        por_ciclo = {
            l: [_pct(num(c, l), den(c, l)) for c in ciclos] for l in (PRE, POST)
        }


        curvas = {l: tuple(sorted(por_ciclo[l])) for l in (PRE, POST)}
        return IndicadorDocumento(
            nombre=nombre,
            numerador_rotulo=numerador_rotulo,
            denominador_rotulo=denominador_rotulo,
            numerador_pre=tot_num[PRE], denominador_pre=tot_den[PRE],
            numerador_post=tot_num[POST], denominador_post=tot_den[POST],
            valor_pre=valor[PRE], valor_post=valor[POST],


            diferencia_pp=round(valor[POST], 2) - round(valor[PRE], 2),
            desviacion_pre=_desviacion(por_ciclo[PRE]),
            desviacion_post=_desviacion(por_ciclo[POST]),
            caja_pre=_caja(por_ciclo[PRE]), caja_post=_caja(por_ciclo[POST]),
            curva_pre=curvas[PRE],
            curva_post=curvas[POST],
        )


    def _defectos(self, ciclos: list[CicloMedido]) -> EstadoDefectos:
        det = {l: {s: 0 for s in ORDEN_SEVERIDAD} for l in (PRE, POST)}
        cor = {l: {s: 0 for s in ORDEN_SEVERIDAD} for l in (PRE, POST)}
        for c in ciclos:
            for lado in (PRE, POST):
                for s in ORDEN_SEVERIDAD:
                    det[lado][s] += getattr(c, f"detectados_por_severidad_{lado}")[s]
                    cor[lado][s] += getattr(c, f"corregidos_por_severidad_{lado}")[s]

        def estado(d: int, c: int) -> float | None:


            return _pct(c, d) if d else None

        filas = tuple(
            FilaSeveridad(
                severidad=s,
                detectados_pre=det[PRE][s], corregidos_pre=cor[PRE][s],
                no_corregidos_pre=det[PRE][s] - cor[PRE][s],
                estado_pre=estado(det[PRE][s], cor[PRE][s]),
                detectados_post=det[POST][s], corregidos_post=cor[POST][s],
                no_corregidos_post=det[POST][s] - cor[POST][s],
                estado_post=estado(det[POST][s], cor[POST][s]),
            )
            for s in ORDEN_SEVERIDAD
        )
        tot_det = {l: sum(det[l].values()) for l in (PRE, POST)}
        tot_cor = {l: sum(cor[l].values()) for l in (PRE, POST)}
        est = {l: _pct(tot_cor[l], tot_det[l]) for l in (PRE, POST)}
        con = {
            l: sum(1 for c in ciclos if getattr(c, f"defectos_detectados_{l}") > 0)
            for l in (PRE, POST)
        }
        return EstadoDefectos(
            por_severidad=filas,
            detectados_pre=tot_det[PRE], corregidos_pre=tot_cor[PRE],
            no_corregidos_pre=tot_det[PRE] - tot_cor[PRE], estado_pre=est[PRE],
            detectados_post=tot_det[POST], corregidos_post=tot_cor[POST],
            no_corregidos_post=tot_det[POST] - tot_cor[POST], estado_post=est[POST],
            diferencia_pp=round(est[POST], 2) - round(est[PRE], 2),
            ciclos_con_defectos_pre=con[PRE],
            ciclos_sin_defectos_pre=len(ciclos) - con[PRE],
            ciclos_con_defectos_post=con[POST],
            ciclos_sin_defectos_post=len(ciclos) - con[POST],
            total_ciclos=len(ciclos),
            maximo_severidad=_techo(max(
                [f.detectados_pre for f in filas] + [f.detectados_post for f in filas]
            )),
            maximo_detectados=_techo(max(tot_det[PRE], tot_det[POST])),
        )

    def _detalle(self, ciclos: list[CicloMedido]) -> list[dict]:
        def fila(c: CicloMedido) -> dict:
            return {
                "Ciclo": c.ciclo,
                "Referencia sin agente": c.id_pre,
                "Referencia con agente": c.id_post,
                "Cobertura sin agente (%)": round(
                    _pct(c.situaciones_cubiertas_pre, c.situaciones_identificadas_pre), 2),
                "Cobertura con agente (%)": round(
                    _pct(c.situaciones_cubiertas_post, c.situaciones_identificadas_post), 2),
                "Ejecución sin agente (%)": round(
                    _pct(c.casos_ejecutados_pre, c.casos_especificados_pre), 2),
                "Ejecución con agente (%)": round(
                    _pct(c.casos_ejecutados_post, c.casos_especificados_post), 2),
                "Defectos sin agente": c.defectos_detectados_pre,
                "Corregidos sin agente": c.defectos_corregidos_pre,
                "Defectos con agente": c.defectos_detectados_post,
                "Corregidos con agente": c.defectos_corregidos_post,
            }
        return [fila(c) for c in ciclos]
