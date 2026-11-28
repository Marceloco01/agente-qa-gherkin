"""
Comprueba contra Postgres que `historias_usuario` tenga las columnas que el
modelo declara. Lo corre `aplicar_migracion.bat` después del upgrade.

Por qué no alcanza con que Alembic diga "head": lo que rompía era el SELECT,
y el SELECT lo arma SQLAlchemy desde el modelo. Si el modelo gana una columna
y la migración no se escribió --o se escribió y no se aplicó-- Alembic puede
decir "head" igual. La única fuente que no miente es el catálogo de Postgres.

Por eso la comprobación es general: compara TODAS las columnas del modelo
contra las de la tabla, no solo las dos que motivaron esto.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sqlalchemy import create_engine, inspect

from infrastructure.config import cargar_configuracion_db
from infrastructure.db.models_orm import HistoriaUsuarioORM


def main() -> int:
    motor = create_engine(cargar_configuracion_db().url_sqlalchemy)
    tabla = HistoriaUsuarioORM.__tablename__
    en_bd = {c["name"] for c in inspect(motor).get_columns(tabla)}
    en_modelo = {c.name for c in HistoriaUsuarioORM.__table__.columns}

    faltan = sorted(en_modelo - en_bd)
    sobran = sorted(en_bd - en_modelo)

    print(f"   {tabla}: {len(en_bd)} columnas en la base, "
          f"{len(en_modelo)} en el modelo")
    if faltan:
        print(f"   FALTAN en la base: {', '.join(faltan)}")
        print("   -> hay una migracion sin aplicar o sin escribir")
    if sobran:


        print(f"   (la base tiene columnas que el modelo no usa: "
              f"{', '.join(sobran)})")
    if not faltan:
        print("   OK  el modelo y la tabla coinciden")
    return 1 if faltan else 0


if __name__ == "__main__":
    raise SystemExit(main())
