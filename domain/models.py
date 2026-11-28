"""
Entidades de negocio puras del dominio.

Reglas de esta capa (Arquitectura Hexagonal):
- CERO imports de infraestructura (sin Ollama, sin Jira, sin Streamlit, sin DB).
- Sin lógica de negocio compleja: son contenedores de datos (dataclasses) con,
  como máximo, validaciones triviales o propiedades de conveniencia.
- Cualquier otra capa puede importar de aquí. Esta capa no importa de nadie.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

@dataclass
class HistoriaUsuario:
    """
    Representa una Historia de Usuario (HU) tal como viene de Jira.

    Nota de diseño (ver spec, sección 10): este Jira no tiene un campo separado
    de "criterios de aceptación". Todo —contexto, reglas de negocio y criterios—
    vive mezclado como texto libre dentro de `descripcion`. Por eso no existe un
    campo `acceptance_criteria` separado en este modelo: sería inventar una
    estructura que no existe en la fuente real de datos.
    """

    key: str
    titulo: str
    descripcion: str
    test_plan_key: str | None = None


    fecha_inicio_proceso: datetime | None = None


    fecha_fin_proceso: datetime | None = None


    vera_score: int | None = None
    vera_aprobada: bool | None = None
    vera_motivo_bloqueo: str | None = None


    vera_umbral_aplicado: int | None = None


    generacion_forzada: bool = False


    descripcion_usada: str | None = None

    DESCRIPCION_MINIMA_CARACTERES: int = field(default=50, repr=False, compare=False)

    @property
    def descripcion_es_pobre(self) -> bool:
        """
        True si la descripción es demasiado corta para generar test cases con
        contexto suficiente (umbral confirmado en la spec: < 50 caracteres).

        Esto NO bloquea nada por sí solo: según la spec, ante una descripción
        pobre se debe advertir y dejar que el usuario decida si continúa o
        cancela. La decisión vive en la capa de aplicación/frontend, no aquí.

        Nota (fase de agentes humanizados): este chequeo sigue existiendo tal
        cual estaba -- Vera no lo reemplaza, lo complementa. Este es un aviso
        liviano por longitud; Vera hace una evaluación de calidad real vía LLM
        y puede bloquear la generación por completo (ver
        application/validar_hu.py).
        """
        texto = self.descripcion.strip() if self.descripcion else ""
        return len(texto) < self.DESCRIPCION_MINIMA_CARACTERES


@dataclass
class EvaluacionHU:
    """
    Resultado de Vera al evaluar una HU (application/validar_hu.py).

    Dos caminos posibles, mutuamente excluyentes:
    - depende_de_imagen=True: la HU menciona contenido visual (imagen,
      captura, adjunto) que el agente no puede leer -- se detecta por código
      (regex), sin gastar ninguna llamada a LLM, y bloquea SIEMPRE sin
      importar nada más. `score` queda en None porque nunca se llegó a
      evaluar con el LLM (decisión de eficiencia adoptada para este diseño).
    - depende_de_imagen=False: se evaluó con el LLM. `aprobada` es
      `score >= umbral` (ver infrastructure.config.cargar_configuracion_vera).
    """

    aprobada: bool
    depende_de_imagen: bool
    score: int | None = None
    criterios_faltantes: list[str] = field(default_factory=list)
    detalle: str = ""

    umbral: int | None = None


@dataclass(frozen=True)
class InfoTestPlan:
    """
    Información de un Test Plan encontrado al detectar vínculos de una HU
    (spec, sección 6, paso 4). Se usa para mostrar más contexto que solo la
    key cuando hay varios candidatos y el usuario tiene que elegir cuál usar
    -- key sola no alcanza para distinguir "Test Plan - Login viejo" de
    "Test Plan - Login v2" a simple vista.
    """

    key: str
    titulo: str
    estado: str

    def __str__(self) -> str:
        return f"{self.key} — {self.titulo} ({self.estado})"


class TipoCobertura(str, Enum):
    """
    Clasificación de qué situación cubre un test case (fase de agentes
    humanizados: Gio con etiquetado de cobertura).

    Existe por el índice de cobertura de pruebas del Dashboard (fórmula del
    libro [29]: situaciones cubiertas / situaciones identificadas x 100) --
    saber CUÁNTAS situaciones se cubren no alcanza para juzgar si la
    cobertura es buena; separar por tipo permite ver si el mix es
    razonable (todo camino feliz y nada de error/borde es una cobertura
    pobre aunque el índice total dé alto).

    Hereda de `str` por el mismo motivo que `EstadoTestCase`: serializa
    limpio si se persiste en una columna de texto (ver
    infrastructure/db/models_orm.py::TestCaseORM.tipo_cobertura, VARCHAR,
    no ENUM nativo -- mismo criterio que `estado`).
    """

    CAMINO_FELIZ = "camino_feliz"
    BORDE = "borde"
    ERROR = "error"


class EstadoTestCase(str, Enum):
    """
    Estado de revisión de un test case (spec, sección 6, paso 8).

    Hereda de `str` además de `Enum` para que serialice limpio si en Fase 3+
    esto se persiste (ej. en JSON o en una columna de texto), sin necesitar un
    adapter de serialización aparte.
    """

    PENDIENTE = "pendiente"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    SUBIDO_A_XRAY = "subido_a_xray"


@dataclass
class MensajeFeedback:
    """
    Un mensaje dentro del chat libre QA↔Agente (spec, sección 6, paso 8).

    Fase 2: estos mensajes viven solo en memoria de la sesión de Streamlit
    (`st.session_state`), no en base de datos todavía. Esta clase ya queda
    lista para que, en Fase 3+, un `Repository.guardar_feedback()` la
    persista sin tener que cambiar su forma — el campo `autor` ya distingue
    quién dijo qué, que es lo mínimo que pedirá la tabla de historial futura.
    """

    autor: str
    texto: str


@dataclass
class TestCase:
    """
    Representa un caso de prueba individual en formato Gherkin.

    Decisión confirmada (spec, sección 10): NO existe un Gherkin "general" de la
    HU separado de los casos. Cada TestCase ES su propio escenario Gherkin
    completo (Given/When/Then), coincidiendo con el histórico real donde
    `Tipo de Test = Cucumber` en Xray.
    """

    titulo: str
    gherkin: str
    hu_key: str


    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    estado: EstadoTestCase = EstadoTestCase.PENDIENTE
    xray_test_key: str | None = None
    historial_feedback: list[MensajeFeedback] = field(default_factory=list)


    version_contenido: int = 0


    alucinacion_detectada: bool = False
    alucinacion_detalle: str | None = None


    tipo_cobertura: TipoCobertura | None = None


    __test__ = False


    def __str__(self) -> str:
        return f"[{self.hu_key}] {self.titulo}\n{self.gherkin}"


DETALLE_VERIFICACION_NO_DISPONIBLE = (
    "Verificación de alucinación no disponible (error del modelo o respuesta "
    "no interpretable). Revisa el caso y edítalo o regenéralo antes de aprobar."
)


def marcar_verificacion_no_disponible(test_case: "TestCase") -> None:
    """Marca un test case como no verificado, con el mismo bloqueo que una
    alucinación detectada: no puede aprobarse sin edición o regeneración."""
    test_case.alucinacion_detectada = True
    test_case.alucinacion_detalle = DETALLE_VERIFICACION_NO_DISPONIBLE
