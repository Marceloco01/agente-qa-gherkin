"""
Port (contrato) para cualquier proveedor de LLM.

Esta interfaz es el "qué", no el "cómo": define qué necesita la capa de
aplicación de un LLM, sin saber qué motor hay por debajo. `application/` y
`domain/` dependen de esta interfaz, nunca de una implementación concreta.

Fase 1: solo se implementa `generar_test_cases()`.
Fase 2 (chat de feedback, agregar caso manual): se implementan
`regenerar_test_case()` y `generar_test_case_individual()`.
Fase 3 (RAG): se implementa `generar_embedding()`.
Fase 4 (calidad): se implementa `verificar_alucinacion()`.
Fase de agentes humanizados: se implementa `evaluar_hu()` (Vera).

El proveedor activo se resuelve por configuración en
`infrastructure/fabrica_llm.py`; hoy la implementación es Ollama local. Todo
adaptador que se incorpore cumple este contrato sin excepción, que es lo que
permite cambiar de motor sin tocar los casos de uso.

Se define el contrato completo desde ya para que cualquier adapter concreto
no tenga que cambiar de forma entre fases, solo ir agregando implementación
real a métodos que hoy pueden quedar con NotImplementedError.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import HistoriaUsuario, MensajeFeedback, TestCase


class LLMProvider(ABC):
    @abstractmethod
    def generar_test_cases(
        self,
        hu: HistoriaUsuario,
        casos_similares: list[dict] | None = None,
    ) -> list[TestCase]:
        """
        Genera test cases en Gherkin a partir de una HU.

        Args:
            hu: la Historia de Usuario con título y descripción.
            casos_similares: casos históricos relevantes traídos por RAG
                (Fase 3+). En Fase 1 siempre es None o lista vacía: el LLM
                genera solo con el contexto de la HU.

        Returns:
            Lista de TestCase. La cantidad la decide el LLM según lo que la HU
            sugiera (no es un número fijo, ver spec sección 6, punto 5).
        """
        raise NotImplementedError

    @abstractmethod
    def generar_test_case_individual(
        self,
        hu: HistoriaUsuario,
        descripcion_escenario: str,
    ) -> tuple[str, str]:
        """
        Genera UN test case puntual a partir de una descripción libre del
        escenario que el usuario quiere cubrir (ej. "que pase si la
        contraseña tiene menos de 8 caracteres"), en vez de dejar que el LLM
        decida todos los casos de la HU.

        A diferencia de `generar_test_cases()` (genera varios, decide el LLM
        cuántos) y de `regenerar_test_case()` (corrige uno existente con
        feedback), este método crea un test case nuevo desde cero a partir de
        una idea puntual del usuario -- el caso de uso típico es "como
        experto QA, sé que falta cubrir X, quiero agregarlo yo".

        Args:
            hu: la HU, para que el LLM tenga el contexto completo (título +
                descripción) y no solo la frase suelta del escenario.
            descripcion_escenario: descripción en lenguaje natural de lo que
                el test case debe cubrir.

        Returns:
            Tupla (gherkin, titulo).
        """
        raise NotImplementedError

    @abstractmethod
    def regenerar_test_case(
        self,
        gherkin_actual: str,
        titulo_actual: str,
        historial_feedback: list[MensajeFeedback],
    ) -> tuple[str, str]:
        """
        Regenera un test case rechazado, considerando el feedback acumulado
        del chat libre QA↔Agente (spec, sección 6, paso 8 y sección 8, tabla
        de casos límite).

        Args:
            gherkin_actual: el Gherkin que el usuario rechazó.
            titulo_actual: el título actual del test case.
            historial_feedback: la conversación completa hasta ahora (no solo
                el último mensaje), para que el LLM tenga contexto de
                correcciones previas si las hubo.

        Returns:
            Tupla (nuevo_gherkin, nuevo_titulo).
        """
        raise NotImplementedError

    @abstractmethod
    def generar_embedding(self, texto: str) -> list[float]:
        """
        Genera el vector de embedding de un texto.

        Nota (fase de agentes humanizados): esto SIEMPRE corre contra
        `nomic-embed-text` vía Ollama, sin importar qué proveedor esté
        configurado como principal para el resto de las operaciones (ver
        `adapters/llm/ollama_provider.py`). Cambiar de modelo de embedding
        rompería la comparabilidad de los 768 valores ya guardados en
        `embeddings_historicos` -- no es una decisión de rendimiento, es de
        integridad de datos.
        """
        raise NotImplementedError

    @abstractmethod
    def verificar_alucinacion(
        self,
        test_cases: list[TestCase],
        contexto: list[dict],
    ) -> list[dict]:
        """
        Verifica, en un solo llamado batch, qué test cases tienen contenido no
        respaldado por el contexto (HU + casos de referencia del RAG).

        Fase 1: no se usa todavía (no hay verificación de alucinación). Se
        implementa en Fase 4.
        """
        raise NotImplementedError

    @abstractmethod
    def evaluar_hu(self, hu: HistoriaUsuario) -> tuple[int, list[str], str]:
        """
        Vera: evalúa la calidad de una HU en 3 criterios -- claridad,
        completitud de criterios de aceptación reales (sin contar notas de
        estimación/alcance no funcional) y testabilidad -- y devuelve un
        score promedio de 0 a 100.

        No evalúa dependencia de contenido visual (menciones a imágenes,
        capturas, adjuntos): ese chequeo es determinista y vive en
        `application/validar_hu.py` como código simple (regex), no como
        juicio del LLM -- así se evita gastar una llamada cuando ya se sabe
        que la HU depende de algo que el agente no puede leer (decisión de
        eficiencia adoptada para este diseño).

        Returns:
            Tupla (score de 0 a 100, lista de criterios faltantes o
            ambiguos, detalle en una o dos frases para mostrarle al QA). La
            decisión de si `score` alcanza el umbral de aprobación vive en
            `application/validar_hu.py` (configurable vía
            `UMBRAL_SCORE_HU`), no en el adapter.
        """
        raise NotImplementedError

    @abstractmethod
    def clasificar_cobertura_criterios(
        self,
        criterios: list[str],
        tests: list[dict],
    ) -> list[dict]:
        """
        Cobertura REAL de una HU (índice de cobertura del libro [29]:
        situaciones cubiertas / situaciones identificadas × 100) -- distinta
        de la "densidad" (num_tests/num_criterios) que se calcula sin LLM y
        que puede superar el 100%. Acá cada criterio de aceptación es una
        "situación identificada", y está "cubierto" si al menos un test
        existente lo aborda -- una decisión semántica que no se puede
        resolver por regex, por eso es el único punto de todo el índice de
        cobertura que pasa por un LLM.

        Usado por la página `frontend/pages/5_🎯_Seguimiento.py` (agente de
        seguimiento en vivo), NO por el corpus cerrado del análisis retrospectivo -- ahí
        la cobertura queda como densidad, ya congelada para la tesis.
        Decisión de diseño (2026-09-02).

        Args:
            criterios: los criterios de aceptación de la HU (texto plano),
                en el orden en que se reporta el resultado.
            tests: los test cases EXISTENTES en Xray para esa HU (no
                necesariamente generados por este agente -- pueden ser
                históricos, escritos a mano). Cada dict trae
                {"titulo": str, "gherkin": str} -- `gherkin` puede venir
                vacío si no se pudo confirmar ese campo en el schema de
                Xray; en ese caso la clasificación se apoya solo en el
                título.

        Returns:
            Lista de dicts, uno por criterio, en el MISMO orden que
            `criterios`: {"criterio": str, "cubierto": bool,
            "tests_relacionados": list[str]} (títulos de los tests que lo
            cubren, vacío si `cubierto` es False).

        Nota de no-determinismo (mismo criterio ya documentado con
        `HU-394`): dos corridas de la misma HU podrían clasificar un
        caso límite distinto. Por eso esto es opt-in en la página de
        Seguimiento (el usuario decide cuándo pagar ese costo de
        determinismo a cambio de un número acotado a 100% real), nunca se
        usa para recalcular el análisis retrospectivo ya cerrado.
        """
        raise NotImplementedError

    @abstractmethod
    def interpretar_dashboard(self, metricas: dict) -> tuple[str, list[str]]:
        """
        Nora: interpreta en lenguaje natural las métricas operativas del
        agente para un período dado (Dashboard, `frontend/pages/1_📊_Dashboard.py`)
        y recomienda estrategias concretas.

        Decisión de diseño (2026-09-02): el alcance de esta
        primera versión es SOLO operativo (cómo se está comportando el
        agente), no el criterio del QA sobre casos puntuales -- por eso
        `metricas` trae exactamente lo mismo que ya se muestra en el
        Dashboard (tiempos, alucinaciones, volumen y tipos de test cases,
        HU bloqueadas por Vera), nada nuevo que la UI no muestre ya. Es
        bajo demanda: el frontend cachea el resultado por período en
        `st.session_state` y solo llama a esto cuando el QA lo pide
        explícitamente (nunca en cada rerun de Streamlit -- ver
        `application/interpretar_dashboard.py`).

        Args:
            metricas: dict con las mismas claves que devuelve
                `_cargar_datos()` en el Dashboard (volumen, calidad,
                avg_min_hu, avg_min_tc, pct_subidos, tipos_cobertura, vera).

        Returns:
            Tupla (resumen, recomendaciones): `resumen` es un párrafo corto
            (2-4 frases) interpretando el período; `recomendaciones` es una
            lista de 2 a 4 estrategias concretas y accionables.
        """
        raise NotImplementedError

    @abstractmethod
    def chat_nexus_insights(
        self,
        contexto: dict,
        historial: list[dict],
        pregunta: str,
    ) -> list[dict]:
        """
        Nexus Insights: chat real sobre TODO el universo analítico de NEXUS
        (`frontend/pages/7_💬_Nexus_Insights.py`) -- calidad y volumen del
        agente, desenlace de alucinaciones, mezcla de tipos de Gio, salud de
        HU evaluada por Vera, índices y tendencias de pruebas/certificación,
        defectos por severidad, la comparación cerrada de tesis IA vs.
        proceso tradicional (análisis retrospectivo), y adopción real de NEXUS en
        producción. Reemplaza a Nora (`interpretar_dashboard()` arriba, que
        queda deprecado): Decisión de diseño (2026-09-02)
        de ampliar el alcance de datos a todo el sistema y de que Nora deje
        de ser un agente aparte para convertirse en esta capacidad de
        interpretación dentro de Nexus Insights.

        A diferencia de `interpretar_dashboard()` (una sola pasada por
        período, sin memoria), esto es un chat real con preguntas de
        seguimiento -- cada llamada es un mensaje nuevo al LLM. Control de
        costo (decisión de diseño tomada al construir esto, no pedida
        explícitamente en esos términos): el frontend arma `contexto` UNA
        sola vez por refresco de datos (cacheado 60s en
        `_cargar_contexto_nexus_insights()`, no se recalcula en cada
        mensaje) y trunca `historial` a los últimos turnos antes de pasarlo
        acá -- así el costo por mensaje queda acotado al tamaño del
        contexto agregado (resúmenes, nunca filas crudas de HU/test cases
        individuales) más un puñado de turnos previos, no crece sin límite
        con la duración de la conversación.

        Args:
            contexto: dict con TODAS las áreas analíticas (calidad, gio,
                vera, desenlace_alucinaciones, pruebas, tendencias,
                defectos, ia_vs_tradicional, adopcion) -- ver
                `_cargar_contexto_nexus_insights()` en la página para la
                forma exacta de cada bloque.
            historial: turnos previos de la conversación, ya truncados por
                el frontend, cada uno `{"rol": "usuario"|"nexus", "texto":
                str}` -- para turnos de Nexus Insights, `texto` es el paso
                "resumen" de esa respuesta, no la estructura completa de
                pasos (mantiene el historial compacto).
            pregunta: la pregunta nueva del usuario QA.

        Returns:
            Lista de 2 a 5 "pasos", cada uno `{"tipo": "info"|"hallazgo"|
            "resumen", "texto": str}`. UX pedida explícitamente por el
            usuario (2026-09-02, nota capturada al analizar la viabilidad
            de NEXUS): presentar la respuesta como un pipeline de mensajes
            secuenciales, no un bloque de texto plano, y mencionar
            explícitamente cuando encuentra algo digno de atención (paso
            tipo "hallazgo", nunca forzado si no hay nada real que señalar).
            El último paso es siempre "resumen".
        """
        raise NotImplementedError
