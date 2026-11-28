"""
Persistencia de resultados de Seguimiento para trackear evolución
cronológica (tesis, Decisión de diseño:
"cronológico").

A propósito NO vive dentro del port `Repository`: mismo criterio que
`infrastructure/db/mapa_seguimiento.py` -- es una utilidad de trazabilidad
para el histórico batch, no una operación del flujo central del agente
(generar/revisar/subir). Usa `obtener_sesion()` directo, mismo patrón de
"sesión por bloque" que el resto del proyecto.

Escribe en `seguimiento_hu_metricas` (ver el docstring completo de esa
tabla en `infrastructure/db/models_orm.py::SeguimientoHUMetricasORM`) --
APPEND-ONLY: `guardar_snapshot_hu()` siempre hace INSERT, nunca UPDATE. El
resumible de `scripts/procesar_seguimiento_historico.py` no depende de un
CSV de control aparte: `obtener_keys_ya_medidas()` le pregunta a esta misma
tabla qué HU ya tienen snapshot, y esa lista ES el estado de avance.

Error real encontrado corriendo el backfill (2026-09-02) y corregido acá:
`ejecutar_seguimiento()` arma `filas_salida` como una lista de dicts donde,
por ejemplo, `num_tests` es `None` para las HU sin Test Plan y un entero
para el resto -- eso está bien mientras es un dict de Python, pero al pasar
por `pd.DataFrame(...)` y después `DataFrame.to_dict(orient="records")`,
pandas convierte esa columna mixta a `float64` y el `None` de las filas sin
dato se vuelve `NaN`, no `None`. Postgres no acepta `NaN` en una columna
INTEGER/FLOAT (falla con "entero fuera de rango"). Se normaliza acá, en el
borde de persistencia -- no en el motor, donde `NaN` es el comportamiento
esperado/idiomático de pandas para mostrarlo en la tabla de Streamlit.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timezone

from sqlalchemy import select

from application.seguimiento.motor import NIVELES_SEVERIDAD
from infrastructure.db.conexion import obtener_sesion
from infrastructure.db.models_orm import SeguimientoHUMetricasORM


def _limpiar_nan(valor):
    """`NaN` (float) -> `None`; cualquier otro valor pasa igual. Ver el
    docstring del módulo para el porqué."""
    if isinstance(valor, float) and math.isnan(valor):
        return None
    return valor


def obtener_keys_ya_medidas() -> set[str]:
    """
    HU que ya tienen al menos un snapshot guardado. Usado por
    `scripts/procesar_seguimiento_historico.py` para no reprocesar HU ya
    medidas -- correr el script de nuevo más adelante (cuando haya HU
    nuevas con customfield_10428 cargado) es, sin necesidad de un modo
    aparte, el mismo mecanismo que cubre "la muestra al día" que el
    usuario planteaba como alternativa.
    """
    with obtener_sesion() as sesion:
        resultado = sesion.execute(select(SeguimientoHUMetricasORM.hu_key)).scalars().all()
        return set(resultado)


def guardar_snapshot_hu(fila: dict, fecha_certificacion_terminada: date | None) -> None:
    """
    Guarda UNA fila de resultado de
    `application/seguimiento/motor.py::ejecutar_seguimiento()` (un dict, ej.
    vía `DataFrame.iloc[i].to_dict()`) como snapshot nuevo.

    Siempre INSERT, nunca UPDATE (ver docstring del módulo y de
    `SeguimientoHUMetricasORM`) -- si `hu_key` ya tenía un snapshot previo,
    esto agrega uno adicional en vez de pisarlo. El caller
    (`scripts/procesar_seguimiento_historico.py`) es quien decide, vía
    `obtener_keys_ya_medidas()`, no volver a llamar esto para una HU ya
    medida -- esta función no lo valida por sí misma para no imponer esa
    política a un eventual caller futuro que sí quiera un refresh explícito
    (ej. reprocesar solo estado de defectos).

    Args:
        fila: una fila de salida de `ejecutar_seguimiento()`. Se admiten
            claves faltantes (usa `.get()` en todas) para tolerar
            variaciones futuras del motor sin romper la persistencia.
        fecha_certificacion_terminada: el valor de customfield_10428 para
            esta HU (viene de `buscar_hu_certificadas()`, no de `fila`,
            porque el motor no lo consulta -- es un dato del descubrimiento
            cronológico, no del cálculo de índices).
    """


    fila = {clave: _limpiar_nan(valor) for clave, valor in fila.items()}

    num_defectos_detectados = sum(
        (fila.get(f"defectos_{nivel.lower()}_detectados") or 0) for nivel in NIVELES_SEVERIDAD
    ) + (fila.get("defectos_otros_detectados") or 0)

    with obtener_sesion() as sesion:
        entrada = SeguimientoHUMetricasORM(
            hu_key=fila["hu_key"],
            fecha_certificacion_terminada=(
                datetime.combine(fecha_certificacion_terminada, time.min, tzinfo=timezone.utc)
                if fecha_certificacion_terminada else None
            ),
            num_criterios_identificados=fila.get("num_criterios_identificados"),
            num_tests=fila.get("num_tests"),
            indice_cobertura_densidad_pct=fila.get("indice_cobertura_densidad_pct"),
            indice_cobertura_real_pct=fila.get("indice_cobertura_real_pct"),
            criterios_no_cubiertos=fila.get("criterios_no_cubiertos") or None,
            indice_ejecucion_pct=fila.get("indice_ejecucion_pct"),
            test_pass_rate_pct=fila.get("test_pass_rate_pct"),
            num_defectos_detectados=num_defectos_detectados if num_defectos_detectados else None,
            num_defectos_resueltos=fila.get("num_defectos_resueltos"),
            defectos_por_severidad=fila.get("defectos_por_severidad") or None,
            test_plan_keys=fila.get("test_plan_keys") or None,
            aviso=fila.get("aviso") or None,
        )
        sesion.add(entrada)


def listar_metricas(
    desde: date | None = None, hasta: date | None = None,
) -> list[SeguimientoHUMetricasORM]:
    """
    Lista snapshots guardados, ordenados por `fecha_certificacion_terminada`
    ascendente (las que no tienen esa fecha quedan al final), opcionalmente
    acotado por rango -- pensado para una futura vista de evolución por
    cohortes (agrupar en Python o con SQL `AVG(...) GROUP BY` sobre lo que
    esto devuelve; esa vista todavía no se construyó, ver conversación con
    el usuario 2026-09-02).

    Devuelve objetos ORM desconectados de la sesión (se cierra al salir del
    bloque `with`) -- quien llame solo debe leer sus atributos, no
    mutarlos esperando que se persista.
    """
    with obtener_sesion() as sesion:
        consulta = select(SeguimientoHUMetricasORM).order_by(
            SeguimientoHUMetricasORM.fecha_certificacion_terminada.is_(None),
            SeguimientoHUMetricasORM.fecha_certificacion_terminada.asc(),
        )
        if desde:
            consulta = consulta.where(SeguimientoHUMetricasORM.fecha_certificacion_terminada >= desde)
        if hasta:
            consulta = consulta.where(SeguimientoHUMetricasORM.fecha_certificacion_terminada <= hasta)
        resultados = list(sesion.execute(consulta).scalars().all())
        for fila in resultados:
            sesion.expunge(fila)
        return resultados
