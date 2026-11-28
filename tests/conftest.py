"""
Configuración común de pytest.

Las pruebas escriben el log en una carpeta temporal y no en logs/ del
proyecto. Antes del ajuste de empaquetado, cada corrida dejaba en logs/agente_qa.log
cientos de líneas con datos de prueba (PROJ-1, "Mi caso"), y ese archivo
terminó dentro del zip del código. Esto tiene que ejecutarse antes de que
cualquier prueba importe infrastructure.config, y pytest carga conftest.py
antes que los módulos de prueba.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("AGENTE_QA_DIR_LOGS", tempfile.mkdtemp(prefix="agente_qa_logs_"))
