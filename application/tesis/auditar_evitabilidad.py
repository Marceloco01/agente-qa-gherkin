"""
Caso de uso: la auditoría cualitativa de los juicios de mitigación.

Fase 3 §3.3. Igual que el resto de la fase, todo el cálculo vive acá --el
índice de acuerdo humano/LLM, la distribución de veredictos, cuántos
descuentan-- y la vista solo dibuja.

Nota de vocabulario: el DATO se llama "evitabilidad" y sus valores son
'Evitable' / 'Parcialmente evitable' / 'No evitable' --así están en los CSV
de origen y así se comparan en este módulo--. La PANTALLA los muestra como
mitigación (ver `ETIQUETA_VEREDICTO`), por definición del indicador. Las dos
capas no se mezclan: acá nunca se compara contra una etiqueta de pantalla.

El punto de esta pantalla no es mostrar defectos: es dejar auditar el número
que sostiene el indicador TPD. Por eso el veredicto que se muestra como
vigente es EXACTAMENTE el que alimenta el cálculo (el humano cuando existe),
y no el del LLM: si la pantalla mostrara un juicio y el indicador usara otro,
la auditoría estaría revisando algo distinto de lo que se reporta.
"""

from __future__ import annotations

from dataclasses import dataclass

from ports.tesis_repository import DefectoAuditado, TesisRepository


VEREDICTOS = ("Evitable", "Parcialmente evitable", "No evitable")


VEREDICTO_QUE_DESCUENTA = "Evitable"


ETIQUETA_VEREDICTO = {
    "Evitable": "Mitigable",
    "Parcialmente evitable": "Parcialmente mitigable",
    "No evitable": "No mitigable",
}


def etiqueta_veredicto(veredicto: str) -> str:
    """El nombre de pantalla de un veredicto. Si no está mapeado, se devuelve
    tal cual en vez de inventar uno: un veredicto desconocido tiene que verse,
    no esconderse detrás de una etiqueta genérica."""
    return ETIQUETA_VEREDICTO.get(veredicto, veredicto)


@dataclass(frozen=True)
class CabeceraAuditoria:
    total: int
    validados: int
    acuerdo_pct: float
    coincidencias: int
    discrepancias: int
    distribucion: dict
    distribucion_llm: dict


    distribucion_etiquetada: tuple[tuple[str, int], ...]
    n_mitigable: int
    n_parcialmente_mitigable: int
    n_no_mitigable: int
    mitigados: int
    defectos_pre: int


    hu_auditadas: int
    sin_caso_agente: int


    corregidos_sin_caso: tuple[str, ...]
    modelo_juez: str
    limitacion: str


@dataclass(frozen=True)
class AuditoriaEvitabilidadDTO:
    cabecera: CabeceraAuditoria
    defectos: list[DefectoAuditado]


class AuditarEvitabilidad:
    def __init__(self, repositorio: TesisRepository):
        self._repo = repositorio

    def ejecutar(self) -> AuditoriaEvitabilidadDTO:
        corpus = self._repo.obtener_corpus()
        d = list(corpus.defectos)
        total = len(d)
        validados = sum(1 for x in d if x.veredicto_humano)
        discrepancias = sum(1 for x in d if x.corregido_por_humano)


        coincidencias = validados - discrepancias
        acuerdo = coincidencias / validados * 100 if validados else 0.0

        vigente: dict = {v: 0 for v in VEREDICTOS}
        llm: dict = {v: 0 for v in VEREDICTOS}
        for x in d:
            if x.veredicto in vigente:
                vigente[x.veredicto] += 1
            if x.veredicto_llm in llm:
                llm[x.veredicto_llm] += 1
        mitigados = vigente[VEREDICTO_QUE_DESCUENTA]

        modelos = {x.modelo_juez for x in d if x.modelo_juez}
        limitacion = (corpus.limitaciones
                      .get("evitabilidad_segunda_opinion", {})
                      .get("motivo", ""))

        return AuditoriaEvitabilidadDTO(
            cabecera=CabeceraAuditoria(
                total=total,
                validados=validados,
                acuerdo_pct=acuerdo,
                coincidencias=coincidencias,
                discrepancias=discrepancias,
                distribucion=vigente,
                distribucion_llm=llm,
                distribucion_etiquetada=tuple(
                    (etiqueta_veredicto(v), vigente[v]) for v in VEREDICTOS),
                n_mitigable=vigente[VEREDICTOS[0]],
                n_parcialmente_mitigable=vigente[VEREDICTOS[1]],
                n_no_mitigable=vigente[VEREDICTOS[2]],
                mitigados=mitigados,
                defectos_pre=total,
                hu_auditadas=corpus.hu_con_trazabilidad_defectos,
                sin_caso_agente=sum(1 for x in d if not x.caso_agente),
            corregidos_sin_caso=tuple(
                x.defecto_key for x in d
                if x.veredicto == VEREDICTO_QUE_DESCUENTA and not x.caso_agente),
                modelo_juez=", ".join(sorted(modelos)) or "s/d",
                limitacion=limitacion,
            ),
            defectos=sorted(d, key=lambda x: (x.criticidad, x.defecto_key)),
        )
