"""
Módulo de datos único para la sección Pre-Test / Post-Test (NEXUS, 2026-09-06).

Una sola fuente de verdad para toda la sección: la página de Streamlit no lee
ni un CSV por su cuenta ni calcula ningún porcentaje. Así, si mañana cambia
de dónde sale un número, cambia acá y no en cuatro pantallas.

Definición de Pre-Test y Post-Test (adoptada para este diseño)
---------------------------------------------------------------
Corpus cerrado del análisis retrospectivo: **43 HU**. Para cada una:
- **Pre-Test**  = lo que realmente pasó en Jira/Xray con el proceso manual.
- **Post-Test** = lo que produjo el agente (Vera + Gio) sobre esas MISMAS HU.

No es un piloto nuevo: es el mismo corpus mirado desde los dos lados.

**Los tres indicadores NO comparten la misma muestra, y eso se declara.** El
2026-09-06 se recuperaron HU que quedaban fuera solo porque no se les
detectaban los criterios de aceptación. Tienen cobertura, pero no ejecución ni
defectos históricos, porque nunca estuvieron en el corpus cerrado. Así que:
cobertura sobre 47 HU, ejecución y defectos sobre las 43 del corpus. Cada
indicador expone su propio `n_*` y la página lo muestra al lado del número.
Además, `cobertura_control` recalcula la cobertura SOLO sobre las HU que
también tienen ejecución, para poder responder con un número --y no con una
explicación-- la pregunta obvia: "¿la mejora aparece porque agregaron HU?".

Qué es real y qué es un sustituto — LEER ANTES DE CITAR NINGÚN NÚMERO
---------------------------------------------------------------------
1. **Índice de ejecución.** Pre-Test es real y directo:
   `test_runs_ejecutados / test_runs × 100` sobre Xray. Este corpus exploratorio no aporta un Post-Test de ejecución:
   la corrida exploratoria utilizó `RepositoryNulo`, sin publicación de sus casos.
   Esto no describe las ejecuciones QA del flujo operativo. Lo más cercano que hay es la revisión
   retrospectiva de casos: de los casos que generó el agente, cuántos
   sobrevivieron a la revisión humana. Se expone con su propio nombre
   (`aceptacion_post_pct`) y NUNCA como "índice de ejecución del agente",
   porque mide otra cosa: aceptación, no ejecución.

2. **"Índice de cobertura" — OJO, no es cobertura.** El dato que existe en
   `retro_resultado_57hu.csv` (`indice_cobertura_agente_pct` /
   `indice_cobertura_historico_pct`) es, verificado fila por fila contra las
   columnas crudas, exactamente `casos_de_prueba_reales / criterios_de_
   aceptacion_identificados × 100`. Eso es **densidad de casos por criterio**,
   no cobertura: no está acotado a 100 (se observan valores de hasta 600%) y
   sobre todo **no dice qué criterios quedaron cubiertos**. Ocho casos
   apuntando todos al mismo criterio darían 800% con siete criterios sin
   tocar. Por eso este módulo lo llama `densidad_*` y no `cobertura_*`.
   La **cobertura real** SÍ existe desde el 2026-09-06: la calcula
   `scripts/calcular_cobertura_real_retro.py` con
   `LLMProvider.clasificar_cobertura_criterios()`, criterio por criterio y con
   el juez ciego a qué lado está evaluando, y se lee de
   `cobertura_real_retro.csv` en los campos `cobertura_*`. La densidad se
   mantiene expuesta pero relegada: es un dato del análisis retrospectivo, no el indicador.

3. **Estado de defectos.** Pre-Test es real (severidad y estado resueltos
   contra Jira, `defectos_severidad_resumen_retro.csv`). Post-Test no puede
   existir -- sin ejecución no hay defectos encontrados. En su lugar se expone
   el **análisis de evitabilidad**: de los defectos reales, cuáles habría
   anticipado el agente. Usa `validacion_humana` cuando está completa y cae al
   veredicto del LLM cuando no, informando cuál se usó.

Entradas (todas en la raíz del proyecto):
    retro/retro_resultado_57hu.csv        corpus, ejecución, densidad
    revision_manual_retrospectiva_resumen.csv aceptación post (revisión retrospectiva de casos)
    defectos_severidad_resumen_retro.csv    defectos reales por criticidad
    evitabilidad_defectos_retro__*.csv      evitabilidad (opcional)
    contaminacion_rag_retro.csv             HU con RAG contaminado (opcional)
"""

from __future__ import annotations

import csv
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from application.seguimiento.corpus_retro import ampliar

_CRITICIDADES = ["Critico", "Alto", "Medio", "Bajo"]
_VEREDICTOS = ["Evitable", "Parcialmente evitable", "No evitable"]


UMBRAL_PRODUCCION_VERA = 62


_ARCHIVO_LIMITACIONES = "limitaciones_asumidas.csv"


def _num(valor: str | None) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _ent(valor: str | None) -> int:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return 0


@dataclass
class FilaHU:
    hu_key: str
    test_plan_key: str = ""

    runs: int = 0
    runs_ejecutados: int = 0
    ejecucion_pre_pct: float | None = None
    casos_pre: int = 0
    densidad_pre_pct: float | None = None

    casos_post: int = 0
    densidad_post_pct: float | None = None
    aprobados: int = 0
    editados: int = 0
    rechazados: int = 0

    criterios: int = 0
    veredicto_retro: str = ""

    cobertura_pre_pct: float | None = None
    cobertura_post_pct: float | None = None
    cubiertos_pre: int = 0
    cubiertos_post: int = 0
    criterios_no_cubiertos_pre: str = ""
    criterios_no_cubiertos_post: str = ""
    casos_evaluados_pre: int = 0
    defectos: dict = field(default_factory=dict)


    de_ampliacion: bool = False


    tests: int = 0

    @property
    def tests_plan(self) -> int:
        """Tests distintos, con los runs como respaldo si el dato no vino."""
        return self.tests or self.runs

    @property
    def tests_ejecutados(self) -> int:
        """
        Tests cubiertos al menos una vez. Cota superior: supone que los runs
        ejecutados cayeron sobre tests distintos, que el resumen no prueba
        --habría que bajar el detalle de runs de Xray para confirmarlo--.
        """
        return min(self.runs_ejecutados, self.tests_plan)

    @property
    def aceptacion_post_pct(self) -> float | None:
        total = self.aprobados + self.editados + self.rechazados
        if not total:
            return None
        return (self.aprobados + self.editados) / total * 100

    @property
    def delta_densidad(self) -> float | None:
        if self.densidad_pre_pct is None or self.densidad_post_pct is None:
            return None
        return self.densidad_post_pct - self.densidad_pre_pct


@dataclass
class DatosPrePost:
    hus: list[FilaHU]
    defectos_pre: dict
    defectos_sin_clasificar: int


    defectos_sin_criticidad: list[dict]
    evitabilidad: dict
    evitabilidad_fuente: str
    evitabilidad_n: int
    hu_contaminadas: list[str]
    avisos: list[str]
    revision: dict


    scores_vera: dict = field(default_factory=dict)

    limitaciones: dict = field(default_factory=dict)


    ejecutabilidad: dict = field(default_factory=dict)


    defectos_auditados: list[dict] = field(default_factory=list)

    _revision_agente: dict = field(default_factory=dict)


    @property
    def hus_corpus(self) -> list[FilaHU]:
        """Las del corpus cerrado del análisis retrospectivo: las únicas con datos históricos."""
        return [h for h in self.hus if not h.de_ampliacion]

    @property
    def hus_con_runs(self) -> list[FilaHU]:
        """
        Todas las que tienen test runs, vengan de donde vengan.

        Durante meses el índice de ejecución se calculó sobre el corpus cerrado
        (43 HU) porque se creía que las demás no tenían runs. No era cierto:
        los de las 5 recuperadas estaban en historico_test_plan_resumen_57hu.csv
        y los de septiembre en su propio archivo -- existían, nadie los leía. El
        resultado era un dashboard con la cobertura sobre 60 HU y la ejecución
        sobre 43, sin motivo real.

        Son 61. NO es la base de reporte: para eso está hus_con_ejecucion.
        """
        return [h for h in self.hus if h.runs]

    @property
    def hus_con_ejecucion(self) -> list[FilaHU]:
        """
        LA BASE DE 60: las HU que tienen runs Y cobertura calculada.

        Es la misma lista exacta que sostiene el índice de cobertura, y ese es
        todo el punto. Las 61 con runs incluyen una (HU-300) que no tiene
        cobertura real calculada; dejarla adentro obligaba a poner "61 HU" al
        lado de "60 HU" en la misma pantalla y a explicar la diferencia cada
        vez. Sacarla mueve el índice de 95.04% a 95.00% --cuatro centésimas--
        y a cambio los dos indicadores quedan parados sobre el mismo corpus,
        con los mismos 272 criterios. Para una sustentación eso vale más que
        las cuatro centésimas.

        Defectos sigue sobre 43 (el corpus cerrado) porque solo esas tienen
        histórico de defectos; esa diferencia no se puede alinear y se declara.
        """
        con_cobertura = {h.hu_key for h in self._hus_con_cobertura}
        return [h for h in self.hus if h.runs and h.hu_key in con_cobertura]

    @property
    def hus_ampliacion(self) -> list[FilaHU]:
        return [h for h in self.hus if h.de_ampliacion]

    @property
    def n_ejecucion(self) -> int:
        return len(self.hus_con_ejecucion)

    @property
    def n_defectos(self) -> int:
        return len(self.hus_corpus)

    @property
    def n_cobertura(self) -> int:
        return len(self._hus_con_cobertura)


    @property
    def ejecucion_pre_pct(self) -> float | None:
        """
        El índice reportado, en unidad "test ejecutado al menos una vez".

        Se mide así y no en runs porque el denominador tiene que significar lo
        mismo en las 60 HU. En 58 un run es un test y las dos unidades dan
        idéntico; en HU-453 (21 tests, 65 runs) y en HU-104 (10 y 16)
        un run es una corrida, y sumarlos hacía que el índice contara ciclos de
        regresión no completados como si fueran casos nunca probados. En runs
        da 95.0%; en tests, 98.8%. La diferencia NO es que se quitara nada:
        están las 60 HU completas, medidas en la unidad que el indicador
        declara. El corte en runs sigue disponible en ejecucion_runs_pct.
        """
        hs = self.hus_con_ejecucion
        tot = sum(h.tests_plan for h in hs)
        return sum(h.tests_ejecutados for h in hs) / tot * 100 if tot else None

    @property
    def ejecucion_runs_pct(self) -> float | None:
        """El mismo índice contando runs. Se reporta al lado, como sensibilidad."""
        hs = self.hus_con_ejecucion
        runs = sum(h.runs for h in hs)
        return sum(h.runs_ejecutados for h in hs) / runs * 100 if runs else None

    @property
    def plan_agente(self) -> dict:
        """
        El plan que habría producido el agente para las MISMAS 60 HU, y la
        eficiencia que resulta de compararlo contra el humano.

        Por qué esto y no un "Post del índice de ejecución": el índice es
        ejecutados/planificados, y con el Pre en 98.8% el techo deja +1.2 pts
        de margen. Peor: todo estimador que deje fijo el numerador y agrande
        el denominador castiga justo a las HU donde el agente aporta --las de
        cobertura pobre, donde genera MÁS casos--. Se probaron tres y dieron
        -1.3, 0.0 y -21.4 pts. No es que el agente empeore la ejecución: es
        que esa razón no puede detectar la mejora. El equipo no tiene un
        problema de ejecución (ejecuta el 98.8% de lo que planifica); tiene un
        problema de QUÉ planifica, y eso se mide acá y en cobertura.

        La eficiencia sí tiene la forma correcta: criterios cubiertos por test
        ejecutado. Sube si cubrís más, baja si gastás más pruebas, y las dos
        cosas son exactamente lo que el agente cambia.
        """
        hs = self.hus_con_ejecucion
        con_datos = [h for h in hs if h.casos_post and h.criterios]
        densidad = (sum(h.casos_post for h in con_datos)
                    / sum(h.criterios for h in con_datos)) if con_datos else 0.0

        def plan_de(h: FilaHU) -> int:
            return h.casos_post or max(1, round(h.criterios * densidad))


        x = self.ejecutabilidad
        tests_h = x["pre"]["casos"] if x else sum(h.tests_ejecutados for h in hs)
        casos_a = (self.revision_agente.get("aprobados")
                   or sum(plan_de(h) for h in hs))
        crit = sum(h.criterios for h in hs)
        cub_pre = sum(h.cubiertos_pre for h in hs)
        cub_post = sum(h.cubiertos_post for h in hs)
        ef_pre = cub_pre / tests_h if tests_h else None
        ef_post = cub_post / casos_a if casos_a else None
        return {
            "densidad_agente": densidad,
            "hu_con_casos_reales": len(con_datos),
            "hu_extrapoladas": len(hs) - len(con_datos),
            "tests_humano": tests_h,
            "casos_agente": casos_a,
            "reduccion_pct": (1 - casos_a / tests_h) * 100 if tests_h else None,
            "criterios": crit,
            "cubiertos_pre": cub_pre,
            "cubiertos_post": cub_post,
            "eficiencia_pre": ef_pre,
            "eficiencia_post": ef_post,
            "mejora_eficiencia_pct": ((ef_post / ef_pre - 1) * 100
                                      if ef_pre and ef_post else None),
            "tests_por_criterio_pre": tests_h / cub_pre if cub_pre else None,
            "tests_por_criterio_post": casos_a / cub_post if cub_post else None,
        }

    @property
    def capacidad(self) -> dict:
        """
        El lado Post del índice de ejecución, por reasignación de capacidad.

        El razonamiento detrás de esta regla es correcto: si el diseño deja de
        consumir esfuerzo, ese esfuerzo queda disponible para ejecutar. Lo que
        NO se puede hacer es ponerle horas, y conviene decir por qué: las tres
        fuentes de tiempo de diseño del proyecto están rotas.
          - tiempo_diseno_dias: 28 de 82 valores NEGATIVOS (los tests se
            crearon después de arrancar la certificación).
          - duracion_escritura_dias: mediana de 469 días, 54 de 82 por encima
            del año. Es el span entre el primer y el último test del plan, y
            los Test Plans se reciclan; no es tiempo de escritura.
          - revision_manual_retrospectiva: mide el lado Post (114 min para 689
            casos), pero no hay con qué compararlo del lado Pre.
        Así que el modelo se expresa en CASOS, no en horas: es la misma lógica
        sin inventar una magnitud que nadie midió. Del costo de revisar contra
        el de escribir solo se afirma la dirección (revisar cuesta menos que
        escribir desde cero), nunca cuánto.

        Y una advertencia que tiene que viajar con el número: el Δ es chico
        porque el Pre ya estaba en 98.8%, no porque el mecanismo falle. Un
        cociente con techo 100% no puede mostrar una mejora de capacidad; eso
        se ve en la holgura y en cobertura.
        """
        hs = self.hus_con_ejecucion
        rev = self.revision_agente
        x = self.ejecutabilidad
        generados = rev.get("generados", 0)
        aprobados = rev.get("aprobados", 0)
        if not generados or not x:
            return {}

        funcionales_pre = x["pre"]["casos"]
        checklist_pre = x["pre_checklist"]["casos"]
        ejecutados_pre = sum(h.tests_ejecutados for h in hs)


        carga_post = aprobados + checklist_pre
        exceso = carga_post - ejecutados_pre
        post_pct = min(100.0, ejecutados_pre / carga_post * 100) if carga_post else None

        estricto_cub = estricto_tot = 0
        excede = []
        for h in hs:
            a = rev["por_hu"].get(h.hu_key, 0)
            estricto_tot += a
            estricto_cub += min(a, h.tests_ejecutados)
            if a > h.tests_ejecutados:
                excede.append({"hu_key": h.hu_key, "agente": a,
                               "ejecutados": h.tests_ejecutados,
                               "exceso": a - h.tests_ejecutados})
        return {
            "funcionales_pre": funcionales_pre,
            "checklist_pre": checklist_pre,
            "disenados_pre": funcionales_pre + checklist_pre,
            "ejecutados_pre": ejecutados_pre,
            "generados_agente": generados,
            "aprobados_agente": aprobados,
            "rechazados_agente": generados - aprobados,
            "delta_funcional": aprobados - funcionales_pre,
            "delta_funcional_pct": (aprobados / funcionales_pre - 1) * 100
                                   if funcionales_pre else None,
            "carga_post": carga_post,
            "exceso": exceso,
            "exceso_pct": exceso / ejecutados_pre * 100 if ejecutados_pre else None,
            "cabe_global": exceso <= 0,
            "post_pct": post_pct,
            "post_estricto_pct": (estricto_cub / estricto_tot * 100
                                  if estricto_tot else None),
            "hu_que_exceden": sorted(excede, key=lambda z: z["exceso"], reverse=True),
            "n_cabe": len(hs) - len(excede),
        }

    @property
    def revision_agente(self) -> dict:
        """Casos del agente por HU y su veredicto, restringido a la base."""
        return self._revision_agente

    @property
    def hus_multiciclo(self) -> list[FilaHU]:
        """Las que planifican más de un run por test: donde las unidades difieren."""
        return [h for h in self.hus_con_ejecucion
                if h.tests and h.runs > h.tests * 1.5]

    @property
    def n_ejecucion_corpus(self) -> int:
        return len([h for h in self.hus_corpus if h.runs])

    @property
    def ejecucion_corpus_pct(self) -> float | None:
        """
        El índice restringido al corpus cerrado del análisis retrospectivo.

        Existe por una razón concreta: el Excel del pre-test documenta ESE
        alcance (43 HU anonimizadas como H1..H43) y no se puede conciliar HU
        por HU porque las claves están anonimizadas. Comparar el 98.9% del
        Excel contra el 95.0% del tablero --que ya incluye las recuperadas y
        septiembre-- no detecta un error de registro: detecta que el alcance
        creció. Para conciliar hay que comparar el mismo alcance.
        """
        hs = [h for h in self.hus_corpus if h.runs]
        runs = sum(h.runs for h in hs)
        return sum(h.runs_ejecutados for h in hs) / runs * 100 if runs else None

    @property
    def ejecucion_detalle(self) -> dict:
        """
        El índice con su reparto real. El promedio solo no alcanza: una sola HU
        puede explicar casi todo el faltante, y en este corpus eso es justo lo
        que pasa. Reportar 95% sin decir que 34 de los 42 runs sin ejecutar son
        de una única historia esconde el hallazgo en vez de mostrarlo.
        """
        hs = self.hus_con_ejecucion
        planificados = sum(h.tests_plan for h in hs)
        ejecutados = sum(h.tests_ejecutados for h in hs)
        faltantes = planificados - ejecutados
        incompletas = sorted(
            (h for h in hs if h.tests_ejecutados < h.tests_plan),
            key=lambda h: h.tests_plan - h.tests_ejecutados, reverse=True)
        peor = incompletas[0] if incompletas else None
        sin_peor = None
        if peor and faltantes:
            p2 = planificados - peor.tests_plan
            e2 = ejecutados - peor.tests_ejecutados
            sin_peor = {
                "hu_key": peor.hu_key,
                "sin_ejecutar": peor.tests_plan - peor.tests_ejecutados,
                "porcion_del_hueco": (peor.tests_plan - peor.tests_ejecutados) / faltantes * 100,
                "pct_sin_ella": e2 / p2 * 100 if p2 else None,
            }
        return {
            "n": len(hs), "planificados": planificados, "ejecutados": ejecutados,
            "faltantes": faltantes,
            "unidad": "tests",
            "runs_planificados": sum(h.runs for h in hs),
            "runs_ejecutados": sum(h.runs_ejecutados for h in hs),
            "completas": sum(1 for h in hs
                             if h.tests_plan and h.tests_ejecutados == h.tests_plan),
            "incompletas": [
                {"hu_key": h.hu_key, "runs": h.tests_plan, "ejecutados": h.tests_ejecutados,
                 "pct": h.tests_ejecutados / h.tests_plan * 100} for h in incompletas],
            "dominante": sin_peor,
            "multiciclo": [
                {"hu_key": h.hu_key, "tests": h.tests, "runs": h.runs,
                 "ratio": h.runs / h.tests} for h in self.hus_multiciclo],

            "un_run_por_test": sum(1 for h in hs if h.tests and h.runs == h.tests),
            "con_reejecucion": sum(1 for h in hs if h.tests and h.runs > h.tests),


            "sin_run": [
                {"hu_key": h.hu_key, "tests": h.tests, "runs": h.runs}
                for h in hs if h.tests and h.runs < h.tests],
        }

    @property
    def casos_pre(self) -> int:
        return sum(h.casos_pre for h in self.hus_corpus)

    @property
    def casos_post(self) -> int:
        return sum(h.casos_post for h in self.hus_corpus)

    def _prom(self, atributo: str) -> float | None:
        vals = [getattr(h, atributo) for h in self.hus]
        vals = [v for v in vals if v is not None]
        return statistics.mean(vals) if vals else None

    def _mediana(self, atributo: str) -> float | None:
        vals = [getattr(h, atributo) for h in self.hus]
        vals = [v for v in vals if v is not None]
        return statistics.median(vals) if vals else None

    @property
    def densidad_pre_pct(self) -> float | None:
        return self._prom("densidad_pre_pct")

    @property
    def densidad_post_pct(self) -> float | None:
        return self._prom("densidad_post_pct")

    @property
    def densidad_pre_mediana(self) -> float | None:
        return self._mediana("densidad_pre_pct")

    @property
    def densidad_post_mediana(self) -> float | None:
        return self._mediana("densidad_post_pct")

    @property
    def aceptacion_post_pct(self) -> float | None:
        total = sum(h.aprobados + h.editados + h.rechazados for h in self.hus)
        if not total:
            return None
        return sum(h.aprobados + h.editados for h in self.hus) / total * 100


    @property
    def _hus_con_cobertura(self) -> list[FilaHU]:
        return [h for h in self.hus if h.cobertura_pre_pct is not None]

    @property
    def cobertura_pre_pct(self) -> float | None:
        hs = self._hus_con_cobertura
        crit = sum(h.criterios for h in hs)
        return sum(h.cubiertos_pre for h in hs) / crit * 100 if crit else None

    @property
    def cobertura_post_pct(self) -> float | None:
        hs = self._hus_con_cobertura
        crit = sum(h.criterios for h in hs)
        return sum(h.cubiertos_post for h in hs) / crit * 100 if crit else None

    @property
    def criterios_evaluados(self) -> int:
        return sum(h.criterios for h in self._hus_con_cobertura)

    @property
    def criterios_sin_cubrir(self) -> tuple[int, int]:
        """(sin cubrir por el humano, sin cubrir por el agente)."""
        hs = self._hus_con_cobertura
        crit = sum(h.criterios for h in hs)
        return crit - sum(h.cubiertos_pre for h in hs), crit - sum(h.cubiertos_post for h in hs)


    def veredicto(self) -> list[dict]:
        """
        Las afirmaciones que los datos sostienen y las que todavía no.

        Se calcula, no se escribe. Un bloque de conclusiones redactado a mano
        envejece mal: los números cambian y el texto se queda, y termina
        afirmando cosas que los datos ya no dicen. Acá cada afirmación sale de
        los mismos valores que muestra el resto de la página, y las deudas de
        validación salen de los archivos de revisión -- así el día que se
        salden, desaparecen solas.

        Cada elemento: {tipo, texto, respaldo}. `tipo` es "sostiene" (el dato
        alcanza), "matiz" (el dato alcanza pero hay que decir algo más) o
        "falta" (todavía no está respaldado).
        """
        v: list[dict] = []
        r = self.revision or {}

        pre, post = self.cobertura_pre_pct, self.cobertura_post_pct
        if pre is not None and post is not None:
            v.append({
                "clave": "cobertura_delta",
                "tipo": "sostiene",
                "texto": f"El agente cubre {post - pre:+.1f} puntos más de criterios "
                         f"de aceptación que el proceso manual ({pre:.1f}% → {post:.1f}%).",
                "respaldo": f"{self.criterios_evaluados} criterios de {self.n_cobertura} HU, "
                            "juzgados uno por uno con el evaluador ciego al origen de los casos.",
            })
            ctrl = self.cobertura_control
            if ctrl:
                v.append({
                    "clave": "control_muestra",
                    "tipo": "matiz",
                    "texto": f"La mejora no viene de haber ampliado la muestra: sobre "
                             f"las {ctrl['n']} HU del corpus original el Δ sigue siendo "
                             f"{ctrl['delta']:+.1f} pts.",
                    "respaldo": " · ".join(
                        f"{g['nombre']}: {g['n']} HU, Δ {g['delta']:+.1f}"
                        for g in self.cohortes
                    ) + ". Cada grupo entró por un motivo distinto, así que cada uno "
                        "trae su propio Δ en vez de promediarse en una sola cifra.",
                })
            grueso = [g for g in self.cobertura_por_grosor if g.get("hu")]
            if len(grueso) == 2:
                fino, ancho = grueso[0], grueso[1]
                v.append({
                    "tipo": "matiz",
                    "texto": f"La ganancia no depende solo de las HU con poco trabajo manual: "
                             f"donde el humano escribió más de 2 casos ({ancho['hu']} HU) el "
                             f"agente sigue sumando {ancho['delta']:+.1f} pts.",
                    "respaldo": f"En las {fino['hu']} HU con ≤2 casos la ganancia es "
                                f"{fino['delta']:+.1f} pts. Que el grupo grande también mejore "
                                "es lo que sostiene la afirmación general.",
                })

        red = self.reduccion_defectos_pct
        if red is not None and self.evitabilidad_fuente:
            v.append({
                "tipo": "sostiene" if "humana" in self.evitabilidad_fuente else "falta",
                "texto": f"De los {self.total_defectos_pre} defectos reales, el agente habría "
                         f"anticipado {sum(self.defectos_evitados.values())}: "
                         f"{abs(red):.1f}% menos.",
                "respaldo": f"Fuente: {self.evitabilidad_fuente}, {self.evitabilidad_n} defectos. "
                            "Solo se descuentan los 'Evitable'; los 'Parcialmente evitable' "
                            "quedan contados como defectos.",
            })

        if self.ejecucion_pre_pct is not None:
            v.append({
                "tipo": "matiz",
                "texto": f"El índice de ejecución ({self.ejecucion_pre_pct:.1f}%) NO tiene "
                         "lado Post-Test, y no se le inventa uno.",
                "respaldo": "La corrida exploratoria con RepositoryNulo no aporta runs Post-Test de Xray. "
                            "Lo más cercano es la aceptación en la revisión humana, que mide "
                            "otra cosa y se muestra con su propio nombre.",
            })

        if r.get("evit_sin_justificar"):
            n = len(r["evit_sin_justificar"])
            v.append({
                "clave": "evitabilidad_sin_justificar",
                "tipo": "falta",
                "texto": f"{n} veredicto{'s' if n > 1 else ''} de evitabilidad "
                         f"cambiado{'s' if n > 1 else ''} respecto del evaluador automático "
                         "sin motivo escrito.",
                "respaldo": "Son " + ", ".join(r["evit_sin_justificar"]) + ". Sin el porqué "
                            "escrito, esos cambios no se pueden auditar y el número de "
                            "reducción de defectos queda sin respaldo en esa parte.",
            })
        if not r.get("hay_segunda_opinion"):
            v.append({
                "clave": "evitabilidad_segunda_opinion",
                "tipo": "falta",
                "texto": "Los veredictos de evitabilidad tienen una sola opinión detrás.",
                "respaldo": "No hay todavía una segunda lectura a ciegas (ni de otra persona "
                            "ni una re-evaluación propia con distancia). Hasta que la haya, "
                            "esto se declara como limitación del estudio.",
            })
        revisadas = r.get("cobertura_revisadas", 0)
        if revisadas < 5:
            v.append({
                "clave": "cobertura_auditoria",
                "tipo": "falta",
                "texto": f"La cobertura se revisó a mano en {revisadas} HU.",
                "respaldo": "El índice lo emitió un modelo. Con unas 5 HU revisadas a mano "
                            "-- sobre todo las 2 donde el agente cubre menos -- alcanza para "
                            "poder decir que se auditó.",
            })
        elif revisadas:
            v.append({
                "tipo": "sostiene",
                "texto": f"La cobertura se auditó a mano en {revisadas} HU y se coincidió "
                         f"con el evaluador en {r.get('cobertura_coinciden', 0)}.",
                "respaldo": "Revisión humana criterio por criterio, registrada en "
                            "validacion_cobertura.csv.",
            })


        for item in v:
            asumida = self.limitaciones.get(item.get("clave", ""))
            if asumida and item["tipo"] == "falta":
                item["tipo"] = "matiz"
                item["asumida"] = True
                item["respaldo"] = (
                    item["respaldo"] + f"  ›  LIMITACIÓN ASUMIDA ({asumida['fecha']}): "
                    f"{asumida['motivo']}"
                )
        return v

    @property
    def cohortes(self) -> list[dict]:
        """
        Las HU medidas, partidas por CÓMO entraron al estudio.

        Antes esto era un corte binario: "las del corpus" contra "las nuevas".
        Al incorporarse la tanda de septiembre ese segundo grupo pasó a mezclar
        dos cosas que no se parecen -- 5 HU recuperadas por mejorar la detección
        de criterios, y 13 de un lote nuevo, 10 de ellas admitidas con el umbral
        de Vera bajado a 35. Llamarlas a todas "recuperadas" y darles un solo Δ
        describe mal lo que pasó.

        Cada cohorte trae su propio Δ. Si se parecen, el resultado no depende de
        por qué entró cada HU -- que es justo lo que hay que poder mostrar.
        """
        def bloque(nombre: str, hus: list, nota: str) -> dict | None:
            crit = sum(h.criterios for h in hus)
            if not crit:
                return None
            pre = sum(h.cubiertos_pre for h in hus) / crit * 100
            post = sum(h.cubiertos_post for h in hus) / crit * 100
            return {"nombre": nombre, "n": len(hus), "criterios": crit,
                    "pre_pct": pre, "post_pct": post, "delta": post - pre,
                    "nota": nota, "claves": [h.hu_key for h in hus]}

        hs = self._hus_con_cobertura
        sc = self.scores_vera
        reducidas = {k for k, v in sc.items() if v < UMBRAL_PRODUCCION_VERA}
        grupos = [
            bloque("Corpus original", [h for h in hs if not h.de_ampliacion],
                   "Las HU con las que arrancó el estudio."),
            bloque("Ampliación recuperada",
                   [h for h in hs if h.de_ampliacion and h.hu_key not in sc],
                   "Estaban afuera solo porque el detector no reconocía cómo estaban "
                   "escritos sus criterios."),
            bloque(f"Septiembre · umbral {UMBRAL_PRODUCCION_VERA}",
                   [h for h in hs if h.hu_key in sc and h.hu_key not in reducidas],
                   "Lote nuevo que pasó el filtro de Vera de producción."),
            bloque("Septiembre · umbral reducido",
                   [h for h in hs if h.hu_key in reducidas],
                   f"Admitidas con UMBRAL_SCORE_HU en 35 en vez de "
                   f"{UMBRAL_PRODUCCION_VERA}. Declarado como análisis de sensibilidad."),
        ]
        return [g for g in grupos if g]

    @property
    def cobertura_sin_umbral_reducido(self) -> dict | None:
        """
        El mismo índice, pero sin las HU que entraron con el umbral bajado. Es
        la respuesta directa a "¿el resultado depende de haber relajado el
        filtro?", sin tener que recalcular nada a mano.
        """
        sc = self.scores_vera
        reducidas = {k for k, v in sc.items() if v < UMBRAL_PRODUCCION_VERA}
        if not reducidas:
            return None
        hs = [h for h in self._hus_con_cobertura if h.hu_key not in reducidas]
        crit = sum(h.criterios for h in hs)
        if not crit:
            return None
        pre = sum(h.cubiertos_pre for h in hs) / crit * 100
        post = sum(h.cubiertos_post for h in hs) / crit * 100
        return {"n": len(hs), "criterios": crit, "pre_pct": pre, "post_pct": post,
                "delta": post - pre, "n_excluidas": len(reducidas)}

    @property
    def cobertura_control(self) -> dict | None:
        """
        Control de consistencia: la misma cobertura, pero SOLO sobre las HU que
        también tienen ejecución y defectos (las del corpus cerrado).

        Sirve para responder la pregunta obvia de una sustentación -- "¿la
        mejora aparece porque agregaron HU nuevas?" -- con el número calculado
        en vez de con una explicación. Si el Δ del subconjunto compartido se
        parece al total, la ampliación no es lo que produce la ganancia.
        """
        compartidas = [h for h in self._hus_con_cobertura if not h.de_ampliacion]
        nuevas = [h for h in self._hus_con_cobertura if h.de_ampliacion]
        crit = sum(h.criterios for h in compartidas)
        if not crit or not nuevas:
            return None
        pre = sum(h.cubiertos_pre for h in compartidas) / crit * 100
        post = sum(h.cubiertos_post for h in compartidas) / crit * 100
        salida = {
            "n": len(compartidas), "criterios": crit,
            "pre_pct": pre, "post_pct": post, "delta": post - pre,
            "n_nuevas": len(nuevas),
            "claves_nuevas": [h.hu_key for h in nuevas],
        }
        crit_n = sum(h.criterios for h in nuevas)
        if crit_n:
            pre_n = sum(h.cubiertos_pre for h in nuevas) / crit_n * 100
            post_n = sum(h.cubiertos_post for h in nuevas) / crit_n * 100
            salida.update({"criterios_nuevas": crit_n, "pre_nuevas": pre_n,
                           "post_nuevas": post_n, "delta_nuevas": post_n - pre_n})
        return salida

    @property
    def hus_cobertura_completa(self) -> tuple[int, int, int]:
        """(completas con el humano, completas con el agente, total evaluadas)."""
        hs = self._hus_con_cobertura
        return (
            sum(1 for h in hs if (h.cobertura_pre_pct or 0) >= 100),
            sum(1 for h in hs if (h.cobertura_post_pct or 0) >= 100),
            len(hs),
        )

    @property
    def cobertura_por_grosor(self) -> list[dict]:
        """
        De DÓNDE sale la ganancia: separa las HU según cuántos casos había
        escrito el humano. Sin este corte, el promedio global se lee como "el
        agente entiende mejor los criterios", cuando puede estar diciendo "el
        agente es sistemático donde el proceso manual fue escaso".
        """
        salida = []
        for etiqueta, filtro in (
            ("Humano escribió ≤ 2 casos", lambda h: h.casos_evaluados_pre <= 2),
            ("Humano escribió > 2 casos", lambda h: h.casos_evaluados_pre > 2),
        ):
            grupo = [h for h in self._hus_con_cobertura if filtro(h)]
            crit = sum(h.criterios for h in grupo)
            if not crit:
                continue
            pre = sum(h.cubiertos_pre for h in grupo) / crit * 100
            post = sum(h.cubiertos_post for h in grupo) / crit * 100
            salida.append({"grupo": etiqueta, "hu": len(grupo), "criterios": crit,
                           "pre": pre, "post": post, "delta": post - pre})
        return salida

    @property
    def cobertura_con_margen(self) -> dict | None:
        """Excluye las HU que el humano ya cubría al 100% (techo, no empate)."""
        grupo = [h for h in self._hus_con_cobertura if (h.cobertura_pre_pct or 0) < 100]
        crit = sum(h.criterios for h in grupo)
        if not crit:
            return None
        pre = sum(h.cubiertos_pre for h in grupo) / crit * 100
        post = sum(h.cubiertos_post for h in grupo) / crit * 100
        return {"hu": len(grupo), "criterios": crit, "pre": pre, "post": post, "delta": post - pre}

    @property
    def cobertura_regresiones(self) -> list[FilaHU]:
        """HU donde el agente cubre MENOS. No esconderlas: dan credibilidad."""
        return [h for h in self._hus_con_cobertura
                if (h.cobertura_post_pct or 0) < (h.cobertura_pre_pct or 0)]

    @property
    def hus_con_mayor_densidad_agente(self) -> tuple[int, int]:
        comparables = [h for h in self.hus if h.delta_densidad is not None]
        return sum(1 for h in comparables if h.delta_densidad > 0), len(comparables)

    @property
    def total_defectos_pre(self) -> int:
        return sum(v["abiertos"] + v["cerrados"] for v in self.defectos_pre.values()) \
            + self.defectos_sin_clasificar


    @property
    def defectos_evitados(self) -> dict:
        """criticidad -> cuántos habría anticipado el agente."""
        return {
            crit: cuentas.get("Evitable", 0)
            for crit, cuentas in self.evitabilidad.items()
        }

    @property
    def defectos_post(self) -> dict:
        """criticidad -> defectos que quedarían con el agente (Pre − evitados)."""
        evitados = self.defectos_evitados
        salida = {}
        for crit, v in self.defectos_pre.items():
            pre = v["abiertos"] + v["cerrados"]
            salida[crit] = max(0, pre - evitados.get(crit, 0))
        if self.defectos_sin_clasificar:
            salida["SIN_CLASIFICAR"] = max(
                0, self.defectos_sin_clasificar - evitados.get("SIN_CLASIFICAR", 0)
            )
        return salida

    @property
    def total_defectos_post(self) -> int | None:
        if not self.evitabilidad:
            return None
        return sum(self.defectos_post.values())

    @property
    def reduccion_defectos_pct(self) -> float | None:
        pre = self.total_defectos_pre
        post = self.total_defectos_post
        if not pre or post is None:
            return None
        return (post - pre) / pre * 100

    def defectos_pre_de(self, criticidad: str) -> int:
        if criticidad == "SIN_CLASIFICAR":
            return self.defectos_sin_clasificar
        v = self.defectos_pre.get(criticidad, {})
        return v.get("abiertos", 0) + v.get("cerrados", 0)

    def evitabilidad_pct(self, criticidad: str | None = None) -> tuple[int, int] | None:
        """(evitables, total) global o para una criticidad."""
        if not self.evitabilidad:
            return None
        if criticidad:
            c = self.evitabilidad.get(criticidad, {})
            total = sum(c.values())
            return (c.get("Evitable", 0), total) if total else None
        ev = sum(c.get("Evitable", 0) for c in self.evitabilidad.values())
        total = sum(sum(c.values()) for c in self.evitabilidad.values())
        return (ev, total) if total else None


def _leer(raiz: Path, nombre: str) -> list[dict]:
    ruta = raiz / nombre
    if not ruta.exists():
        return []
    with ruta.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


_RE_WHEN = re.compile(r"^\s*(when|cuando)\b", re.I | re.M)
_RE_THEN = re.compile(r"^\s*(then|entonces)\b", re.I | re.M)


def _es_ejecutable(gherkin: str) -> bool:
    t = (gherkin or "").strip()
    return bool(t) and bool(_RE_WHEN.search(t)) and bool(_RE_THEN.search(t))


_UMBRAL_CHECKLIST_HU = 3
_RE_PREFIJO_CASO = re.compile(r"^(CP|TC)\s*-?\s*\d+\s*[-.:]?\s*", re.I)


def _titulo_normalizado(s: str) -> str:
    return re.sub(r"\s+", " ", _RE_PREFIJO_CASO.sub("", (s or "").strip())).strip().lower()


def _clasificar_historico(filas: list[dict]) -> tuple[set[str], list[dict]]:
    """
    Separa los casos históricos en funcionales y verificaciones de gobierno.

    Devuelve (títulos de checklist, catálogo ordenado por cuántas HU lo repiten).
    El catálogo va a pantalla: el hallazgo --que 41% del esfuerzo de prueba del
    área son gates de proceso, no pruebas de la historia-- vale por sí solo y
    tiene que poder mostrarse, no solo restarse.
    """
    hu_por_titulo: dict[str, set[str]] = {}
    for f in filas:
        t = _titulo_normalizado(f.get("test_summary"))
        hu_por_titulo.setdefault(t, set()).add(f.get("hu_key", ""))
    titulos = {t for t, hus in hu_por_titulo.items()
               if len(hus) >= _UMBRAL_CHECKLIST_HU}
    catalogo = sorted(
        ({"titulo": t, "hu": len(hu_por_titulo[t])} for t in titulos),
        key=lambda x: x["hu"], reverse=True)
    return titulos, catalogo


def _cargar_ejecutabilidad(raiz: Path, claves: set[str], avisos: list[str]) -> dict:
    """
    Compara el guion HUMANO histórico contra el del AGENTE, mismo método a los
    dos lados, sobre las mismas HU.

    El lado agente sale de revision_manual_retrospectiva_test_cases.csv porque
    es el único archivo con cobertura de las 60 HU. Se verificó que no está
    contaminado por la edición humana: de los 312 casos que también están en la
    salida cruda (test_cases_generados_82hu.csv y test_cases_septiembre.csv),
    312 coinciden y 0 difieren -- la revisión aprobó o rechazó, nunca reescribió
    el Gherkin. Por eso gherkin_final sirve como salida del agente.
    """
    crudo_humano = [f for archivo in ("historico_gherkin_texto_57hu.csv",
                                     "historico_gherkin_texto_septiembre.csv")
                    for f in _leer(raiz, archivo)
                    if (f.get("hu_key") or "").strip() in claves]
    titulos_check, catalogo = _clasificar_historico(crudo_humano)

    humano = [((f.get("hu_key") or "").strip(), f.get("gherkin_texto") or "")
              for f in crudo_humano]
    funcional = [((f.get("hu_key") or "").strip(), f.get("gherkin_texto") or "")
                 for f in crudo_humano
                 if _titulo_normalizado(f.get("test_summary")) not in titulos_check]
    checklist = [((f.get("hu_key") or "").strip(), f.get("gherkin_texto") or "")
                 for f in crudo_humano
                 if _titulo_normalizado(f.get("test_summary")) in titulos_check]
    agente = [((f.get("hu_key") or "").strip(), f.get("gherkin_final") or "")
              for f in _leer(raiz, "revision_manual_retrospectiva_test_cases.csv")
              if (f.get("hu_key") or "").strip() in claves]
    if not humano or not agente:
        avisos.append(
            "No se pudo medir la ejecutabilidad del guion: falta el texto Gherkin "
            "histórico o el de la revisión retrospectiva."
        )
        return {}

    def resumen(filas):
        n = len(filas)
        return {
            "casos": n,
            "hu": len({k for k, _ in filas}),
            "ejecutables": sum(1 for _, g in filas if _es_ejecutable(g)),
            "sin_guion": sum(1 for _, g in filas if not (g or "").strip()),
            "sin_accion": sum(1 for _, g in filas
                              if (g or "").strip() and not _RE_WHEN.search(g)),
            "sin_resultado": sum(1 for _, g in filas
                                 if (g or "").strip() and not _RE_THEN.search(g)),
        }

    pre, post = resumen(funcional), resumen(agente)
    total, check = resumen(humano), resumen(checklist)
    for r in (pre, post, total, check):
        r["pct"] = r["ejecutables"] / r["casos"] * 100 if r["casos"] else None


    por_hu: dict[str, dict] = {}
    for lado, filas in (("pre", funcional), ("post", agente)):
        for clave, g in filas:
            d = por_hu.setdefault(clave, {"pre": [0, 0], "post": [0, 0]})
            d[lado][1] += 1
            d[lado][0] += _es_ejecutable(g)
    detalle_hu = sorted(
        ({"hu_key": k, "pre_ok": v["pre"][0], "pre_n": v["pre"][1],
          "post_ok": v["post"][0], "post_n": v["post"][1],
          "pre_pct": v["pre"][0] / v["pre"][1] * 100 if v["pre"][1] else None,
          "post_pct": v["post"][0] / v["post"][1] * 100 if v["post"][1] else None}
         for k, v in por_hu.items() if v["pre"][1] or v["post"][1]),
        key=lambda x: x["hu_key"])
    peores = sorted((x for x in detalle_hu if x["pre_pct"] is not None),
                    key=lambda x: x["pre_pct"])[:6]

    return {


        "pre": pre, "post": post,
        "delta": (post["pct"] - pre["pct"]) if pre["pct"] and post["pct"] else None,
        "peores": peores,


        "por_hu": {x["hu_key"]: x for x in detalle_hu},


        "pre_total": total, "pre_checklist": check,
        "catalogo_checklist": catalogo[:12],
        "n_titulos_checklist": len(titulos_check),
        "umbral_hu": _UMBRAL_CHECKLIST_HU,
    }


def cargar(raiz: Path) -> DatosPrePost:
    avisos: list[str] = []

    corpus = _leer(raiz, "retro/retro_resultado_57hu.csv")
    if not corpus:
        raise FileNotFoundError(
            "Falta retro/retro_resultado_57hu.csv -- es el corpus base de "
            "toda la sección Pre-Test / Post-Test."
        )

    revision = {f["hu_key"]: f for f in _leer(raiz, "revision_manual_retrospectiva_resumen.csv")}
    defectos = {f["hu_key"]: f for f in _leer(raiz, "defectos_severidad_resumen_retro.csv")}

    scores_vera: dict[str, int] = {}
    for f in _leer(raiz, "resultado_septiembre.csv"):
        if (f.get("vera_aprobada") or "").strip().lower() not in ("true", "1", "si", "sí"):
            continue
        key = (f.get("hu_key") or "").strip()
        try:
            score = int(float(f.get("vera_score") or ""))
        except ValueError:
            continue
        if key:
            scores_vera[key] = score

    limitaciones: dict[str, dict] = {}
    for f in _leer(raiz, _ARCHIVO_LIMITACIONES):
        clave = (f.get("clave") or "").strip()
        if clave:
            limitaciones[clave] = {
                "motivo": (f.get("motivo") or "").strip() or "sin motivo escrito",
                "fecha": (f.get("fecha") or "").strip() or "sin fecha",
            }


    sin_criticidad: list[dict] = []
    for f in _leer(raiz, "defectos_severidad_detalle_retro.csv"):
        if (f.get("criticidad") or "SIN_CLASIFICAR") != "SIN_CLASIFICAR":
            continue
        titulo = (f.get("defecto_titulo") or "").strip()
        sin_criticidad.append({
            "id": f.get("defecto_id", ""),
            "key": (f.get("defecto_key") or "").strip(),
            "titulo": titulo,


            "motivo": ("severidad vacía en Jira" if titulo
                       else "la referencia no se pudo resolver en Jira"),
            "hu_keys": f.get("hu_keys", ""),
        })

    hus: list[FilaHU] = []
    for f in corpus:
        hu = FilaHU(
            hu_key=f["hu_key"],
            test_plan_key=f.get("test_plan_key", ""),
            runs=_ent(f.get("num_test_runs")),
            runs_ejecutados=_ent(f.get("num_test_runs_ejecutados")),
            ejecucion_pre_pct=_num(f.get("indice_ejecucion_pct")),
            casos_pre=_ent(f.get("hi_real")),
            casos_post=_ent(f.get("ag_real")),
            densidad_pre_pct=_num(f.get("indice_cobertura_historico_pct")),
            densidad_post_pct=_num(f.get("indice_cobertura_agente_pct")),
            criterios=_ent(f.get("num_criterios_identificados")),
            veredicto_retro=f.get("veredicto", ""),
        )
        r = revision.get(hu.hu_key)
        if r:
            hu.aprobados = _ent(r.get("aprobados"))
            hu.editados = _ent(r.get("editados"))
            hu.rechazados = _ent(r.get("rechazados"))
        d = defectos.get(hu.hu_key)
        if d:
            hu.defectos = {
                c: {"abiertos": _ent(d.get(f"{c.lower()}_abiertos")),
                    "cerrados": _ent(d.get(f"{c.lower()}_cerrados"))}
                for c in _CRITICIDADES
            }
        hus.append(hu)


    claves_corpus = {h.hu_key for h in hus}
    cobertura_keys = {f["hu_key"] for f in _leer(raiz, "cobertura_real_retro.csv")}
    for clave in ampliar(sorted(claves_corpus)):
        if clave in claves_corpus or clave not in cobertura_keys:
            continue
        extra = FilaHU(hu_key=clave, de_ampliacion=True)
        r = revision.get(clave)
        if r:
            extra.aprobados = _ent(r.get("aprobados"))
            extra.editados = _ent(r.get("editados"))
            extra.rechazados = _ent(r.get("rechazados"))
        hus.append(extra)


    runs_extra: dict[str, dict] = {}
    for archivo in ("historico_test_plan_resumen_57hu.csv",
                    "historico_test_plan_resumen_septiembre.csv"):
        for f in _leer(raiz, archivo):
            clave = (f.get("hu_key") or "").strip()
            if clave:
                runs_extra[clave] = f


    for h in hus:
        f = runs_extra.get(h.hu_key)
        if f:
            h.tests = _ent(f.get("num_tests"))

    ambiguos: list[str] = []
    for h in hus:
        if h.runs:
            continue
        f = runs_extra.get(h.hu_key)
        if not f:
            continue
        h.runs = _ent(f.get("num_test_runs"))
        h.runs_ejecutados = _ent(f.get("num_test_runs_ejecutados"))
        if h.runs:
            h.ejecucion_pre_pct = h.runs_ejecutados / h.runs * 100
            if not h.test_plan_key:
                h.test_plan_key = (f.get("test_plan_key") or "").strip()
            if "AMBIGUO" in (f.get("ESTADO_VALIDACION") or ""):
                ambiguos.append(h.hu_key)
    if ambiguos:
        avisos.append(
            f"{len(ambiguos)} HU tienen más de un Test Plan vinculado "
            f"({', '.join(sorted(ambiguos))}): sus runs se incluyen en el índice de "
            "ejecución, pero podrían pertenecer a otro plan. Declarado, no descartado."
        )

    sin_revision = [h.hu_key for h in hus if not revision.get(h.hu_key)]
    if sin_revision:
        avisos.append(
            f"{len(sin_revision)} HU del corpus no tienen revisión retrospectiva: "
            "no aportan al índice de aceptación del lado agente."
        )
    sin_densidad = [h.hu_key for h in hus if not h.de_ampliacion and h.densidad_post_pct is None]
    if sin_densidad:
        avisos.append(
            f"{len(sin_densidad)} HU sin criterios de aceptación detectados "
            f"({', '.join(sin_densidad)}): quedan fuera de la comparación de densidad."
        )
    if not defectos:
        avisos.append(
            "No está defectos_severidad_resumen_retro.csv -- corré "
            "scripts/resolver_severidad_defectos_retro.py."
        )


    agregado = {c: {"abiertos": 0, "cerrados": 0} for c in _CRITICIDADES}
    sin_clasificar = 0
    for d in defectos.values():
        for c in _CRITICIDADES:
            agregado[c]["abiertos"] += _ent(d.get(f"{c.lower()}_abiertos"))
            agregado[c]["cerrados"] += _ent(d.get(f"{c.lower()}_cerrados"))
        sin_clasificar += _ent(d.get("sin_clasificar"))


    cobertura = {f["hu_key"]: f for f in _leer(raiz, "cobertura_real_retro.csv")}
    for hu in hus:
        c = cobertura.get(hu.hu_key)
        if not c:
            continue
        hu.cobertura_pre_pct = _num(c.get("cobertura_sin_ia_pct"))
        hu.cobertura_post_pct = _num(c.get("cobertura_con_ia_pct"))
        hu.cubiertos_pre = _ent(c.get("cubiertos_sin_ia"))
        hu.cubiertos_post = _ent(c.get("cubiertos_con_ia"))
        hu.criterios_no_cubiertos_pre = c.get("no_cubiertos_sin_ia", "")
        hu.criterios_no_cubiertos_post = c.get("no_cubiertos_con_ia", "")
        hu.casos_evaluados_pre = _ent(c.get("casos_sin_ia"))

        hu.criterios = _ent(c.get("criterios_total")) or hu.criterios
    if not cobertura:
        avisos.append(
            "Falta cobertura_real_retro.csv -- corré "
            "scripts/calcular_cobertura_real_retro.py para el índice de cobertura."
        )
    else:
        sin_cob = [h.hu_key for h in hus if h.cobertura_pre_pct is None]
        if sin_cob:
            avisos.append(
                f"{len(sin_cob)} de {len(hus)} HU no tienen cobertura real calculada "
                f"({', '.join(sin_cob)}): quedan fuera de la base de reporte. "
                "Cobertura y ejecución se calculan sobre las mismas HU, así que "
                "salir de una es salir de la otra. Sus runs sí existen y se "
                "pueden ver en el corte de 61."
            )


    evit, fuente, n_evit = _cargar_evitabilidad(raiz, avisos)
    auditados = _cargar_defectos_auditados(raiz)
    revision = _revision_pendiente(raiz)

    contaminadas = [
        f["hu_key"] for f in _leer(raiz, "contaminacion_rag_retro.csv")
        if f.get("veredicto") == "CONTAMINADO"
    ]


    con_cobertura = {h.hu_key for h in hus if h.cobertura_pre_pct is not None}
    base_ejecucion = {h.hu_key for h in hus if h.runs and h.hu_key in con_cobertura}
    ejecutabilidad = _cargar_ejecutabilidad(raiz, base_ejecucion, avisos)


    rev_gen = rev_apr = 0
    rev_por_hu: dict[str, int] = {}
    for f in _leer(raiz, "revision_manual_retrospectiva_test_cases.csv"):
        clave = (f.get("hu_key") or "").strip()
        if clave not in base_ejecucion:
            continue
        rev_gen += 1
        if (f.get("estado_final") or "").strip().lower() == "aprobado":
            rev_apr += 1
            rev_por_hu[clave] = rev_por_hu.get(clave, 0) + 1
    revision_agente = {"generados": rev_gen, "aprobados": rev_apr,
                       "por_hu": rev_por_hu}

    return DatosPrePost(
        hus=hus,
        defectos_pre=agregado,
        defectos_sin_clasificar=sin_clasificar,
        defectos_sin_criticidad=sin_criticidad,
        evitabilidad=evit,
        evitabilidad_fuente=fuente,
        evitabilidad_n=n_evit,
        hu_contaminadas=contaminadas,
        revision=revision,
        avisos=avisos,
        scores_vera=scores_vera,
        limitaciones=limitaciones,
        ejecutabilidad=ejecutabilidad,
        defectos_auditados=auditados,
        _revision_agente=revision_agente,
    )


def _revision_pendiente(raiz: Path) -> dict:
    """
    Qué falta para que los números estén respaldados por revisión humana.

    Va en el módulo y no en la página a propósito: el bloque de veredicto tiene
    que decir lo que FALTA con la misma fuente de verdad con la que dice lo que
    hay. Un tablero que muestra los logros calculados y las deudas escritas a
    mano termina, siempre, mostrando deudas viejas.
    """
    cobertura_revisadas = _leer(raiz, "validacion_cobertura.csv")
    coinciden = sum(1 for f in cobertura_revisadas
                    if (f.get("veredicto_humano") or "").startswith("Coincido con"))

    sin_justificar: list[str] = []
    validados = total_juicios = 0
    corridas = sorted(raiz.glob("evitabilidad_defectos_retro__*.csv"))
    if corridas:
        filas: list[dict] = []
        for ruta in corridas:
            with ruta.open("r", newline="", encoding="utf-8") as f:
                candidatas = list(csv.DictReader(f))
            if len(candidatas) > len(filas):
                filas = candidatas
        total_juicios = len(filas)
        validados = sum(1 for f in filas if (f.get("validacion_humana") or "").strip())


        sin_justificar = [
            (f.get("defecto_key") or f.get("defecto_id", ""))
            for f in filas
            if (f.get("validacion_humana") or "").strip()
            and f.get("validacion_humana") != f.get("veredicto")
            and not (f.get("comentario_humano") or "").strip()
        ]

    return {
        "cobertura_revisadas": len(cobertura_revisadas),
        "cobertura_coinciden": coinciden,
        "evit_validados": validados,
        "evit_total": total_juicios,
        "evit_sin_justificar": sin_justificar,
        "hay_segunda_opinion": (raiz / "comparacion_validacion_ciega.csv").exists()
        or (raiz / "comparacion_reevaluacion_ciega.csv").exists(),
    }


def _cargar_defectos_auditados(raiz: Path) -> list[dict]:
    """
    Los 57 defectos reales, uno por uno, con su juicio de evitabilidad y el
    caso del agente que lo habría atrapado.

    Se junta de tres archivos porque el dato está repartido: el juicio y el
    caso señalado en `evitabilidad_defectos_retro__<modelo>.csv`, la
    descripción completa del bug en `defectos_severidad_detalle_retro.csv`,
    y el test HISTÓRICO que estaba vinculado al defecto en
    `defectos_caso_detector_retro.csv` -- ese último es el que permite
    mostrar, al lado del caso de Gio, qué tenía el equipo en su momento.

    Se usa la MISMA corrida que alimenta el indicador (la de más juicios), no
    una elegida aparte: si la auditoría mostrara filas de un archivo y el
    número saliera de otro, la pantalla estaría auditando algo distinto de lo
    que reporta.
    """
    corridas = sorted(raiz.glob("evitabilidad_defectos_retro__*.csv"))
    if not corridas:
        legacy = raiz / "evitabilidad_defectos_retro.csv"
        corridas = [legacy] if legacy.exists() else []
    filas: list[dict] = []
    for ruta in corridas:
        candidatas = _leer(raiz, ruta.name)
        if len(candidatas) > len(filas):
            filas = candidatas
    if not filas:
        return []

    detalle = {f.get("defecto_id"): f
               for f in _leer(raiz, "defectos_severidad_detalle_retro.csv")}
    detectores: dict[str, list[dict]] = {}
    for f in _leer(raiz, "defectos_caso_detector_retro.csv"):
        detectores.setdefault(f.get("defecto_id"), []).append(f)

    salida = []
    for f in filas:
        did = f.get("defecto_id")
        extra = detalle.get(did, {})
        humano = (f.get("validacion_humana") or "").strip()
        llm = (f.get("veredicto") or "").strip()
        salida.append({
            "defecto_id": did,
            "defecto_key": f.get("defecto_key", ""),
            "titulo": f.get("defecto_titulo", ""),
            "descripcion": extra.get("defecto_descripcion", ""),
            "criticidad": f.get("criticidad", ""),
            "estado": f.get("abierto_cerrado", ""),
            "hu_keys": [h.strip() for h in (f.get("hu_keys") or "").split(",") if h.strip()],
            "veredicto_llm": llm,
            "veredicto_humano": humano,


            "veredicto": humano or llm,
            "corregido_por_humano": bool(humano) and humano != llm,
            "caso_agente": (f.get("caso_agente_senalado") or "").strip(),
            "justificacion": f.get("justificacion", ""),
            "motivo_no_evitable": f.get("motivo_no_evitable", ""),
            "confianza": f.get("confianza", ""),
            "modelo_juez": f.get("modelo_juez", ""),
            "comentario_humano": f.get("comentario_humano", ""),
            "tests_historicos": [
                {"test_key": d.get("test_key", ""), "titulo": d.get("test_titulo", ""),
                 "contenido": d.get("test_contenido", ""), "run_estado": d.get("run_estado", "")}
                for d in detectores.get(did, [])
            ],
        })
    return salida


def _cargar_evitabilidad(raiz: Path, avisos: list[str]) -> tuple[dict, str, int]:
    """
    Devuelve {criticidad: {veredicto: n}}, la fuente usada y el n.

    Prefiere la validación humana; si está incompleta usa la pre-clasificación
    del LLM y lo dice. Nunca mezcla las dos en un mismo número.
    """
    corridas = sorted(raiz.glob("evitabilidad_defectos_retro__*.csv"))
    if not corridas:
        legacy = raiz / "evitabilidad_defectos_retro.csv"
        corridas = [legacy] if legacy.exists() else []
    if not corridas:
        avisos.append(
            "No hay análisis de evitabilidad -- corré "
            "el análisis de evitabilidad."
        )
        return {}, "", 0


    filas: list[dict] = []
    for ruta in corridas:
        with ruta.open("r", newline="", encoding="utf-8") as f:
            candidatas = list(csv.DictReader(f))
        if len(candidatas) > len(filas):
            filas = candidatas

    validados = [f for f in filas if (f.get("validacion_humana") or "").strip()]
    if len(validados) == len(filas) and filas:
        usar, campo, fuente = filas, "validacion_humana", "validación humana"
    else:
        usar, campo, fuente = filas, "veredicto", "pre-clasificación del LLM (sin validar del todo)"
        if validados:
            avisos.append(
                f"La validación humana está incompleta ({len(validados)}/{len(filas)}): "
                "los números de evitabilidad usan la pre-clasificación del LLM."
            )

    evit: dict = {}
    for f in usar:
        veredicto = (f.get(campo) or "").strip()
        if veredicto not in _VEREDICTOS:
            continue
        evit.setdefault(f.get("criticidad", "SIN_CLASIFICAR"), {})
        evit[f["criticidad"]][veredicto] = evit[f["criticidad"]].get(veredicto, 0) + 1
    return evit, fuente, sum(sum(c.values()) for c in evit.values())
