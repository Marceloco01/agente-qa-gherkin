"""
Casos de uso de la Fase 4 — Impacto de la IA.

Tres análisis con la misma regla que la Fase 3: todo el cálculo vive acá y la
vista solo dibuja. Ninguno introduce un número nuevo: los tres reconcilian
contra la Fase 3 y las pruebas lo verifican --la suma de criterios tiene que
dar el mismo denominador (272 en cohorte completa) y el conteo de casos
aprobados el mismo 564--.

El tercero (`AnalizarNovedadCasos`, §4.3) es deliberadamente corto. El
submódulo iba a comparar los casos de Gio contra el histórico por similitud
semántica; esa medición se intentó cuatro veces, se descartó, y lo que quedó
en pie es un solo hecho verificable --cuántas compuertas de gobierno generó
Gio-- más la limitación declarada en pantalla. Ver `_LIMITACION`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from infrastructure.reportes.pretest_posttest import _titulo_normalizado
from ports.tesis_repository import (
    CasoRevisado,
    CriterioPareado,
    TesisRepository,
    TiemposProceso,
)

CUADRANTES = ("Ambos", "Solo Gio", "Solo Humano", "Ninguno")


COLOR_CUADRANTE = {
    "Ambos": "#1baf7a",
    "Solo Gio": "#2a78d6",
    "Solo Humano": "#eb6834",
    "Ninguno": "#94A3B8",
}


_FAMILIAS_RECHAZO = (
    ("Alucinación · dato inventado", r"aluc"),
    ("No cuadra con la especificación", r"no cuadra con especificaci"),
    ("Sin criterios disponibles en la HU", r"^ambiguo|criterios?[^.]{0,40}(vac|nan)"),
    ("Comportamiento no especificado", r"inventan|no especifica|no aparece|"
                                       r"sin especificar|no está mencion|no existe"),
)
_OTROS = "Otros motivos"


@dataclass(frozen=True)
class Cuadrante:
    nombre: str
    criterios: int
    porcentaje: float
    color: str
    descripcion: str


@dataclass(frozen=True)
class CoberturaIAvsHumanoDTO:
    cuadrantes: list[Cuadrante]
    total_criterios: int
    cubiertos_humano: int
    cubiertos_gio: int
    ganancia_neta: int
    puntos_ciegos: int
    razon_ganancia: float | None
    detalle: list[dict]
    hu_disponibles: list[str]
    cohorte_nombre: str
    n_hu: int


@dataclass(frozen=True)
class MotivoRechazo:
    familia: str
    casos: int
    porcentaje: float


@dataclass(frozen=True)
class RevisionRetrospectivaDTO:
    total_propuestos: int
    aprobados: int
    rechazados: int
    tasa_aprobacion: float
    tasa_rechazo: float
    motivos: list[MotivoRechazo]
    detalle_rechazados: list[dict]
    tiempos: TiemposProceso
    ciclo_nexus_segundos_hu: float | None
    cohorte_nombre: str
    n_hu: int


def _pct(n: float, d: float) -> float:
    return n / d * 100 if d else 0.0


@dataclass(frozen=True)
class NovedadCasosDTO:
    """
    Lo que quedó en pie del análisis de Gio contra el histórico.

    Es corto a propósito. La similitud semántica se midió cuatro veces y se
    descartó; el detalle de por qué vive en `limitacion_similitud` y se
    muestra en pantalla en vez de esconderse, porque un submódulo que
    prometía tres categorías y entrega una sola tiene que explicar la
    diferencia.
    """

    casos_generados: int
    casos_aprobados: int
    compuertas_generadas: int
    compuertas_historicas: int
    casos_funcionales_humanos: int
    casos_historicos_total: int
    pct_gobierno: float
    titulos_gobierno: list[dict]
    tabla_gobierno: list[dict]
    umbral_hu_gobierno: int
    limitacion_similitud: str


class AnalizarNovedadCasos:
    """Gio vs histórico: lo verificable, sin la similitud semántica."""


    _LIMITACION = (
        "El parecido semántico entre los casos de Gio y los del histórico se "
        "midió con embeddings (nomic-embed-text, el mismo del RAG) y NO se "
        "reporta como indicador. Se calibró de cuatro formas y cada una dio un "
        "titular distinto sobre exactamente los mismos vectores: (1) umbrales "
        "absolutos 0.85/0.60 dieron 26.0% de casos «replicados» y 0% "
        "«novedosos», imposible, porque el parecido mínimo observado es 0.7154 "
        "y nunca baja del umbral de novedad; (2) una nula de pares al azar dio "
        "92.7% replicado, y se descartó al reproducirla con vectores de ruido "
        "puro, que dieron lo mismo --la nula estaba sesgada, no los datos--; "
        "(3) una nula de mejor-match humano dio 0% replicado y 61.4% novedoso, "
        "con un p95 humano de 1.0000 exacto que delata el problema. La causa de "
        "fondo es estructural: un caso humano tiene hermanos dentro de su "
        "propia HU, escritos por la misma persona en la misma sesión --271 de "
        "los 280 pares casi idénticos del corpus (>=0.95) son de la misma HU, y "
        "196 de los 394 casos históricos (49.7%) tienen al menos un gemelo--, y "
        "Gio no tiene hermanos en esa comparación. Cualquier referencia "
        "construida sobre «cuánto se parece un caso a su vecino más cercano» "
        "mide esa hermandad, no originalidad. Un número que se mueve de 26% a "
        "92.7% a 0% según cómo se calibre no sostiene una afirmación, así que "
        "acá no se afirma nada con él. Los vectores y las dos distribuciones "
        "quedan en similitud_gio_historico.csv, distribucion_similitud.csv y "
        "duplicados_historico.csv para quien quiera retomarlo con un diseño "
        "mejor. El aporte incremental del agente sí está medido, sin embeddings "
        "y con cuentas que cuadran exactas, en Cobertura IA vs Humano."
    )

    def __init__(self, repositorio: TesisRepository):
        self._repo = repositorio

    def ejecutar(self) -> NovedadCasosDTO:
        corpus = self._repo.obtener_corpus()
        c = corpus.composicion


        titulos = {t["titulo"] for t in c.titulos_gobierno}
        generadas = sum(
            1 for caso in self._repo.obtener_casos_revisados()
            if _titulo_normalizado(caso.titulo) in titulos
        )
        total_historico = c.casos_funcionales_humanos + c.casos_gobierno
        return NovedadCasosDTO(
            casos_generados=c.casos_generados_agente,
            casos_aprobados=c.casos_aprobados_agente,
            compuertas_generadas=generadas,
            compuertas_historicas=c.casos_gobierno,
            casos_funcionales_humanos=c.casos_funcionales_humanos,
            casos_historicos_total=total_historico,
            pct_gobierno=_pct(c.casos_gobierno, total_historico),
            titulos_gobierno=list(c.titulos_gobierno),
            tabla_gobierno=[
                {"Verificación normativa": str(t["titulo"]).capitalize(),
                 "HU en las que se repite": t["hu"]}
                for t in sorted(c.titulos_gobierno,
                                key=lambda x: x["hu"], reverse=True)
            ],
            umbral_hu_gobierno=c.umbral_hu_gobierno,
            limitacion_similitud=self._LIMITACION,
        )


class AnalizarCoberturaIAvsHumano:
    """La matriz de intersección criterio por criterio."""

    _DESCRIPCION = {
        "Ambos": "Consenso: lo cubrieron el humano y Gio.",
        "Solo Gio": "Ganancia neta: el humano lo omitió y Gio lo cubrió.",
        "Solo Humano": "Puntos ciegos: el humano lo cubrió y Gio lo omitió.",
        "Ninguno": "Brecha residual: no lo cubrió ninguno de los dos.",
    }

    def __init__(self, repositorio: TesisRepository):
        self._repo = repositorio

    def ejecutar(self, cohorte: str = "completa") -> CoberturaIAvsHumanoDTO:
        corpus = self._repo.obtener_corpus()
        cohortes = {c.clave: c for c in corpus.cohortes}
        elegida = cohortes.get(cohorte) or cohortes["completa"]
        claves = set(elegida.claves_hu)
        criterios = [c for c in self._repo.obtener_criterios_pareados()
                     if c.hu_key in claves]
        total = len(criterios)

        conteo: dict[str, int] = {q: 0 for q in CUADRANTES}
        for c in criterios:
            conteo[c.cuadrante] += 1
        solo_gio, solo_hum = conteo["Solo Gio"], conteo["Solo Humano"]

        return CoberturaIAvsHumanoDTO(
            cuadrantes=[
                Cuadrante(nombre=q, criterios=conteo[q],
                          porcentaje=_pct(conteo[q], total),
                          color=COLOR_CUADRANTE[q],
                          descripcion=self._DESCRIPCION[q])
                for q in CUADRANTES
            ],
            total_criterios=total,
            cubiertos_humano=sum(1 for c in criterios if c.cubierto_humano),
            cubiertos_gio=sum(1 for c in criterios if c.cubierto_gio),
            ganancia_neta=solo_gio,
            puntos_ciegos=solo_hum,
            razon_ganancia=solo_gio / solo_hum if solo_hum else None,
            detalle=[
                {"HU Key": c.hu_key, "Criterio": c.texto,
                 "Humano": "Sí" if c.cubierto_humano else "No",
                 "Gio": "Sí" if c.cubierto_gio else "No",
                 "Cuadrante": c.cuadrante}
                for c in sorted(criterios, key=lambda x: (x.hu_key, x.cuadrante))
            ],
            hu_disponibles=sorted(claves),
            cohorte_nombre=elegida.nombre,
            n_hu=len(claves),
        )


class AnalizarRevisionRetrospectiva:
    """Qué hizo la revisión humana con los casos que propuso Gio."""

    def __init__(self, repositorio: TesisRepository):
        self._repo = repositorio

    def ejecutar(self, cohorte: str = "completa") -> RevisionRetrospectivaDTO:
        corpus = self._repo.obtener_corpus()
        cohortes = {c.clave: c for c in corpus.cohortes}
        elegida = cohortes.get(cohorte) or cohortes["completa"]
        claves = set(elegida.claves_hu)
        casos = [c for c in self._repo.obtener_casos_revisados() if c.hu_key in claves]
        rechazados = [c for c in casos if not c.aprobado]
        total = len(casos)

        familias: dict[str, int] = {}
        for c in rechazados:
            familias[self._familia(c)] = familias.get(self._familia(c), 0) + 1
        motivos = sorted(
            (MotivoRechazo(familia=f, casos=n, porcentaje=_pct(n, len(rechazados)))
             for f, n in familias.items()),
            key=lambda m: m.casos, reverse=True)

        t = self._repo.obtener_tiempos()
        ciclo = None
        if t.generacion_segundos_mediana is not None and t.revision_minutos_mediana_hu:
            ciclo = t.generacion_segundos_mediana + t.revision_minutos_mediana_hu * 60

        return RevisionRetrospectivaDTO(
            total_propuestos=total,
            aprobados=total - len(rechazados),
            rechazados=len(rechazados),
            tasa_aprobacion=_pct(total - len(rechazados), total),
            tasa_rechazo=_pct(len(rechazados), total),
            motivos=motivos,
            detalle_rechazados=[
                {"HU Key": c.hu_key, "Título": c.titulo,
                 "Familia": self._familia(c),
                 "Motivo del revisor": c.motivo_rechazo or "(sin motivo registrado)"}
                for c in sorted(rechazados, key=lambda x: (x.hu_key, x.titulo))
            ],
            tiempos=t,
            ciclo_nexus_segundos_hu=ciclo,
            cohorte_nombre=elegida.nombre,
            n_hu=len(claves),
        )

    @staticmethod
    def _familia(caso: CasoRevisado) -> str:
        motivo = (caso.motivo_rechazo or "").strip().lower()
        for nombre, patron in _FAMILIAS_RECHAZO:
            if re.search(patron, motivo):
                return nombre
        return _OTROS
