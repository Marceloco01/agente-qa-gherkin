"""
Carga de configuración técnica desde variables de entorno, y configuración de
logging del proyecto.

Este es el único lugar de Fase 1 donde se permite saber "de dónde vienen" las
credenciales (archivo .env). El resto del código (domain, application, ports)
nunca debe leer variables de entorno directamente.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


_RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
_CARPETA_LOGS_POR_DEFECTO = _RAIZ_PROYECTO / "logs"
_NOMBRE_ARCHIVO_LOG = "agente_qa.log"

_logging_configurado = False


def carpeta_logs() -> Path:
    """Carpeta de logs vigente: AGENTE_QA_DIR_LOGS si está definida, si no logs/."""
    valor = os.getenv("AGENTE_QA_DIR_LOGS", "").strip()
    return Path(valor) if valor else _CARPETA_LOGS_POR_DEFECTO


def configurar_logging() -> None:
    """
    Configura el logging del proyecto: archivo `logs/agente_qa.log` (o el de
    AGENTE_QA_DIR_LOGS), nivel INFO por defecto, con rotación para que el
    archivo no crezca sin control (5 MB por archivo, hasta 3 de respaldo).

    Idempotente: si ya se configuró en este proceso, no vuelve a agregar
    handlers duplicados (relevante porque Streamlit puede re-ejecutar este
    módulo varias veces dentro de la misma sesión).
    """
    global _logging_configurado
    if _logging_configurado:
        return

    carpeta = carpeta_logs()
    carpeta.mkdir(parents=True, exist_ok=True)

    handler_archivo = RotatingFileHandler(
        carpeta / _NOMBRE_ARCHIVO_LOG, maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding="utf-8",
    )
    handler_archivo.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    logger_raiz = logging.getLogger("agente_qa")
    logger_raiz.setLevel(logging.INFO)
    logger_raiz.addHandler(handler_archivo)

    _logging_configurado = True


def obtener_logger(nombre: str) -> logging.Logger:
    """
    Devuelve un logger hijo de "agente_qa", asegurando que el logging ya esté
    configurado. Uso típico: `log = obtener_logger(__name__)` al inicio de
    cualquier adapter o caso de uso que necesite registrar eventos.
    """
    configurar_logging()
    return logging.getLogger(f"agente_qa.{nombre}")


@dataclass(frozen=True)
class ConfiguracionJira:
    base_url: str
    email: str
    api_token: str


@dataclass(frozen=True)
class ConfiguracionOllama:
    modelo: str
    host: str | None


def cargar_configuracion_jira() -> ConfiguracionJira:
    base_url = os.getenv("JIRA_BASE_URL", "")
    email = os.getenv("JIRA_EMAIL", "")
    api_token = os.getenv("JIRA_API_TOKEN", "")

    faltantes = [
        nombre
        for nombre, valor in [
            ("JIRA_BASE_URL", base_url),
            ("JIRA_EMAIL", email),
            ("JIRA_API_TOKEN", api_token),
        ]
        if not valor
    ]
    if faltantes:
        raise ValueError(
            "Faltan variables de entorno requeridas para Jira: "
            f"{', '.join(faltantes)}. Revisa tu archivo .env (ver .env.example)."
        )

    return ConfiguracionJira(base_url=base_url, email=email, api_token=api_token)


def cargar_configuracion_ollama() -> ConfiguracionOllama:
    modelo = os.getenv("OLLAMA_MODELO", "llama3.1:8b")
    host = os.getenv("OLLAMA_HOST") or None
    return ConfiguracionOllama(modelo=modelo, host=host)

@dataclass(frozen=True)
class ConfiguracionXray:
    client_id: str
    client_secret: str


def cargar_configuracion_xray() -> ConfiguracionXray:
    client_id = os.getenv("XRAY_CLIENT_ID", "")
    client_secret = os.getenv("XRAY_CLIENT_SECRET", "")

    faltantes = [
        nombre
        for nombre, valor in [
            ("XRAY_CLIENT_ID", client_id),
            ("XRAY_CLIENT_SECRET", client_secret),
        ]
        if not valor
    ]
    if faltantes:
        raise ValueError(
            "Faltan variables de entorno requeridas para Xray: "
            f"{', '.join(faltantes)}. Recuerda que Xray usa Client ID + "
            f"Client Secret, NO el mismo token que Jira (ver .env.example)."
        )

    return ConfiguracionXray(client_id=client_id, client_secret=client_secret)

@dataclass(frozen=True)
class ConfiguracionDB:
    host: str
    port: str
    nombre_db: str
    usuario: str
    password: str

    @property
    def url_sqlalchemy(self) -> str:
        """
        URL de conexión en formato SQLAlchemy, usando el driver psycopg
        (versión 3) -- ver Decisión de diseño: psycopg[binary]
        en vez de psycopg2-binary, para evitar problemas de compilación en
        Windows.
        """
        return (
            f"postgresql+psycopg://{self.usuario}:{self.password}"
            f"@{self.host}:{self.port}/{self.nombre_db}"
        )


def cargar_configuracion_db() -> ConfiguracionDB:
    host = os.getenv("DB_HOST", "")
    port = os.getenv("DB_PORT", "")
    nombre_db = os.getenv("DB_NAME", "")
    usuario = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")

    faltantes = [
        nombre
        for nombre, valor in [
            ("DB_HOST", host),
            ("DB_PORT", port),
            ("DB_NAME", nombre_db),
            ("DB_USER", usuario),
            ("DB_PASSWORD", password),
        ]
        if not valor
    ]
    if faltantes:
        raise ValueError(
            "Faltan variables de entorno requeridas para PostgreSQL: "
            f"{', '.join(faltantes)}. Revisa tu archivo .env (ver .env.example). "
            "Recuerda usar el usuario dedicado agente_qa_user, no el "
            "superusuario postgres."
        )

    return ConfiguracionDB(
        host=host, port=port, nombre_db=nombre_db, usuario=usuario, password=password
    )


@dataclass(frozen=True)
class ConfiguracionRAG:
    top_k: int


def cargar_configuracion_rag() -> ConfiguracionRAG:
    """
    Lee TOP_K_RAG desde .env (default: 3).

    Separado en su propia función de carga para que sea fácil de ajustar
    sin tocar el código de negocio -- si en el futuro el hardware mejora
    y se quiere pasar más contexto al LLM, es un cambio de una sola línea
    en .env (TOP_K_RAG=5 o TOP_K_RAG=10).
    """
    top_k_str = os.getenv("TOP_K_RAG", "3")
    try:
        top_k = int(top_k_str)
        if top_k < 1:
            raise ValueError
    except ValueError:
        raise ValueError(
            f"TOP_K_RAG debe ser un entero positivo, se recibió: {top_k_str!r}. "
            "Revisa tu archivo .env."
        )
    return ConfiguracionRAG(top_k=top_k)


@dataclass(frozen=True)
class ConfiguracionVera:
    umbral_score: int


def cargar_configuracion_vera() -> ConfiguracionVera:
    """
    Lee UMBRAL_SCORE_HU desde .env (default: 62).

    Decisión de diseño: el umbral de aprobación de Vera es
    ajustable sin tocar código, mismo patrón que TOP_K_RAG -- si con el uso
    real conviene subirlo o bajarlo, es un cambio de una línea en .env.
    """
    umbral_str = os.getenv("UMBRAL_SCORE_HU", "62")
    try:
        umbral = int(umbral_str)
        if not (0 <= umbral <= 100):
            raise ValueError
    except ValueError:
        raise ValueError(
            f"UMBRAL_SCORE_HU debe ser un entero entre 0 y 100, se recibió: "
            f"{umbral_str!r}. Revisa tu archivo .env."
        )
    return ConfiguracionVera(umbral_score=umbral)


@dataclass(frozen=True)
class ConfiguracionTiempoProceso:
    estados_entrada_qa: frozenset[str]


def cargar_configuracion_tiempo_proceso() -> ConfiguracionTiempoProceso:
    """
    Lee ESTADOS_ENTRADA_QA desde .env (lista separada por comas).

    Decisión confirmada con datos reales (2026-08-30, ver
    adapters/issue_tracker/jira_cloud_adapter.py::obtener_fecha_entrada_qa):
    el nombre del estado que marca "entrada a QA" NO es uniforme entre
    proyectos de esta instancia de Jira -- se confirmaron dos workflows
    reales distintos: uno usa "En Certificación" (ej. proyecto PRJ-06),
    otro usa "In QA" (ej. proyecto PRJ-03). Por eso esto es una lista
    configurable, no un string fijo -- si en el futuro aparece un tercer
    workflow con otro nombre, es un cambio de una línea en .env, no de
    código.

    Default: "En Certificación,In QA" (los dos confirmados). Comparación
    siempre case-insensitive porque Jira no es consistente ni con eso
    ("CODE REVIEW" en mayúsculas junto a "In Development" en el mismo
    workflow, visto en los datos reales).
    """
    raw = os.getenv("ESTADOS_ENTRADA_QA", "En Certificación,In QA")
    estados = frozenset(
        estado.strip().lower() for estado in raw.split(",") if estado.strip()
    )
    if not estados:
        raise ValueError(
            "ESTADOS_ENTRADA_QA no puede quedar vacío. Revisa tu archivo .env "
            "(o quita la variable para usar el default)."
        )
    return ConfiguracionTiempoProceso(estados_entrada_qa=estados)
