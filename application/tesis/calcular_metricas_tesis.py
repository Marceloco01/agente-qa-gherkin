"""
Caso de uso: los cuatro indicadores oficiales del estudio, para una cohorte.

Fase 3, regla 1. Acá vive TODO el cálculo: ratios, deltas, agregación y el
filtro de sensibilidad por cohorte. La vista recibe un `ResumenTesisDTO` y
solo lo dibuja.

Por qué importa que esté acá y no en la pantalla: en este proyecto ya apareció
seis veces el mismo bug -- una pantalla que muestra un agregado calculado
sobre un conjunto distinto del que dice mostrar. Con el cálculo en un solo
lugar y la muestra viajando dentro del propio indicador (`n_muestra`), ese
error deja de ser posible: no hay dónde escribir el número equivocado.

Nota sobre TVO: su Post NO se calcula sobre la cohorte filtrada. La capacidad
demostrada y la carga normativa son del corpus entero --las compuertas de
gobierno se aplican a toda HU, no a la muestra que uno elija mirar--, así que
recortarlas por cohorte daría un número sin sentido físico. Se reporta con su
propia muestra declarada y eso queda dicho en su descripción metodológica.
"""

from __future__ import annotations

from dataclasses import dataclass

from ports.tesis_repository import CorpusTesis, FilaTesis, TesisRepository

COHORTE_POR_DEFECTO = "completa"


_VEREDICTO_CORREGIDO = "Evitable"


_ORDEN_SEVERIDAD = {"Critico": 0, "Crítico": 0, "Alto": 1, "Medio": 2,
                    "Bajo": 3, "SIN_CLASIFICAR": 4, "Sin clasificar": 4}
_ETIQUETA_SEVERIDAD = {"Critico": "Crítico", "SIN_CLASIFICAR": "Sin clasificar"}


@dataclass(frozen=True)
class IndicadorComparativo:
    nombre: str
    sigla: str
    valor_pre: float
    valor_post: float
    unidad: str
    delta_absoluto: float
    delta_porcentual: float
    n_muestra: int
    descripcion_metodologica: str


    detalle_pre: str = ""
    detalle_post: str = ""

    sentido: str = "mejor"


    etiqueta_pre: str = "Pre-Test"
    etiqueta_post: str = "Post-Test"


    delta_etiqueta: str = ""


@dataclass(frozen=True)
class DesgloseEstadoDefectos:
    severidad: str
    total_detectados: int
    mitigados: int


    abiertos: int
    cerrados: int
    ratio_estado: float


@dataclass(frozen=True)
class ResumenTesisDTO:


    indice_cobertura_pruebas: IndicadorComparativo


    indice_ejecutabilidad_estructural: IndicadorComparativo
    estado_defectos_global: IndicadorComparativo
    estado_defectos_por_severidad: list[DesgloseEstadoDefectos]


    total_defectos_detectados: int
    total_defectos_mitigados: int


    maximo_defectos_severidad: int
    severidad_mas_mitigada: DesgloseEstadoDefectos | None


    viabilidad_operativa_control: IndicadorComparativo
    densidad_requerimiento_caso: tuple[float, float]
    drc_pre: float
    drc_post: float
    total_casos_normativos: int
    casos_sin_guion: int
    casos_sin_accion: int
    casos_no_ejecutables: int
    total_casos_funcionales_humanos: int
    total_casos_funcionales_agente: int
    casos_rechazados_revision: int
    detalle_por_hu: list[dict]

    cohorte_clave: str
    cohorte_nombre: str
    n_hu: int
    n_criterios: int
    n_defectos_auditados: int
    titulos_gobierno: list[dict]
    umbral_hu_gobierno: int
    hu_excluidas: list[str]
    avisos: list[str]
    cohortes_disponibles: list[dict]


def _pct(num: float, den: float) -> float:
    return num / den * 100 if den else 0.0


def _abierto(estado: str) -> bool:
    return (estado or "").strip().lower().startswith("abiert")


def _cerrado(estado: str) -> bool:
    return (estado or "").strip().lower().startswith("cerrad")


def _techo_entero(valor: int) -> int:
    """
    Sube el tope del eje al siguiente múltiplo de 4.

    El gráfico dibuja la rejilla en cuartos. Con un tope de 26 las marcas caen
    en 6,5 / 13 / 19,5 y se imprimen como 6, 13, 20 -- un eje de conteos con
    saltos irregulares, que en una sustentación se lee como descuido. Múltiplo
    de 4 garantiza que los cuatro cuartos sean enteros.
    """
    return max(4, -(-valor // 4) * 4)


class CalcularMetricasTesis:
    def __init__(self, repositorio: TesisRepository):
        self._repo = repositorio

    def ejecutar(self, cohorte: str = COHORTE_POR_DEFECTO) -> ResumenTesisDTO:
        corpus = self._repo.obtener_corpus()
        cohortes = {c.clave: c for c in corpus.cohortes}
        elegida = cohortes.get(cohorte) or cohortes[COHORTE_POR_DEFECTO]
        claves = set(elegida.claves_hu)
        filas = [f for f in corpus.filas if f.hu_key in claves]
        if not filas:
            filas = list(corpus.filas)

        drc_pre, drc_post = self._drc(filas, "pre"), self._drc(filas, "post")
        desglose = self._estado_defectos_severidad(corpus)
        return ResumenTesisDTO(
            indice_cobertura_pruebas=self._cobertura(filas),


            indice_ejecutabilidad_estructural=self._ejecutabilidad_estructural(filas),
            viabilidad_operativa_control=self._ejecuciones(corpus, filas),
            estado_defectos_global=self._estado_defectos(corpus),
            estado_defectos_por_severidad=desglose,
            total_defectos_detectados=len(corpus.defectos),
            total_defectos_mitigados=sum(d.mitigados for d in desglose),
            maximo_defectos_severidad=_techo_entero(
                max((d.total_detectados for d in desglose), default=1)),
            severidad_mas_mitigada=(
                max(desglose, key=lambda d: d.ratio_estado) if desglose else None),

            densidad_requerimiento_caso=(drc_pre, drc_post),
            drc_pre=drc_pre,
            drc_post=drc_post,
            total_casos_normativos=corpus.composicion.casos_gobierno,
            casos_sin_guion=corpus.composicion.casos_sin_guion,
            casos_sin_accion=corpus.composicion.casos_sin_accion,
            casos_no_ejecutables=(corpus.composicion.casos_sin_guion
                                  + corpus.composicion.casos_sin_accion),
            total_casos_funcionales_humanos=corpus.composicion.casos_funcionales_humanos,
            total_casos_funcionales_agente=corpus.composicion.casos_aprobados_agente,
            casos_rechazados_revision=corpus.composicion.casos_rechazados_agente,
            detalle_por_hu=self._detalle(filas),
            cohorte_clave=elegida.clave,
            cohorte_nombre=elegida.nombre,
            n_hu=len(filas),
            n_criterios=sum(f.criterios for f in filas),
            n_defectos_auditados=sum(f.defectos_pre for f in filas),
            titulos_gobierno=list(corpus.composicion.titulos_gobierno),
            umbral_hu_gobierno=corpus.composicion.umbral_hu_gobierno,
            hu_excluidas=list(corpus.hu_excluidas),
            avisos=list(corpus.avisos),
            cohortes_disponibles=[
                {"clave": c.clave, "nombre": c.nombre,
                 "n": len([f for f in corpus.filas if f.hu_key in set(c.claves_hu)]),
                 "nota": c.nota}
                for c in corpus.cohortes
            ],
        )


    def _cobertura(self, filas: list[FilaTesis]) -> IndicadorComparativo:
        crit = sum(f.criterios for f in filas)
        pre = _pct(sum(f.cubiertos_pre for f in filas), crit)
        post = _pct(sum(f.cubiertos_post for f in filas), crit)
        return IndicadorComparativo(
            nombre="Índice de cobertura de pruebas", sigla="Cobertura",
            valor_pre=pre, valor_post=post, unidad="%",
            delta_absoluto=post - pre,
            delta_porcentual=(post / pre - 1) * 100 if pre else 0.0,
            n_muestra=len(filas),
            descripcion_metodologica=(
                "Evaluación semántica automatizada, criterio por criterio, del "
                "histórico humano y de los casos de Gio sobre los mismos "
                "criterios. No la afectan los casos normativos: esas "
                "verificaciones no cubren criterios de ninguno de los dos lados."
            ),
            detalle_pre=f"{sum(f.cubiertos_pre for f in filas)}/{crit} criterios",
            detalle_post=f"{sum(f.cubiertos_post for f in filas)}/{crit} criterios",
        )

    def _ejecutabilidad_estructural(self, filas: list[FilaTesis]) -> IndicadorComparativo:
        pre_n = sum(f.casos_pre for f in filas)
        post_n = sum(f.casos_post for f in filas)
        pre = _pct(sum(f.casos_pre_ejecutables for f in filas), pre_n)
        post = _pct(sum(f.casos_post_ejecutables for f in filas), post_n)


        no_ejecutables = pre_n - sum(f.casos_pre_ejecutables for f in filas)
        return IndicadorComparativo(


            nombre="Índice de ejecuciones de pruebas",
            sigla="Ejecuciones",
            valor_pre=pre, valor_post=post, unidad="%",
            delta_absoluto=post - pre,
            delta_porcentual=(post / pre - 1) * 100 if pre else 0.0,
            n_muestra=len(filas),
            descripcion_metodologica=(
                "Porcentaje de casos de prueba cuyo diseño cumple la "
                "estructura Gherkin mínima para ejecutarse sin reprocesos. "
                "Verificación sintáctica determinista, sin LLM: un caso es "
                "ejecutable por un QA que no lo escribió si el guion existe y "
                "declara acción (When) y resultado verificable (Then). Mide el "
                "DISEÑO del caso, no su corrida en ambiente de test: ninguna "
                "ejecución entra en esta cuenta --las ejecuciones reales están "
                "en Viabilidad operativa--. Se mide solo sobre casos "
                "FUNCIONALES: el agente no genera verificaciones normativas, "
                "así que compararlo contra el total humano no compararía lo "
                "mismo."
            ),
            detalle_pre=f"{sum(f.casos_pre_ejecutables for f in filas)}/{pre_n} casos "
                        f"· {no_ejecutables} no ejecutables",
            detalle_post=f"{sum(f.casos_post_ejecutables for f in filas)}/{post_n} casos",
        )

    def _ejecuciones(self, corpus: CorpusTesis, filas: list[FilaTesis]) -> IndicadorComparativo:

        plan = sum(f.tests_plan for f in filas)
        pre = _pct(sum(f.tests_ejecutados for f in filas), plan)


        capacidad = corpus.capacidad_demostrada
        demanda = (corpus.composicion.casos_aprobados_agente
                   + corpus.composicion.casos_gobierno)
        post = min(100.0, _pct(capacidad, demanda))
        exceso = demanda - capacidad
        return IndicadorComparativo(
            nombre="Viabilidad operativa de ejecución", sigla="Capacidad",
            valor_pre=pre, valor_post=post, unidad="%",
            delta_absoluto=post - pre,
            delta_porcentual=(post / pre - 1) * 100 if pre else 0.0,
            n_muestra=len(corpus.filas),
            descripcion_metodologica=(
                f"Compromiso operativo: la demanda Post son los "
                f"{corpus.composicion.casos_aprobados_agente} casos funcionales "
                f"aprobados del agente MÁS los {corpus.composicion.casos_gobierno} "
                "normativos, que no desaparecen porque el agente escriba los "
                f"funcionales. Contra {capacidad} tests de capacidad demostrada, "
                f"excede en {exceso} ({_pct(exceso, capacidad):+.1f}%). El Post se "
                "reporta sobre el corpus entero y no sobre la cohorte: la "
                "capacidad y la carga normativa no se recortan por muestra."
            ),
            detalle_pre=f"{sum(f.tests_ejecutados for f in filas)}/{plan} tests cubiertos",
            detalle_post=f"{capacidad} capacidad / {demanda} demanda",
            sentido="neutro",
        )

    def _estado_defectos(self, corpus: CorpusTesis) -> IndicadorComparativo:
        """
        Estado de defectos: el inventario real contra lo que el agente mitiga.

        **Cambio del 2026-09-16, decidido por el tesista.** Antes el Post era
        `total - mitigados` = 30, rotulado "defectos proyectados". Eso es un
        contrafáctico --cuántos quedarían-- y no corresponde a ningún conjunto
        auditable: no existen 30 defectos que alguien pueda abrir y revisar.
        Ahora el Post son los 27 efectivamente mitigados, que sí son un
        conjunto concreto, validado uno por uno y exportable. La proyección no
        se reporta en ninguna pantalla.

        Ojo con la lectura: el Pre (57) y el Post (27) NO son la misma magnitud
        medida dos veces. El Post es un SUBCONJUNTO del Pre, así que la tarjeta
        no los rotula "Pre-Test / Post-Test" ni muestra un cambio porcentual
        --"57 → 27" se leería como una caída del 53% que nunca ocurrió--. Por
        eso viajan `etiqueta_pre`, `etiqueta_post` y `delta_etiqueta`.

        Un defecto cuenta como MITIGADO cuando su validación humana es
        estrictamente 'Evitable'. Los 'Parcialmente evitable' y el 'No
        evitable' entran al denominador pero NO al numerador: es el criterio
        conservador del estudio, y contar la categoría de la duda inflaría el
        resultado justo donde el método es más débil.

        Sobre por qué NO se exige además que el defecto tenga un caso señalado
        por el juez: ese campo lo llena el LLM, y queda vacío precisamente en
        los defectos donde el arbitraje humano SUBIÓ el veredicto a 'Evitable'
        (el juez había dicho 'Parcialmente' o 'No evitable' y no nombró
        ninguno). Exigirlo borraría 5 de los 27 -- es decir, borraría el
        arbitraje humano, que es justamente lo que da rigor al indicador. Esos
        5 se muestran identificados en la pantalla de auditoría en vez de
        descontarse en silencio.

        El Pre es el inventario completo, y ninguno de esos 57 fue prevenido
        por las pruebas del equipo: eso no es un truco, es la definición de la
        muestra --se parte del listado de defectos que LLEGARON A PRODUCCIÓN--.
        """
        total = len(corpus.defectos)
        mitigados = sum(1 for x in corpus.defectos
                        if x.veredicto == _VEREDICTO_CORREGIDO)
        abiertos = sum(1 for x in corpus.defectos if _abierto(x.estado))
        cerrados = sum(1 for x in corpus.defectos if _cerrado(x.estado))
        sin_caso = sum(1 for x in corpus.defectos
                       if x.veredicto == _VEREDICTO_CORREGIDO and not x.caso_agente)
        return IndicadorComparativo(
            nombre="Estado de defectos", sigla="Defectos",
            valor_pre=float(total), valor_post=float(mitigados), unidad="conteo",
            delta_absoluto=float(mitigados),
            delta_porcentual=_pct(mitigados, total),
            etiqueta_pre="Llegaron a producción",
            etiqueta_post="Mitigados por NEXUS",
            delta_etiqueta=f"{_pct(mitigados, total):.1f}% de los {total}",
            n_muestra=corpus.hu_con_trazabilidad_defectos,
            descripcion_metodologica=(
                f"Cantidad de defectos reales del histórico frente a los que "
                f"las pruebas del agente habrían mitigado. Las dos cifras no "
                f"son la misma magnitud medida dos veces: los {mitigados} son "
                f"un SUBCONJUNTO de los {total}, no un «después», y cada uno "
                f"es un defecto real que se puede abrir y revisar. Un defecto "
                f"cuenta como mitigado "
                f"cuando la validación humana lo clasifica como mitigable por "
                f"las pruebas del agente ({mitigados} de {total}); los "
                f"parcialmente mitigables y los no mitigables NO descuentan "
                f"--es la categoría de la duda, y descontarla inflaría la "
                f"mejora justo donde el método es más débil--. Muestra fija: "
                f"solo estas HU tienen trazabilidad de incidentes en Jira. De "
                f"los {mitigados} mitigados, {sin_caso} lo son por arbitraje "
                f"humano sin caso señalado por el juez, identificados en "
                f"Validar mitigación."
            ),
            detalle_pre=f"{total} defectos reales · {abiertos} abiertos, "
                        f"{cerrados} cerrados",
            detalle_post=f"{mitigados} de los {total}, validados uno por uno",
            sentido="mejor",
        )


    def _estado_defectos_severidad(
        self, corpus: CorpusTesis
    ) -> list[DesgloseEstadoDefectos]:
        """La misma fórmula, por nivel de severidad."""
        total: dict[str, int] = {}
        corr: dict[str, int] = {}
        abie: dict[str, int] = {}
        cerr: dict[str, int] = {}
        for x in corpus.defectos:


            sev = _ETIQUETA_SEVERIDAD.get(x.criticidad, x.criticidad or "Sin clasificar")
            total[sev] = total.get(sev, 0) + 1
            if x.veredicto == _VEREDICTO_CORREGIDO:
                corr[sev] = corr.get(sev, 0) + 1
            if _abierto(x.estado):
                abie[sev] = abie.get(sev, 0) + 1
            elif _cerrado(x.estado):
                cerr[sev] = cerr.get(sev, 0) + 1
        return [
            DesgloseEstadoDefectos(
                severidad=sev,
                total_detectados=total[sev],
                mitigados=corr.get(sev, 0),
                abiertos=abie.get(sev, 0),
                cerrados=cerr.get(sev, 0),
                ratio_estado=_pct(corr.get(sev, 0), total[sev]),
            )
            for sev in sorted(total, key=lambda s: _ORDEN_SEVERIDAD.get(s, 99))
        ]


    def _drc(self, filas: list[FilaTesis], lado: str) -> float:
        """Criterios cubiertos por caso funcional. Densidad, no cobertura."""
        if lado == "pre":
            casos = sum(f.casos_pre for f in filas)
            return sum(f.cubiertos_pre for f in filas) / casos if casos else 0.0


        casos = sum(f.casos_post_aprobados for f in filas)
        return sum(f.cubiertos_post for f in filas) / casos if casos else 0.0

    def _detalle(self, filas: list[FilaTesis]) -> list[dict]:
        return [
            {
                "Key HU": f.hu_key,
                "Criterios Totales": f.criterios,
                "CRF Pre (%)": round(_pct(f.cubiertos_pre, f.criterios), 1),
                "CRF Post (%)": round(_pct(f.cubiertos_post, f.criterios), 1),
                "CEC Pre (%)": round(_pct(f.casos_pre_ejecutables, f.casos_pre), 1),
                "CEC Post (%)": round(_pct(f.casos_post_ejecutables, f.casos_post), 1),
                "Defectos Pre": f.defectos_pre,
                "Defectos Mitigados": f.defectos_mitigados,
                "Estado Umbral": "Reducido" if f.umbral_reducido else "Estándar",
            }
            for f in sorted(filas, key=lambda x: x.hu_key)
        ]
