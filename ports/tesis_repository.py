"""
Puerto: de dónde sale el corpus del estudio Pre-Test / Post-Test.

Fase 3, regla 1 ("cero cálculos en la vista"). La regla es de DIRECCIÓN DE
DEPENDENCIAS, no de motor de almacenamiento: la vista no calcula, el caso de
uso `CalcularMetricasTesis` calcula, y este puerto dice qué datos necesita sin
comprometerse con dónde están guardados.

Hoy están en CSV --el corpus histórico del estudio nunca pasó por Postgres; la
base tiene lo operativo (HU que procesó NEXUS, casos que generó Gio), no las
82 HU cerradas del corpus con su prueba real--. El adaptador CSV es el único
que existe por ahora. Migrar a Postgres es un ETL de ocho fuentes y queda como
tarea aparte, con su propio plan de verificación: comparar indicador por
indicador CSV contra Postgres ANTES de cambiar el adaptador por defecto. Esa
comparación es el motivo de que exista este puerto; sin él habría que tocar la
vista para cambiar el origen.

Las estructuras que devuelve son plain dataclasses del dominio del estudio, no
filas de ningún CSV ni de ninguna tabla: eso es lo que hace que el caso de uso
no sepa de dónde vienen.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FilaTesis:
    """Una HU del corpus, con sus dos lados medidos."""

    hu_key: str
    criterios: int

    cubiertos_pre: int
    cubiertos_post: int

    casos_pre: int
    casos_pre_ejecutables: int
    casos_post: int
    casos_post_ejecutables: int


    casos_post_aprobados: int

    tests_plan: int
    tests_ejecutados: int

    defectos_pre: int
    defectos_mitigados: int

    cohorte: str
    umbral_reducido: bool


@dataclass(frozen=True)
class Cohorte:
    """Un corte acumulativo de la muestra, para el análisis de sensibilidad."""

    clave: str
    nombre: str
    claves_hu: tuple[str, ...]
    nota: str


@dataclass(frozen=True)
class ComposicionCasos:
    """
    Cómo se reparte el esfuerzo de prueba histórico, y qué puso el agente.

    `casos_gobierno` son las verificaciones normativas que se repiten idénticas
    en muchas HU (cumplimiento normativo, análisis estático, seguridad de la información y documentos de despliegue). El
    agente genera cero de esas, así que cualquier comparación contra él tiene
    que hacerse contra `casos_funcionales_humanos`, no contra el total.
    """

    casos_funcionales_humanos: int
    casos_gobierno: int
    titulos_gobierno: tuple[dict, ...]
    umbral_hu_gobierno: int


    casos_sin_guion: int
    casos_sin_accion: int
    casos_generados_agente: int
    casos_aprobados_agente: int
    casos_rechazados_agente: int


@dataclass(frozen=True)
class DefectoAuditado:
    """Un defecto real con su juicio de evitabilidad, para auditarlo a mano."""

    defecto_key: str
    titulo: str
    descripcion: str
    criticidad: str
    estado: str
    hu_keys: tuple[str, ...]
    veredicto: str
    veredicto_llm: str
    veredicto_humano: str
    corregido_por_humano: bool
    caso_agente: str
    justificacion: str
    motivo_no_evitable: str
    confianza: str
    modelo_juez: str
    comentario_humano: str
    tests_historicos: tuple[dict, ...]


@dataclass(frozen=True)
class CorpusTesis:
    """Todo lo que el caso de uso necesita, ya normalizado."""

    filas: tuple[FilaTesis, ...]
    cohortes: tuple[Cohorte, ...]
    composicion: ComposicionCasos
    defectos: tuple[DefectoAuditado, ...]


    capacidad_demostrada: int


    hu_con_trazabilidad_defectos: int
    hu_excluidas: tuple[str, ...]

    limitaciones: dict = field(default_factory=dict)
    avisos: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CriterioPareado:
    """
    Un criterio de aceptación con quién lo cubrió. Es la unidad de la matriz
    de intersección de la Fase 4.1.

    Se reconstruye desde las listas de NO cubiertos de cada lado, que es el
    único lugar del corpus con granularidad por criterio. La reconstrucción se
    verificó: las 60 filas cuadran contra los conteos declarados y los
    marginales dan exacto (207 del humano, 258 de Gio).
    """

    hu_key: str
    texto: str
    cubierto_humano: bool
    cubierto_gio: bool

    @property
    def cuadrante(self) -> str:
        if self.cubierto_humano and self.cubierto_gio:
            return "Ambos"
        if self.cubierto_gio:
            return "Solo Gio"
        if self.cubierto_humano:
            return "Solo Humano"
        return "Ninguno"


@dataclass(frozen=True)
class CasoRevisado:
    """Un caso que generó Gio, con el veredicto de la revisión humana."""

    hu_key: str
    titulo: str
    estado: str
    motivo_rechazo: str
    gherkin: str

    @property
    def aprobado(self) -> bool:
        return self.estado.strip().lower() == "aprobado"


@dataclass(frozen=True)
class TiemposProceso:
    """
    Lo que se puede medir del ciclo de diseño, y lo que no.

    `diseno_humano_*` va en None a propósito y NO se estima: las tres fuentes
    de tiempo de diseño del proyecto están rotas y eso se declara en vez de
    rellenarse -- tiempo_diseno_dias tiene 28 de 82 valores negativos,
    duracion_escritura_dias tiene mediana de 469 días (es el span de Test Plans
    reciclados) y la revisión retrospectiva mide solo el lado Post.
    """

    generacion_segundos_mediana: float | None
    generacion_n: int
    revision_minutos_total: float | None
    revision_minutos_mediana_hu: float | None
    revision_segundos_por_caso: float | None
    revision_n_hu: int
    revision_n_casos: int
    diseno_humano_minutos_hu: float | None
    motivo_sin_dato_humano: str


class TesisRepository(ABC):
    """Fuente del corpus del estudio. Una implementación por origen de datos."""

    @abstractmethod
    def obtener_corpus(self) -> CorpusTesis:
        """Devuelve el corpus entero, ya normalizado. Sin filtrar por cohorte."""
        raise NotImplementedError

    @abstractmethod
    def obtener_criterios_pareados(self) -> tuple[CriterioPareado, ...]:
        """Un registro por criterio de aceptación, con quién lo cubrió."""
        raise NotImplementedError

    @abstractmethod
    def obtener_casos_revisados(self) -> tuple[CasoRevisado, ...]:
        """Los casos que generó Gio, con el veredicto de la revisión humana."""
        raise NotImplementedError

    @abstractmethod
    def obtener_tiempos(self) -> TiemposProceso:
        """Tiempos medidos del ciclo, con lo no medible declarado como tal."""
        raise NotImplementedError
