"""
Limpieza puntual de snapshots inválidos en `seguimiento_hu_metricas`
(2026-09-02) -- caso EXCEPCIONAL, no es parte del flujo normal de este
histórico (por eso esto no vive como función en
`infrastructure/db/seguimiento_metricas.py` -- esa tabla es append-only a
propósito, ver el docstring de `SeguimientoHUMetricasORM` en
`infrastructure/db/models_orm.py`).

Origen: 7 HU quedaron guardadas en una corrida vieja (previa a armar el
JQL final con `type = Historia`), que buscaba con `customfield_10429 is
not EMPTY` sin filtro de issuetype (ver
`scripts/diagnosticar_alcance_seguimiento_historico.py` para el porqué de
ese cambio). El usuario verificó en Jira con
`key in (HU-476, HU-478, HU-477, HU-475, HU-481, HU-480,
HU-479) AND issuetype != Historia` que 3 de esas 7 son en realidad
`Historia Técnica` -- un tipo de issue que este proyecto NO mide ni
cuenta como HU (todo el resto del histórico y el análisis retrospectivo se basan en
`type = Historia`): `HU-477`, `HU-478`, `HU-475`. Las otras 4 sí
son `Historia` real y quedan en la tabla -- dan histórico desde mediados
de 2024 en vez de arrancar en enero 2026.

Por defecto hace DRY-RUN (solo muestra qué borraría, no borra nada) --
hace falta pasar `--confirmar` para que borre de verdad.

Uso (desde la raíz del proyecto, con el venv activado):

    python scripts\\limpiar_snapshots_invalidos.py HU-477 HU-478 HU-475
    python scripts\\limpiar_snapshots_invalidos.py HU-477 HU-478 HU-475 --confirmar
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select

from infrastructure.db.conexion import obtener_sesion
from infrastructure.db.models_orm import SeguimientoHUMetricasORM


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Borra puntualmente snapshots inválidos de seguimiento_hu_metricas por hu_key.",
    )
    parser.add_argument("keys", nargs="+", help="hu_key(s) a borrar, ej. HU-477 HU-478 HU-475.")
    parser.add_argument(
        "--confirmar", action="store_true",
        help="Sin este flag solo muestra qué borraría (dry-run) -- no borra nada.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parsear_argumentos()
    keys = args.keys

    with obtener_sesion() as sesion:
        filas = sesion.execute(
            select(SeguimientoHUMetricasORM).where(SeguimientoHUMetricasORM.hu_key.in_(keys))
        ).scalars().all()

        if not filas:
            print("No se encontró ningún snapshot con esas keys -- nada para borrar.")
            return

        print(f"Se encontraron {len(filas)} snapshot(s) que matchean:")
        for fila in filas:
            fecha = (
                fila.fecha_certificacion_terminada.date().isoformat()
                if fila.fecha_certificacion_terminada else "(sin fecha)"
            )
            print(f"  id={fila.id}  hu_key={fila.hu_key}  fecha={fecha}")

        encontradas = {f.hu_key for f in filas}
        no_encontradas = set(keys) - encontradas
        if no_encontradas:
            print(f"\nAVISO: no se encontró snapshot para: {sorted(no_encontradas)}")

        if not args.confirmar:
            print("\nDRY-RUN -- no se borró nada. Corré de nuevo con --confirmar para borrar de verdad.")
            return

        sesion.execute(
            delete(SeguimientoHUMetricasORM).where(SeguimientoHUMetricasORM.hu_key.in_(keys))
        )
        print(f"\nBorrados {len(filas)} snapshot(s).")


if __name__ == "__main__":
    main()
