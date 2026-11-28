"""
Adapter concreto de LLMProvider para Ollama (modelos locales).

Implementa solo `generar_test_cases()` en Fase 1, con `llama3.1:8b` (fallback
`qwen3:4b` si los tiempos resultan muy altos en el hardware disponible — ver
spec, sección 2). `generar_embedding()` (Fase 3) y `verificar_alucinacion()`
(Fase 4) quedan con NotImplementedError.

Fase de agentes humanizados: se agrega `evaluar_hu()` (Vera). Ollama deja de
ser el proveedor primario (ver `adapters/llm/ollama_provider.py` y
`infrastructure/fabrica_llm.py`), pero se mantiene como alternativa completa
-- implementa el mismo contrato, sin partes a medias.
"""

from __future__ import annotations

import json
import re
import time

import ollama

from domain.models import HistoriaUsuario, MensajeFeedback, TestCase, TipoCobertura
from infrastructure.config import obtener_logger
from ports.llm_provider import LLMProvider

_log = obtener_logger(__name__)


_PROMPT_SISTEMA = """\
Eres un ingeniero de QA experto en escribir casos de prueba en formato Gherkin \
(Given/When/Then) a partir de Historias de Usuario.

Reglas estrictas que debes seguir:
1. Cada caso de prueba es un escenario Gherkin INDEPENDIENTE y COMPLETO. No \
generes un Gherkin general de la HU separado de los casos: cada caso ES su \
propio Gherkin.
2. La cantidad de casos depende de lo que la Historia de Usuario sugiera \
(caminos felices, validaciones, casos de error, casos límite mencionados en \
la descripción). No generes un número fijo arbitrario: genera los que \
realmente correspondan, ni más ni menos.
3. No inventes funcionalidad que no esté mencionada ni implícita en la \
descripción de la HU. Si la descripción no menciona algo, no lo asumas.
4. Clasifica cada caso con "tipo_cobertura", exactamente uno de estos tres \
valores:
   - "camino_feliz": todo sucede según lo esperado, sin errores ni \
condiciones límite.
   - "borde": prueba un límite o condición extrema pero válida (mínimos, \
máximos, casos particulares que la HU menciona explícitamente).
   - "error": prueba una condición inválida o una falla esperada \
(validación que debe rechazar, mensaje de error, dato incorrecto).
5. Responde EXCLUSIVAMENTE con un JSON válido, sin texto antes ni después, \
sin bloques de código markdown, con esta forma exacta:

{
  "test_cases": [
    {
      "titulo": "string corto descriptivo del escenario",
      "gherkin": "Scenario: ...\\n  Given ...\\n  When ...\\n  Then ...",
      "tipo_cobertura": "camino_feliz"
    }
  ]
}

El campo "gherkin" debe ser un string con saltos de línea (\\n), empezando \
con "Scenario:" seguido de las líneas Given/When/Then/And que correspondan. \
El campo "tipo_cobertura" debe ser exactamente uno de los tres valores de \
la regla 4, en minúsculas, sin comillas adicionales ni variantes.
"""

_PROMPT_USUARIO_TEMPLATE = """\
Historia de Usuario: {key}
Título: {titulo}

Descripción:
{descripcion}
{seccion_casos_similares}
Genera los casos de prueba en Gherkin para esta Historia de Usuario, \
siguiendo exactamente el formato JSON indicado.
"""

_PROMPT_SISTEMA_REGENERACION = """\
Eres un ingeniero de QA. Un test case en Gherkin fue rechazado por un revisor \
humano, que te dio feedback sobre qué corregir. Tu tarea es generar una nueva \
versión del MISMO test case (mismo propósito general), corrigiendo lo que el \
feedback indica.

Reglas estrictas:
1. Sigue el feedback más reciente del usuario, pero ten en cuenta también el \
historial completo de la conversación si hay correcciones previas.
2. No cambies el test case a algo completamente distinto -- es una corrección, \
no una reescritura libre.
3. Responde EXCLUSIVAMENTE con un JSON válido, sin texto antes ni después, sin \
bloques de código markdown, con esta forma exacta:

{
  "titulo": "string corto descriptivo del escenario",
  "gherkin": "Scenario: ...\\n  Given ...\\n  When ...\\n  Then ..."
}
"""

_PROMPT_USUARIO_REGENERACION_TEMPLATE = """\
Test case actual (rechazado):
Título: {titulo_actual}
{gherkin_actual}

Historial de feedback (en orden cronológico):
{historial_formateado}

Genera la nueva versión corregida, siguiendo exactamente el formato JSON indicado.
"""

_PROMPT_SISTEMA_CASO_INDIVIDUAL = """\
Eres un ingeniero de QA. El usuario (un experto en QA) quiere agregar un test \
case puntual a una Historia de Usuario, describiendo en lenguaje natural el \
escenario que quiere cubrir. Tu tarea es escribir ESE escenario específico en \
formato Gherkin (Given/When/Then) -- no generes otros casos, no te desvíes \
del escenario que el usuario describió.

Reglas estrictas:
1. El test case debe cubrir EXACTAMENTE el escenario que el usuario describió, \
ni más ni menos. No agregues validaciones o pasos que el usuario no pidió.
2. Usa el contexto de la HU (título y descripción) para entender el dominio, \
pero el escenario lo define el usuario, no la HU en general.
3. Responde EXCLUSIVAMENTE con un JSON válido, sin texto antes ni después, sin \
bloques de código markdown, con esta forma exacta:

{
  "titulo": "string corto descriptivo del escenario",
  "gherkin": "Scenario: ...\\n  Given ...\\n  When ...\\n  Then ..."
}
"""

_PROMPT_USUARIO_CASO_INDIVIDUAL_TEMPLATE = """\
Historia de Usuario: {key}
Título: {titulo}

Descripción:
{descripcion}

Escenario que el usuario quiere cubrir con este test case:
{descripcion_escenario}

Genera el test case en Gherkin para ESE escenario específico, siguiendo \
exactamente el formato JSON indicado.
"""


_PROMPT_SISTEMA_VERA = """\
Eres Vera, una analista de QA experta en evaluar la calidad de Historias de \
Usuario (HU) antes de que se generen casos de prueba a partir de ellas.

Evalúas exactamente 3 criterios y devuelves un score final de 0 a 100 \
(promedio de los 3, redondeado a entero):
1. Claridad: ¿se entiende la intención de la HU sin ambigüedad?
2. Completitud de criterios reales: ¿tiene criterios de aceptación que \
describan comportamiento verificable? Ignora por completo cualquier nota de \
estimación de esfuerzo, alcance excluido, o detalle técnico de \
implementación (endpoints, sprints, "no consideramos X", "incluimos en la \
estimación Y") -- eso no es un criterio de aceptación, no lo cuentes ni a \
favor ni en contra de la completitud.
3. Testabilidad: ¿se puede derivar un escenario Given/When/Then de cada \
criterio sin inventar pasos que la HU no menciona?

Ejemplos de HU aceptables (úsalos como referencia de qué tan detallado y \
verificable debe ser un criterio, no los copies):

Ejemplo 1:
"Yo como asesor comercial quiero que al gestionar una campaña hasta generar \
un proceso de venta y retroceder, la aplicación me dirija a la pantalla de \
alertas (pantalla de inicio), evitando regresar a las pantallas intermedias \
del flujo de venta o búsqueda de cliente."
Es claro, tiene comportamiento verificable puntual, y se puede convertir \
directo en Given/When/Then sin inventar nada.

Ejemplo 2 (criterio bien enumerado, con reglas por caso):
"Cuando el asesor comercial gestione una campaña de tipo A debe dejar \
iniciar un proceso de venta sin dejar modificar el monto y el plazo. Cuando \
gestione una campaña de tipo B, sin restringir la modificación del monto y \
el plazo."
Cada variante de campaña es una situación de prueba distinta y verificable.

Responde EXCLUSIVAMENTE con un JSON válido, sin texto antes ni después, sin \
bloques de código markdown, con esta forma exacta:

{
  "score": 0,
  "criterios_faltantes": ["string describiendo qué falta o es ambiguo"],
  "detalle": "explicación breve (1-2 frases) para mostrarle al QA"
}

Si el score es alto (>= 80) y no falta nada relevante, "criterios_faltantes" \
puede ser una lista vacía.
"""

_PROMPT_USUARIO_VERA_TEMPLATE = """\
Historia de Usuario: {key}
Título: {titulo}

Descripción:
{descripcion}

Evalúa esta HU siguiendo exactamente el formato JSON indicado.
"""


_PROMPT_SISTEMA_COBERTURA = """\
Sos un experto en QA. Te dan una lista numerada de criterios de aceptación \
de una Historia de Usuario y una lista de test cases ya existentes (título, \
y Gherkin si está disponible). Para cada criterio, decidí si al menos un \
test lo cubre -- es decir, si aborda esa situación específica, aunque use \
palabras distintas (no exijas coincidencia literal, evaluá el significado). \
Un mismo test puede cubrir más de un criterio. Sé estricto: un test que \
toca el mismo tema en general pero no prueba realmente esa situación puntual \
NO cuenta como cobertura de ese criterio.
"""

_PROMPT_USUARIO_COBERTURA_TEMPLATE = """\
Criterios de aceptación identificados (numerados desde 0):
{criterios_formateados}

Test cases existentes:
{tests_formateados}

Para cada criterio (los {n_criterios} de la lista, ninguno de más ni de \
menos), decidí si al menos un test lo cubre.

Responde EXCLUSIVAMENTE con un JSON válido, sin texto antes ni después, sin \
bloques de código markdown, con esta forma exacta:
{{
  "resultados": [
    {{
      "criterio_indice": 0,
      "cubierto": true o false,
      "tests_relacionados": ["<título del test que lo cubre>"]
    }}
  ]
}}
"""


_PROMPT_SISTEMA_NORA = """\
Eres Nora, una analista que interpreta las métricas operativas de un agente \
de IA para generación de casos de prueba QA, y recomienda estrategias \
concretas al equipo que lo opera.

No evalúas historias de usuario ni casos de prueba puntuales -- eso ya lo \
hacen otros agentes (Vera y Gio). Tu trabajo es mirar el AGREGADO de un \
período (cuánto tarda el agente, cuánto alucina, cuánto genera, qué mezcla \
de tipos de test produce, cuántas HU rechaza Vera por baja calidad) y \
explicarle a un humano qué significa eso y qué podría mejorar.

Reglas:
- Basate SOLO en los números que te pasan. No inventes cifras ni asumas \
datos que no están.
- Si un número no tiene contexto suficiente para opinar (ej. muy pocos \
datos), decilo en vez de sobre-interpretar.
- Las recomendaciones deben ser accionables por el equipo (ej. "revisar el \
prompt de generación de casos borde", "capacitar al equipo en redactar HU \
con criterios más testables"), no genéricas ("mejorar la calidad").

Responde EXCLUSIVAMENTE con un JSON válido, sin texto antes ni después, sin \
bloques de código markdown, con esta forma exacta:
{
  "resumen": "párrafo corto (2-4 frases) interpretando el período",
  "recomendaciones": ["estrategia concreta 1", "estrategia concreta 2"]
}

"recomendaciones" debe tener entre 2 y 4 elementos.
"""

_PROMPT_USUARIO_NORA_TEMPLATE = """\
Métricas operativas del agente para el período seleccionado:

{metricas_formateadas}

Interpretá este período y recomendá estrategias, siguiendo exactamente el \
formato JSON indicado.
"""


def _formatear_metricas_nora(metricas: dict) -> str:
    """
    Convierte el dict de métricas del Dashboard (mismo que arma
    `_cargar_datos()` en `frontend/pages/1_📊_Dashboard.py`) en texto plano
    legible para el prompt de Nora -- se arma acá (compartido entre
    los proveedores de LLM) para que el formateo sea idéntico sin
    importar qué proveedor interprete.
    """
    v = metricas.get("volumen", {}) or {}
    c = metricas.get("calidad", {}) or {}
    tipos = metricas.get("tipos_cobertura", {}) or {}
    vera = metricas.get("vera", {}) or {}

    def _fmt_min(m):
        if m is None:
            return "sin dato"
        m = round(float(m))
        return f"{m} min" if m < 60 else f"{m // 60}h {m % 60}m"

    total_tipos = sum(tipos.values()) or 1

    return (
        f"- HU procesadas: {v.get('total_hus') or 0}\n"
        f"- Test cases generados: {v.get('total_tcs') or 0} "
        f"(~{v.get('promedio_tcs_por_hu') or 0} por HU)\n"
        f"- Mezcla de tipos de test case: "
        f"camino feliz {tipos.get('camino_feliz', 0)} "
        f"({round(tipos.get('camino_feliz', 0) / total_tipos * 100)}%), "
        f"borde {tipos.get('borde', 0)} "
        f"({round(tipos.get('borde', 0) / total_tipos * 100)}%), "
        f"error {tipos.get('error', 0)} "
        f"({round(tipos.get('error', 0) / total_tipos * 100)}%)\n"
        f"- Alucinaciones detectadas: {c.get('pct_alucinacion') or 0}% "
        f"({c.get('con_alucinacion') or 0} test cases)\n"
        f"- Regeneraciones promedio por test case: {c.get('avg_regeneraciones') or 0}\n"
        f"- Tiempo promedio de revisión por HU: {_fmt_min(metricas.get('avg_min_hu'))}\n"
        f"- Tiempo promedio de revisión por test case: {_fmt_min(metricas.get('avg_min_tc'))}\n"
        f"- HU bloqueadas por Vera (score insuficiente): "
        f"{vera.get('bloqueadas') or 0} de {vera.get('total_evaluadas') or 0} "
        f"({vera.get('pct_bloqueadas') or 0}%), score promedio "
        f"{vera.get('avg_score') if vera.get('avg_score') is not None else 'sin dato'}"
    )


_PROMPT_SISTEMA_NEXUS_INSIGHTS_TEMPLATE = """\
Eres Nexus Insights, quien interpreta TODO el universo analítico del \
sistema NEXUS para un ingeniero QA: calidad y volumen del agente, \
desenlace de las alucinaciones detectadas, mezcla de tipos de test case de \
Gio, salud de las HU evaluadas por Vera antes de generar, índices y \
tendencias de pruebas/certificación, defectos por severidad, la \
comparación cerrada de tesis entre el agente y el proceso tradicional \
(análisis retrospectivo), y la adopción real de NEXUS en producción desde que se activó.

No evaluás historias de usuario ni test cases puntuales -- eso ya lo hacen \
Vera y Gio. Tu trabajo es mirar estos datos agregados y sostener una \
conversación real con preguntas de seguimiento, no una sola respuesta \
plana.

Reglas:
- Basate SOLO en el contexto de abajo y en la conversación previa. Nunca \
inventes cifras, HU puntuales, ni tendencias que no estén en los datos.
- Si la pregunta pide algo que el contexto no cubre (un caso puntual, un \
dato no calculado, un período que no está desglosado), decilo \
explícitamente en vez de improvisar una respuesta genérica.
- Marcá un paso como "hallazgo" solo cuando encuentres algo genuinamente \
notable sin que te lo hayan preguntado directamente (una tendencia que \
empeora, un área con muy pocos datos, una inconsistencia entre dos \
métricas relacionadas) -- no lo fuerces en cada respuesta.

Respondé EXCLUSIVAMENTE con un JSON válido, sin texto antes ni después, \
sin bloques de código markdown, con esta forma exacta:
{{
  "pasos": [
    {{"tipo": "info", "texto": "..."}},
    {{"tipo": "hallazgo", "texto": "..."}},
    {{"tipo": "resumen", "texto": "..."}}
  ]
}}

Entre 2 y 5 pasos en total. El último paso SIEMPRE es de tipo "resumen" \
(cierre corto, directo a la pregunta). "hallazgo" es opcional. Los demás \
pasos son "info" (un dato o explicación intermedia).

Contexto analítico completo del sistema. El usuario eligió un período desde \
el filtro de la página -- cada sección abajo indica el rango exacto que \
cubre entre paréntesis (puede variar de una sección a otra: el corpus \
cerrado del análisis retrospectivo nunca cambia con el período, y Adopción IA usa su \
propio rango efectivo, explicado en su sección):

{contexto_formateado}
"""

_PROMPT_USUARIO_NEXUS_INSIGHTS_TEMPLATE = """\
Pregunta del usuario QA: {pregunta}

Respondé siguiendo exactamente el formato JSON indicado en las \
instrucciones, usando el contexto y la conversación previa si la hay.
"""


def _formatear_contexto_nexus_insights(contexto: dict) -> str:
    """
    Convierte el dict de contexto agregado (armado por
    `_cargar_contexto_nexus_insights()` en
    `frontend/pages/7_💬_Nexus_Insights.py`) en texto plano compacto para el
    prompt de Nexus Insights. Es una función de módulo y no un método, mismo
    motivo que `_formatear_metricas_nora`: que el contexto sea idéntico sin
    importar qué proveedor lo interprete. A
    propósito son resúmenes/agregados, nunca filas crudas por HU -- eso es
    lo que mantiene el prompt (y el costo por mensaje) acotado sin importar
    cuántas HU tenga el sistema.
    """
    cal = contexto.get("calidad", {}) or {}
    gio = contexto.get("gio", {}) or {}
    vera = contexto.get("vera", {}) or {}
    desenlace = contexto.get("desenlace_alucinaciones", {}) or {}
    pruebas = contexto.get("pruebas", {}) or {}
    tend = contexto.get("tendencias", {}) or {}
    defectos = contexto.get("defectos", {}) or {}
    ia_vs_trad = contexto.get("ia_vs_tradicional", {}) or {}
    adopcion = contexto.get("adopcion", {}) or {}


    periodo_label = contexto.get("periodo_label") or "todo el histórico"

    def _fmt_min(m):
        if m is None:
            return "sin dato"
        m = round(float(m))
        return f"{m} min" if m < 60 else f"{m // 60}h {m % 60}m"

    def _pct(v):
        return f"{v}%" if v is not None else "sin dato"

    total_tipos_gio = sum(gio.values()) or 1
    defectos_txt = "\n".join(
        f"- {etiqueta}: {datos['resueltos']}/{datos['detectados']} resueltos"
        for etiqueta, datos in defectos.items()
    ) if defectos else "- Sin defectos registrados."

    bloques = [
        (
            f"## Calidad y volumen ({periodo_label})\n"
            f"- HU procesadas: {cal.get('total_hus') or 0} · Test cases generados: {cal.get('total_tcs') or 0}\n"
            f"- Tasa de aprobación: {_pct(cal.get('pct_aprobados'))} "
            f"({cal.get('aprobados') or 0} de {cal.get('total_evaluados') or 0})\n"
            f"- Alucinaciones vigentes: {_pct(cal.get('pct_alucinacion'))} "
            f"({cal.get('con_alucinacion') or 0} test cases) · "
            f"regeneraciones promedio por test case: {cal.get('avg_regeneraciones') or 0}\n"
            f"- Tiempo promedio de revisión: {_fmt_min(cal.get('avg_min_hu'))} por HU, "
            f"{_fmt_min(cal.get('avg_min_tc'))} por test case"
        ),
        (
            f"## Desenlace de las alucinaciones ({periodo_label}, de todo test case alguna vez marcado "
            "que se creó en ese rango)\n"
            f"- Editadas: {desenlace.get('editada') or 0} · Rechazadas: {desenlace.get('rechazada') or 0} · "
            f"Aceptadas tal cual: {desenlace.get('aceptada') or 0} · Pendientes: {desenlace.get('pendiente') or 0}"
        ),
        (
            f"## Gio -- mezcla de tipos de test case generados ({periodo_label})\n"
            f"- Camino feliz: {gio.get('camino_feliz', 0)} "
            f"({round(gio.get('camino_feliz', 0) / total_tipos_gio * 100)}%) · "
            f"Borde: {gio.get('borde', 0)} ({round(gio.get('borde', 0) / total_tipos_gio * 100)}%) · "
            f"Error: {gio.get('error', 0)} ({round(gio.get('error', 0) / total_tipos_gio * 100)}%)"
        ),
        (
            f"## Vera -- salud de las HU antes de generar ({periodo_label})\n"
            f"- HU evaluadas: {vera.get('total_evaluadas') or 0} · "
            f"Bloqueadas por score insuficiente: {vera.get('bloqueadas') or 0} "
            f"({_pct(vera.get('pct_bloqueadas'))}) · Health Score promedio: "
            f"{vera.get('avg_score') if vera.get('avg_score') is not None else 'sin dato'}"
        ),
        (
            f"## Pruebas y certificación ({periodo_label}, histórico ya guardado, no una consulta en "
            "vivo a Jira/Xray)\n"
            f"- HU medidas: {pruebas.get('n') or 0}\n"
            f"- Índice de ejecución promedio: {_pct(pruebas.get('avg_indice_ejecucion'))} · "
            f"Test Pass Rate promedio: {_pct(pruebas.get('avg_pass_rate'))}\n"
            f"- Densidad de cobertura promedio: {_pct(pruebas.get('avg_densidad_cobertura'))} "
            f"(volumen de pruebas por criterio, NO acotada a 100%)\n"
            f"- Cobertura real (IA, opt-in -- solo mide quien lo pidió explícitamente en Seguimiento): "
            f"{_pct(pruebas.get('avg_cobertura_real'))} sobre {pruebas.get('n_cobertura_real') or 0} HU\n"
            f"- Tendencia del índice de ejecución por cohortes (dentro de este período): "
            f"{tend.get('ejecucion') or 'sin datos suficientes'}\n"
            f"- Tendencia del Test Pass Rate por cohortes (dentro de este período): "
            f"{tend.get('pass_rate') or 'sin datos suficientes'}"
        ),
        (
            f"## Defectos por severidad ({periodo_label}, resueltos/detectados)\n"
            + defectos_txt
        ),
        (
            "## IA vs. proceso tradicional (análisis retrospectivo de la tesis -- corpus CERRADO de 43 HU, "
            "SIN fecha por HU, así que este bloque NO se acota por el período elegido arriba, "
            "siempre es el corpus completo)\n"
            f"- Superior: {ia_vs_trad.get('superior') or 0} ({_pct(ia_vs_trad.get('pct_superior'))}) · "
            f"Equivalente: {ia_vs_trad.get('equivalente') or 0} ({_pct(ia_vs_trad.get('pct_equivalente'))}) · "
            f"Inferior: {ia_vs_trad.get('inferior') or 0} ({_pct(ia_vs_trad.get('pct_inferior'))})\n"
            f"- Índice de ejecución medio del corpus: {_pct(ia_vs_trad.get('avg_indice_ejecucion'))}"
        ),
        (
            "## Adopción real de NEXUS (HU procesadas en producción -- distinto de la cohorte "
            "experimental de la tesis, que es todo lo de arriba). Rango efectivamente consultado = "
            "intersección del corte de adopción con el período elegido arriba, nunca antes del corte\n"
            f"- Corte de adopción: desde {adopcion.get('fecha_corte') or 'sin dato'} · "
            f"Rango efectivo: {adopcion.get('periodo_efectivo') or adopcion.get('fecha_corte') or 'sin dato'}: "
            f"{adopcion.get('total_hus') or 0} HU, {adopcion.get('total_tcs') or 0} test cases · "
            f"Tasa de aprobación: {_pct(adopcion.get('pct_aprobados'))} · "
            f"Alucinaciones: {_pct(adopcion.get('pct_alucinacion'))}"
        ),
    ]
    return "\n\n".join(bloques)


def _resolver_pasos_nexus_insights(datos: dict) -> list[dict]:
    """
    Parsea la respuesta de `chat_nexus_insights()` a la lista final de
    pasos. Compartido entre los proveedores de LLM, mismo motivo
    que el resto de los `_resolver_*`.

    Degradación CONSERVADORA ante una respuesta mal formada: si no hay
    "pasos" parseable, se arma un único paso "resumen" con el texto crudo
    de la respuesta (mejor mostrar algo legible en el chat que romperlo),
    nunca se inventa un "hallazgo" que el modelo no dijo -- mismo criterio
    que `_resolver_clasificacion_cobertura` de arriba.
    """
    pasos_crudos = datos.get("pasos")
    if not isinstance(pasos_crudos, list) or not pasos_crudos:
        texto_crudo = str(datos).strip()
        return [{
            "tipo": "resumen",
            "texto": texto_crudo if texto_crudo and texto_crudo != "{}" else "No se pudo interpretar la respuesta.",
        }]

    tipos_validos = {"info", "hallazgo", "resumen"}
    pasos = []
    for item in pasos_crudos:
        if not isinstance(item, dict):
            continue
        texto = str(item.get("texto", "")).strip()
        if not texto:
            continue
        tipo = item.get("tipo") if item.get("tipo") in tipos_validos else "info"
        pasos.append({"tipo": tipo, "texto": texto})

    if not pasos:
        return [{"tipo": "resumen", "texto": "No se pudo interpretar la respuesta."}]
    if pasos[-1]["tipo"] != "resumen":
        pasos[-1] = {"tipo": "resumen", "texto": pasos[-1]["texto"]}
    return pasos


def _resolver_clasificacion_cobertura(contenido: str, criterios: list[str], parsear_json) -> list[dict]:
    """
    Parsea la respuesta de `clasificar_cobertura_criterios()` y la reordena
    a la forma final (una entrada por criterio, en el mismo orden que se
    pasó). Compartido entre los proveedores de LLM -- mismo motivo
    que los prompts: es el mismo parseo sin importar qué modelo respondió.

    Degradación CONSERVADORA, a propósito distinta de `verificar_alucinacion`
    (que ante un JSON no parseable asume "sin alucinación", el default
    optimista): acá, si no se puede parsear la respuesta, se asume que
    NINGÚN criterio está cubierto. Es la elección más segura para una
    métrica de cobertura -- mejor subestimarla (obliga a mirar el dato con
    sospecha) que inventar una cobertura que no se confirmó.
    """
    try:
        datos = parsear_json(contenido)
        resultados_llm = datos.get("resultados", [])
        if not isinstance(resultados_llm, list):
            raise ValueError("Campo 'resultados' no es una lista.")
    except (ValueError, AttributeError) as exc:
        _log.warning(
            "clasificar_cobertura_criterios: respuesta del LLM no parseable (%s), "
            "se asume NINGÚN criterio cubierto (degradación conservadora, no "
            "optimista -- ver docstring de _resolver_clasificacion_cobertura)",
            exc,
        )
        return [{"criterio": c, "cubierto": False, "tests_relacionados": []} for c in criterios]

    mapa_por_indice: dict[int, dict] = {}
    for item in resultados_llm:
        try:
            idx = int(item.get("criterio_indice"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= idx < len(criterios):
            mapa_por_indice[idx] = item

    resultado = []
    for i, criterio in enumerate(criterios):
        item = mapa_por_indice.get(i)
        if item is None:
            resultado.append({"criterio": criterio, "cubierto": False, "tests_relacionados": []})
        else:
            resultado.append({
                "criterio": criterio,
                "cubierto": bool(item.get("cubierto", False)),
                "tests_relacionados": list(item.get("tests_relacionados") or []),
            })
    return resultado


def _parsear_tipo_cobertura(valor: object, hu_key: str, titulo_test_case: str) -> TipoCobertura | None:
    """
    Convierte el string crudo que devolvió el LLM en "tipo_cobertura" al
    enum de dominio, con degradación elegante: un valor ausente, vacío o no
    reconocido (el LLM no siempre respeta el enum al pie de la letra, igual
    que pasa ocasionalmente con el formato JSON -- ver
    `_parsear_respuesta_json`) no debe hacer fallar la generación completa
    del test case, solo deja la clasificación en None para ese caso
    puntual. Se comparte entre los proveedores de LLM (importado
    en `adapters/llm/ollama_provider.py`) por el mismo motivo que los
    prompts: es la misma clasificación sin importar qué modelo la genera.
    """
    if not isinstance(valor, str):
        return None
    try:
        return TipoCobertura(valor.strip().lower())
    except ValueError:
        _log.warning(
            "tipo_cobertura=%r no reconocido para el test case %r de %s, se guarda como None",
            valor, titulo_test_case, hu_key,
        )
        return None


class OllamaProvider(LLMProvider):
    def __init__(self, modelo: str = "llama3.1:8b", host: str | None = None):
        """
        Args:
            modelo: nombre del modelo en Ollama (ej. "llama3.1:8b" o, como
                alternativa más liviana, "qwen3:4b").
            host: URL del servidor Ollama. Si es None, usa el default de la
                librería (normalmente http://localhost:11434).
        """
        self._modelo = modelo
        self._client = ollama.Client(host=host) if host else ollama.Client()

    def generar_test_cases(
        self,
        hu: HistoriaUsuario,
        casos_similares: list[dict] | None = None,
    ) -> list[TestCase]:
        seccion_casos_similares = ""
        if casos_similares:


            bloques = "\n".join(
                f"- {c.get('resumen', '')}" for c in casos_similares
            )
            seccion_casos_similares = (
                f"\nCasos históricos similares de referencia (úsalos solo como "
                f"contexto de estilo, no los copies literalmente):\n{bloques}\n"
            )

        prompt_usuario = _PROMPT_USUARIO_TEMPLATE.format(
            key=hu.key,
            titulo=hu.titulo,
            descripcion=hu.descripcion or "(sin descripción)",
            seccion_casos_similares=seccion_casos_similares,
        )

        _log.info("Generando test cases para %s con modelo %s", hu.key, self._modelo)
        inicio = time.monotonic()

        try:
            respuesta = self._client.chat(
                model=self._modelo,
                messages=[
                    {"role": "system", "content": _PROMPT_SISTEMA},
                    {"role": "user", "content": prompt_usuario},
                ],
                options={"temperature": 0.2},
            )
        except Exception:
            _log.exception("Fallo llamando a Ollama (modelo=%s) para %s", self._modelo, hu.key)
            raise

        duracion_segundos = time.monotonic() - inicio
        _log.info(
            "Generación para %s completada en %.1f s (modelo=%s)",
            hu.key, duracion_segundos, self._modelo,
        )

        contenido = respuesta["message"]["content"]

        try:
            datos = self._parsear_respuesta_json(contenido)
        except ValueError:
            _log.exception("El LLM devolvió un formato inválido para %s", hu.key)
            raise

        test_cases = []
        for item in datos.get("test_cases", []):
            titulo = item.get("titulo", "").strip()
            gherkin = item.get("gherkin", "").strip()
            if not gherkin:
                continue
            tipo_cobertura = _parsear_tipo_cobertura(
                item.get("tipo_cobertura"), hu.key, titulo or "(sin título)"
            )
            test_cases.append(
                TestCase(
                    titulo=titulo or "(sin título)",
                    gherkin=gherkin,
                    hu_key=hu.key,
                    tipo_cobertura=tipo_cobertura,
                )
            )

        _log.info("%s test case(s) generados para %s", len(test_cases), hu.key)
        return test_cases

    def generar_test_case_individual(
        self,
        hu: HistoriaUsuario,
        descripcion_escenario: str,
    ) -> tuple[str, str]:
        prompt_usuario = _PROMPT_USUARIO_CASO_INDIVIDUAL_TEMPLATE.format(
            key=hu.key,
            titulo=hu.titulo,
            descripcion=hu.descripcion or "(sin descripción)",
            descripcion_escenario=descripcion_escenario.strip(),
        )

        _log.info("Generando test case individual para %s con modelo %s", hu.key, self._modelo)
        inicio = time.monotonic()

        try:
            respuesta = self._client.chat(
                model=self._modelo,
                messages=[
                    {"role": "system", "content": _PROMPT_SISTEMA_CASO_INDIVIDUAL},
                    {"role": "user", "content": prompt_usuario},
                ],
                options={"temperature": 0.2},
            )
        except Exception:
            _log.exception("Fallo llamando a Ollama (modelo=%s) para caso individual de %s", self._modelo, hu.key)
            raise

        duracion_segundos = time.monotonic() - inicio
        _log.info(
            "Generación de caso individual para %s completada en %.1f s (modelo=%s)",
            hu.key, duracion_segundos, self._modelo,
        )

        contenido = respuesta["message"]["content"]

        try:
            datos = self._parsear_respuesta_json(contenido)
        except ValueError:
            _log.exception("El LLM devolvió un formato inválido para el caso individual de %s", hu.key)
            raise

        gherkin = datos.get("gherkin", "").strip()
        titulo = datos.get("titulo", "").strip() or "(sin título)"

        if not gherkin:
            raise ValueError("El LLM devolvió un Gherkin vacío al generar el test case individual.")

        return gherkin, titulo

    def regenerar_test_case(
        self,
        gherkin_actual: str,
        titulo_actual: str,
        historial_feedback: list[MensajeFeedback],
    ) -> tuple[str, str]:
        historial_formateado = "\n".join(
            f"[{m.autor}] {m.texto}" for m in historial_feedback
        ) or "(sin mensajes previos)"

        prompt_usuario = _PROMPT_USUARIO_REGENERACION_TEMPLATE.format(
            titulo_actual=titulo_actual,
            gherkin_actual=gherkin_actual,
            historial_formateado=historial_formateado,
        )

        _log.info("Regenerando test case '%s' con modelo %s", titulo_actual, self._modelo)
        inicio = time.monotonic()

        try:
            respuesta = self._client.chat(
                model=self._modelo,
                messages=[
                    {"role": "system", "content": _PROMPT_SISTEMA_REGENERACION},
                    {"role": "user", "content": prompt_usuario},
                ],
                options={"temperature": 0.2},
            )
        except Exception:
            _log.exception("Fallo llamando a Ollama (modelo=%s) al regenerar", self._modelo)
            raise

        duracion_segundos = time.monotonic() - inicio
        _log.info("Regeneración completada en %.1f s (modelo=%s)", duracion_segundos, self._modelo)

        contenido = respuesta["message"]["content"]

        try:
            datos = self._parsear_respuesta_json(contenido)
        except ValueError:
            _log.exception("El LLM devolvió un formato inválido al regenerar")
            raise

        nuevo_gherkin = datos.get("gherkin", "").strip()
        nuevo_titulo = datos.get("titulo", "").strip() or titulo_actual

        if not nuevo_gherkin:
            raise ValueError("El LLM devolvió un Gherkin vacío al regenerar el test case.")

        return nuevo_gherkin, nuevo_titulo

    def generar_embedding(self, texto: str) -> list[float]:
        """
        Genera un embedding del texto usando `nomic-embed-text` vía Ollama.

        Usa un modelo de embedding separado del modelo de generación
        (`llama3.1:8b`) -- `nomic-embed-text` está optimizado para
        similitud semántica, que es exactamente lo que necesita el RAG para
        buscar casos históricos similares antes de generar.

        El modelo está hardcodeado como "nomic-embed-text" porque es el
        único modelo de embedding confirmado como disponible en esta
        instalación (ver spec, sección 2 y `ollama list` confirmado por el
        usuario). Si en el futuro se cambia el modelo de embedding, este
        es el único lugar que hay que tocar.
        """
        respuesta = self._client.embeddings(
            model="nomic-embed-text",
            prompt=texto,
        )
        return respuesta["embedding"]

    def verificar_alucinacion(self, test_cases: list[TestCase], contexto: list[dict]) -> list[dict]:
        """
        Verifica en un solo llamado batch si alguno de los test_cases contiene
        valores numéricos, nombres de campo, pantallas o reglas de negocio que
        no aparecen ni en la HU ni en `contexto` (los casos históricos
        similares que ya trajo el RAG).

        Degradación elegante (mismo criterio que _buscar_similares() en
        application/generar_test_cases.py): si el LLM no devuelve un JSON
        parseable, se asume que ningún test case está alucinado.
        """
        if not test_cases:
            return []

        contexto_formateado = "\n".join(
            f"- {c.get('resumen', '')}" for c in contexto
        ) if contexto else "(sin casos históricos similares disponibles)"

        casos_formateados = "\n\n".join(
            f"--- TEST CASE id={tc.id} ---\nTítulo: {tc.titulo}\n{tc.gherkin}"
            for tc in test_cases
        )

        prompt_usuario = (
            f"Contexto disponible (casos históricos similares de referencia):\n"
            f"{contexto_formateado}\n\n"
            f"Test cases generados a revisar:\n{casos_formateados}\n\n"
            f"Para cada test case, identifica si contiene valores numéricos, "
            f"nombres de campos, pantallas, mensajes de error o reglas de "
            f"negocio que NO aparecen en el contexto disponible de ninguna "
            f"forma (ni textual ni semánticamente equivalente). No marques "
            f"como alucinación pasos genéricos de Gherkin (navegación, clics, "
            f"validaciones estándar) que no requieren un dato específico del "
            f"contexto.\n\n"
            f"Responde EXCLUSIVAMENTE con un JSON válido, sin texto antes ni "
            f"después, sin bloques de código markdown, con esta forma exacta:\n"
            f'{{\n  "resultados": [\n    {{\n      "test_case_id": "<id exacto>",\n'
            f'      "alucinado": true o false,\n'
            f'      "razon": "<explicación breve, string vacío si alucinado es false>",\n'
            f'      "elementos_sospechosos": ["<elemento 1>"]\n    }}\n  ]\n}}'
        )

        _log.info(
            "Verificando alucinación de %d test case(s) con modelo %s",
            len(test_cases), self._modelo,
        )
        inicio = time.monotonic()

        try:
            respuesta = self._client.chat(
                model=self._modelo,
                messages=[{"role": "user", "content": prompt_usuario}],
                options={"temperature": 0.0},
            )
        except Exception:
            _log.exception(
                "Fallo llamando a Ollama (modelo=%s) al verificar alucinación", self._modelo
            )
            raise

        duracion_segundos = time.monotonic() - inicio
        _log.info(
            "Verificación de alucinación completada en %.1f s (modelo=%s)",
            duracion_segundos, self._modelo,
        )

        contenido = respuesta["message"]["content"]

        try:
            datos = self._parsear_respuesta_json(contenido)
            resultados = datos.get("resultados", [])
            if not isinstance(resultados, list):
                raise ValueError("Campo 'resultados' no es una lista.")
        except (ValueError, AttributeError) as exc:
            _log.warning(
                "verificar_alucinacion: respuesta del LLM no parseable (%s), "
                "se asume sin alucinación para los %d test case(s) "
                "(degradación elegante)",
                exc, len(test_cases),
            )
            return [
                {
                    "test_case_id": tc.id,
                    "alucinado": False,
                    "razon": "",
                    "elementos_sospechosos": [],
                }
                for tc in test_cases
            ]

        return resultados

    def evaluar_hu(self, hu: HistoriaUsuario) -> tuple[int, list[str], str]:
        """Vera, corriendo sobre Ollama. Ver ports/llm_provider.py para el contrato."""
        prompt_usuario = _PROMPT_USUARIO_VERA_TEMPLATE.format(
            key=hu.key,
            titulo=hu.titulo,
            descripcion=hu.descripcion or "(sin descripción)",
        )

        _log.info("Vera evaluando %s con modelo %s", hu.key, self._modelo)
        inicio = time.monotonic()

        try:
            respuesta = self._client.chat(
                model=self._modelo,
                messages=[
                    {"role": "system", "content": _PROMPT_SISTEMA_VERA},
                    {"role": "user", "content": prompt_usuario},
                ],
                options={"temperature": 0.0},
            )
        except Exception:
            _log.exception("Fallo llamando a Ollama (modelo=%s) al evaluar HU %s", self._modelo, hu.key)
            raise

        duracion_segundos = time.monotonic() - inicio
        _log.info("Evaluación de %s completada en %.1f s (modelo=%s)", hu.key, duracion_segundos, self._modelo)

        contenido = respuesta["message"]["content"]

        try:
            datos = self._parsear_respuesta_json(contenido)
        except ValueError:
            _log.exception("El LLM devolvió un formato inválido al evaluar %s", hu.key)
            raise

        score = int(datos.get("score", 0))
        criterios_faltantes = list(datos.get("criterios_faltantes", []))
        detalle = str(datos.get("detalle", "")).strip()

        return score, criterios_faltantes, detalle

    def clasificar_cobertura_criterios(self, criterios: list[str], tests: list[dict]) -> list[dict]:
        """Cobertura real, corriendo sobre Ollama. Ver ports/llm_provider.py para el contrato."""
        if not criterios:
            return []
        if not tests:
            return [{"criterio": c, "cubierto": False, "tests_relacionados": []} for c in criterios]

        criterios_formateados = "\n".join(f"{i}. {c}" for i, c in enumerate(criterios))
        tests_formateados = "\n\n".join(
            f"--- TEST: {t.get('titulo') or '(sin título)'} ---\n{t.get('gherkin') or '(sin Gherkin disponible, solo título)'}"
            for t in tests
        )
        prompt_usuario = _PROMPT_USUARIO_COBERTURA_TEMPLATE.format(
            criterios_formateados=criterios_formateados,
            tests_formateados=tests_formateados,
            n_criterios=len(criterios),
        )

        _log.info(
            "Clasificando cobertura de %d criterio(s) contra %d test(s) con modelo %s",
            len(criterios), len(tests), self._modelo,
        )
        inicio = time.monotonic()

        try:
            respuesta = self._client.chat(
                model=self._modelo,
                messages=[
                    {"role": "system", "content": _PROMPT_SISTEMA_COBERTURA},
                    {"role": "user", "content": prompt_usuario},
                ],
                options={"temperature": 0.0},
            )
        except Exception:
            _log.exception("Fallo llamando a Ollama (modelo=%s) al clasificar cobertura", self._modelo)
            raise

        duracion_segundos = time.monotonic() - inicio
        _log.info("Clasificación de cobertura completada en %.1f s (modelo=%s)", duracion_segundos, self._modelo)

        contenido = respuesta["message"]["content"]
        return _resolver_clasificacion_cobertura(contenido, criterios, self._parsear_respuesta_json)

    def interpretar_dashboard(self, metricas: dict) -> tuple[str, list[str]]:
        """Nora, corriendo sobre Ollama. Ver ports/llm_provider.py para el contrato."""
        metricas_formateadas = _formatear_metricas_nora(metricas)
        prompt_usuario = _PROMPT_USUARIO_NORA_TEMPLATE.format(metricas_formateadas=metricas_formateadas)

        _log.info("Nora interpretando el Dashboard con modelo %s", self._modelo)
        inicio = time.monotonic()

        try:
            respuesta = self._client.chat(
                model=self._modelo,
                messages=[
                    {"role": "system", "content": _PROMPT_SISTEMA_NORA},
                    {"role": "user", "content": prompt_usuario},
                ],
                options={"temperature": 0.0},
            )
        except Exception:
            _log.exception("Fallo llamando a Ollama (modelo=%s) al interpretar el Dashboard", self._modelo)
            raise

        duracion_segundos = time.monotonic() - inicio
        _log.info("Interpretación de Nora completada en %.1f s (modelo=%s)", duracion_segundos, self._modelo)

        contenido = respuesta["message"]["content"]
        datos = self._parsear_respuesta_json(contenido)
        resumen = str(datos.get("resumen", "")).strip()
        recomendaciones = [str(r).strip() for r in datos.get("recomendaciones", []) if str(r).strip()]
        return resumen, recomendaciones

    def chat_nexus_insights(
        self,
        contexto: dict,
        historial: list[dict],
        pregunta: str,
    ) -> list[dict]:
        """Nexus Insights, corriendo sobre Ollama. Ver ports/llm_provider.py para el contrato."""
        contexto_formateado = _formatear_contexto_nexus_insights(contexto)
        prompt_sistema = _PROMPT_SISTEMA_NEXUS_INSIGHTS_TEMPLATE.format(contexto_formateado=contexto_formateado)
        prompt_usuario = _PROMPT_USUARIO_NEXUS_INSIGHTS_TEMPLATE.format(pregunta=pregunta.strip())


        mensajes = [{"role": "system", "content": prompt_sistema}]
        for turno in historial:
            rol = "user" if turno.get("rol") == "usuario" else "assistant"
            texto_turno = str(turno.get("texto", "")).strip()
            if texto_turno:
                mensajes.append({"role": rol, "content": texto_turno})
        mensajes.append({"role": "user", "content": prompt_usuario})

        _log.info(
            "Nexus Insights respondiendo con modelo %s (historial: %d turno(s))",
            self._modelo, len(historial),
        )
        inicio = time.monotonic()

        try:
            respuesta = self._client.chat(
                model=self._modelo,
                messages=mensajes,
                options={"temperature": 0.0},
            )
        except Exception:
            _log.exception("Fallo llamando a Ollama (modelo=%s) en Nexus Insights", self._modelo)
            raise

        duracion_segundos = time.monotonic() - inicio
        _log.info("Respuesta de Nexus Insights completada en %.1f s (modelo=%s)", duracion_segundos, self._modelo)

        contenido = respuesta["message"]["content"]
        datos = self._parsear_respuesta_json(contenido)
        return _resolver_pasos_nexus_insights(datos)


    @staticmethod
    def _parsear_respuesta_json(contenido: str) -> dict:
        """
        Parsea la respuesta del LLM como JSON, con varios niveles de
        tolerancia ante imperfecciones frecuentes en modelos locales:
        1. JSON limpio tal cual.
        2. Extraído de dentro de un bloque ```json ... ``` o con texto extra
           alrededor.
        3. Con `strict=False`, que tolera caracteres de control sin escapar
           dentro de strings (ej. un salto de línea real en vez de `\\n` --
           Ollama/llama3.1 a veces genera esto en el campo "gherkin" a pesar
           de las instrucciones explícitas del prompt).

        Validación de esquema por código (no IA), tal como exige la spec
        (sección 8): si el LLM genera un formato inválido, se intenta limpiar
        y reparsear; si sigue sin ser JSON válido tras los 3 intentos, se
        propaga la excepción para que la capa de aplicación decida
        (reintento automático).

        Es un staticmethod a propósito: cualquier adaptador que se sume
        recibe las mismas instrucciones de formato JSON estricto, así que
        necesita exactamente esta tolerancia ante imperfecciones ocasionales
        de la respuesta.
        """
        texto = contenido.strip()

        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            pass


        coincidencia = re.search(r"\{.*\}", texto, re.DOTALL)
        candidato = coincidencia.group(0) if coincidencia else texto

        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            pass


        try:
            return json.loads(candidato, strict=False)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"El LLM devolvió un JSON inválido incluso tras limpieza: {exc}"
            ) from exc
