"""
Utilidades de curación manual de `mapa_seguimiento_hu` (Dashboard, comparación
"antes vs. con IA").

A propósito NO vive dentro del port `Repository`: no es una operación del
flujo central del agente (generar/revisar/subir), es una utilidad de
curación para el Dashboard que el QA usa directamente -- agregar/listar qué
HUs quiere comparar. Usa `obtener_sesion()` directo, mismo patrón de
"sesión por bloque" que el resto del proyecto.
"""

from __future__ import annotations

from sqlalchemy import select

from infrastructure.db.conexion import obtener_sesion
from infrastructure.db.models_orm import MapaSeguimientoHUORM

GRUPOS_VALIDOS = ("antes_manual", "con_ia")


def agregar_hu_al_mapa(
    hu_key: str,
    grupo: str,
    tiempo_proceso_horas: float | None = None,
    notas: str | None = None,
) -> None:
    """
    Agrega (o actualiza, si la key ya estaba) una HU a la lista curada de
    seguimiento del Dashboard.

    Args:
        hu_key: key de Jira de la HU (no tiene que haber pasado por el
            agente -- para "antes_manual" nunca pasó).
        grupo: "antes_manual" o "con_ia".
        tiempo_proceso_horas: solo tiene sentido para "antes_manual" (ver
            docstring de MapaSeguimientoHUORM); se ignora si grupo="con_ia",
            porque ese tiempo se calcula solo desde historias_usuario.
    """
    if grupo not in GRUPOS_VALIDOS:
        raise ValueError(f"grupo debe ser uno de {GRUPOS_VALIDOS}, se recibió: {grupo!r}")

    with obtener_sesion() as sesion:
        entrada = MapaSeguimientoHUORM(
            hu_key=hu_key,
            grupo=grupo,
            tiempo_proceso_horas=tiempo_proceso_horas if grupo == "antes_manual" else None,
            notas=notas,
        )
        sesion.merge(entrada)


def listar_mapa(grupo: str | None = None) -> list[MapaSeguimientoHUORM]:
    """
    Lista las HUs curadas para seguimiento, opcionalmente filtradas por
    grupo. Devuelve objetos ORM desconectados de la sesión (se cierra al
    salir del bloque `with`) -- quien llame solo debe leer sus atributos,
    no intentar mutarlos y esperar que se persista.
    """
    if grupo is not None and grupo not in GRUPOS_VALIDOS:
        raise ValueError(f"grupo debe ser uno de {GRUPOS_VALIDOS}, se recibió: {grupo!r}")

    with obtener_sesion() as sesion:
        consulta = select(MapaSeguimientoHUORM)
        if grupo:
            consulta = consulta.where(MapaSeguimientoHUORM.grupo == grupo)
        resultados = list(sesion.execute(consulta).scalars().all())
        for fila in resultados:
            sesion.expunge(fila)
        return resultados
