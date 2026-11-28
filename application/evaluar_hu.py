"""
Caso de uso: evaluar una HU con Vera, y parar ahí.

Fase 2 §2.2. Antes esto vivía adentro de `GenerarTestCases.ejecutar()`, que
hacía todo de un saque: traer la HU de Jira, evaluarla con Vera y --si
aprobaba-- generar los casos con Gio. El Quality Gate quedaba ENCERRADO en
esa llamada, así que la pantalla no podía frenar en él: para cuando el
usuario veía el score, Gio ya había corrido y gastado.

Separarlo es lo que permite la pantalla que pidió el usuario: Vera evalúa,
se muestra el Health Score contra el umbral, y el usuario decide si genera,
si corrige la HU y reevalúa, o si fuerza.

Este caso de uso NO llama a Gio, NO toca el RAG y NO gasta más que la
evaluación de Vera --que además arranca con un chequeo determinista gratis
(dependencia visual) antes de cualquier llamada al LLM--. Reevaluar varias
veces mientras se corrige una HU cuesta centavos, y esa es justamente la
idea.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from application.validar_hu import ValidarHU
from domain.models import EvaluacionHU, HistoriaUsuario
from infrastructure.config import obtener_logger
from ports.issue_tracker import IssueTracker
from ports.llm_provider import LLMProvider
from ports.repository import Repository

_log = obtener_logger(__name__)


@dataclass
class ResultadoEvaluacion:
    """La HU tal como quedó tras evaluarla, y el veredicto de Vera."""

    hu: HistoriaUsuario
    evaluacion: EvaluacionHU
    descripcion_es_pobre: bool


class EvaluarHU:
    """
    Trae la HU de Jira (o la recibe ya editada), la persiste y la evalúa.

    `ejecutar()` es el camino normal: key -> Jira -> persistir -> Vera.
    `reevaluar()` es el de la edición en pantalla: recibe la HU con la
    descripción que el usuario corrigió y vuelve a pasarla por Vera SIN
    volver a pedirla a Jira --si la pidiera, sobreescribiría justamente lo
    que el usuario acaba de escribir-- y sin tocar Jira, que es la fuente de
    verdad del negocio y no se modifica desde una herramienta de QA.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        repository: Repository,
        issue_tracker: IssueTracker | None = None,
    ):


        self._issue_tracker = issue_tracker
        self._repository = repository
        self._validar_hu = ValidarHU(llm_provider)

    def ejecutar(self, key_hu: str) -> ResultadoEvaluacion:


        fecha_inicio = datetime.now(timezone.utc)
        hu = self._issue_tracker.obtener_hu(key_hu)
        hu.fecha_inicio_proceso = fecha_inicio


        self._repository.guardar_hu(hu)
        return self._evaluar(hu)

    def reevaluar(self, hu: HistoriaUsuario) -> ResultadoEvaluacion:
        """
        Vuelve a pasar por Vera una HU ya traída, con la descripción editada.

        A diferencia de `ejecutar()`, acá NO se llama a `guardar_hu()`: ese
        método hace upsert de la fila entera, incluida `descripcion`, y la
        pisaría con el texto editado. `descripcion` tiene que seguir siendo lo
        que vino de Jira --si no, nadie puede comparar después qué se cambió--
        y el texto editado se guarda aparte, en `descripcion_usada`, recién
        cuando se genera. Si el usuario edita, reevalúa y se va sin generar,
        no queda nada: correcto, porque no se generó nada con ese texto.
        """
        return self._evaluar(hu)

    def _evaluar(self, hu: HistoriaUsuario) -> ResultadoEvaluacion:
        evaluacion = self._validar_hu.ejecutar(hu)
        hu.vera_score = evaluacion.score
        hu.vera_aprobada = evaluacion.aprobada
        hu.vera_motivo_bloqueo = None if evaluacion.aprobada else evaluacion.detalle
        hu.vera_umbral_aplicado = evaluacion.umbral
        self._repository.actualizar_evaluacion_vera(
            hu.key, evaluacion.score, evaluacion.aprobada, hu.vera_motivo_bloqueo,
            umbral_aplicado=evaluacion.umbral,
        )
        return ResultadoEvaluacion(
            hu=hu,
            evaluacion=evaluacion,
            descripcion_es_pobre=hu.descripcion_es_pobre,
        )
