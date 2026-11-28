"""
Adapter concreto de IssueTracker para Jira Cloud (REST API v3).

Implementa `obtener_hu()` y `detectar_test_plan()`. `crear_test()` ya NO vive
aquí (ver `ports/issue_tracker.py` para el porqué) -- eso es responsabilidad
de `XrayCloudAdapter`.

Punto crítico (ver checklist, sección 11 de la spec): la descripción de un
issue en Jira Cloud v3 NO es texto plano. Viene en formato ADF (Atlassian
Document Format), un árbol JSON de nodos anidados (paragraph, bulletList,
listItem, text con marks de negrita/cursiva, etc.). Hay que recorrer ese árbol
recursivamente para reconstruir texto plano legible.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from domain.models import HistoriaUsuario, InfoTestPlan
from infrastructure.config import cargar_configuracion_tiempo_proceso, obtener_logger
from ports.issue_tracker import IssueTracker

_log = obtener_logger(__name__)


class JiraCloudAdapter(IssueTracker):
    def __init__(self, base_url: str, email: str, api_token: str, timeout: float = 30.0):
        """
        Args:
            base_url: ej. "https://tuempresa.atlassian.net" (sin slash final).
            email: email de la cuenta de Jira del usuario.
            api_token: token de API personal (Basic Auth: email + token).
            timeout: timeout en segundos para las llamadas HTTP.
        """
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            auth=(email, api_token),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )


        self._cache_tipos_de_link: dict[str, tuple[str, str]] | None = None

    def obtener_hu(self, key: str) -> HistoriaUsuario:
        url = f"{self._base_url}/rest/api/3/issue/{key}"
        params = {"fields": "summary,description,issuelinks"}

        _log.info("Trayendo HU %s desde Jira", key)
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _log.error("Jira respondió %s al pedir %s", exc.response.status_code, key)
            raise
        except httpx.RequestError:
            _log.exception("Fallo de conexión con Jira al pedir %s", key)
            raise

        data = response.json()

        fields = data.get("fields", {})
        titulo = fields.get("summary", "") or ""
        descripcion_adf = fields.get("description")
        descripcion = self._adf_a_texto(descripcion_adf)

        return HistoriaUsuario(key=key, titulo=titulo, descripcion=descripcion)

    def detectar_test_plan(self, key_hu: str) -> list[InfoTestPlan]:
        """
        Busca TODOS los Test Plans vinculados a la HU vía el issue link
        "Será atendido por", usando una búsqueda JQL directa en vez de
        confiar en los campos anidados de `issuelinks` (que en la práctica
        no siempre incluyen el `issuetype` del issue vinculado, lo que hacía
        fallar la detección en silencio).

        JQL usado: `issue in linkedIssues("{key_hu}", "Será atendido por")
        AND type = "Test Plan"` -- equivalente exacto a filtrar por ese link
        y por tipo, pero resuelto por Jira mismo en una sola consulta.

        Devuelve título y estado además de la key (en la misma consulta, sin
        llamadas extra) porque cuando hay más de un Test Plan candidato, solo
        la key no alcanza para que el usuario distinga cuál es cuál.

        Si hay más de un resultado, se devuelven todos (no se elige uno
        automáticamente) para que el usuario decida cuál usar.
        """
        jql = f'issue in linkedIssues("{key_hu}", "Será atendido por") AND type = "Test Plan"'
        url = f"{self._base_url}/rest/api/3/search/jql"
        body = {"jql": jql, "maxResults": 50, "fields": ["key", "summary", "status"]}

        _log.info("Buscando Test Plan(es) para %s con JQL: %s", key_hu, jql)
        try:
            response = self._client.post(url, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _log.error(
                "Jira respondió %s al buscar Test Plan de %s (JQL: %s)",
                exc.response.status_code, key_hu, jql,
            )
            raise
        except httpx.RequestError:
            _log.exception("Fallo de conexión con Jira al buscar Test Plan de %s", key_hu)
            raise

        data = response.json()
        issues = data.get("issues", [])
        test_plans = [
            InfoTestPlan(
                key=issue["key"],
                titulo=issue.get("fields", {}).get("summary", "") or "",
                estado=issue.get("fields", {}).get("status", {}).get("name", "") or "",
            )
            for issue in issues
        ]

        if not test_plans:
            _log.info("No se encontró ningún Test Plan para %s", key_hu)
        elif len(test_plans) == 1:
            _log.info("Test Plan encontrado para %s: %s", key_hu, test_plans[0].key)
        else:
            _log.info(
                "Se encontraron %s Test Plans para %s: %s",
                len(test_plans), key_hu, [tp.key for tp in test_plans],
            )

        return test_plans

    def project_key_de(self, key_issue: str) -> str:
        """
        Devuelve la key del proyecto Jira al que pertenece un issue (ej. dado
        "PROJ-45" devuelve "PROJ"). Se usa para crear el Test en el mismo
        proyecto donde vive el Test Plan detectado, que es el comportamiento
        por defecto pedido en la spec (sección 5) -- a menos que se indique
        explícitamente otro proyecto destino (`project_key_destino`).

        Nota: technically la key del proyecto siempre se puede derivar de la
        propia key del issue (todo antes del último "-"), pero se pide el
        dato a Jira en vez de parsearlo a mano por robustez: algunas keys de
        proyecto pueden contener guiones, lo que rompería un parseo naive.
        """
        url = f"{self._base_url}/rest/api/3/issue/{key_issue}"
        params = {"fields": "project"}

        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _log.error("Jira respondió %s al pedir el proyecto de %s", exc.response.status_code, key_issue)
            raise
        except httpx.RequestError:
            _log.exception("Fallo de conexión con Jira al pedir el proyecto de %s", key_issue)
            raise

        data = response.json()
        return data["fields"]["project"]["key"]

    def obtener_fecha_entrada_qa(self, key_hu: str) -> datetime | None:
        """
        Busca en el changelog de la HU la PRIMERA transición de estado cuyo
        estado destino (`toString`) coincida, sin distinguir mayúsculas de
        minúsculas, con alguno de los nombres configurados en
        ESTADOS_ENTRADA_QA (ver infrastructure.config).

        Confirmado contra datos reales de esta instancia (2026-08-30, no
        adivinado): el nombre de este estado NO es uniforme entre proyectos
        -- un workflow real usa "En Certificación" (ej. PRJ-06), otro usa
        "In QA" (ej. PRJ-03). Por eso se compara contra una lista configurable
        en vez de un string fijo, y la comparación es case-insensitive
        (los datos reales ni siquiera son consistentes en mayúsculas: se
        vio "CODE REVIEW" junto a "In Development" en el mismo workflow).

        Límite conocido, documentado en vez de resuelto sin confirmación:
        no pagina el changelog (maxResults=100). Para una HU con más de 100
        transiciones de CUALQUIER campo (no solo estado) esto podría no
        traer la transición real -- no se resolvió proactivamente porque
        implica decidir cómo paginar (¿todas las páginas siempre, o parar
        en la primera coincidencia?) y no hay evidencia todavía de que
        algún HU real se acerque a ese volumen de transiciones.
        """
        estados_qa = cargar_configuracion_tiempo_proceso().estados_entrada_qa

        url = f"{self._base_url}/rest/api/3/issue/{key_hu}/changelog"
        params = {"maxResults": 100}

        _log.info("Buscando fecha de entrada a QA de %s", key_hu)
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _log.error(
                "Jira respondió %s al pedir el changelog de %s",
                exc.response.status_code, key_hu,
            )
            raise
        except httpx.RequestError:
            _log.exception("Fallo de conexión con Jira al pedir el changelog de %s", key_hu)
            raise

        data = response.json()

        for entrada in data.get("values", []):
            fecha_str = entrada.get("created")
            for item in entrada.get("items", []):
                if item.get("field") != "status":
                    continue
                estado_destino = (item.get("toString") or "").strip().lower()
                if estado_destino in estados_qa:
                    _log.info(
                        "%s entró a QA el %s (estado '%s')",
                        key_hu, fecha_str, item.get("toString"),
                    )
                    return self._parsear_fecha_jira(fecha_str)

        _log.info(
            "%s nunca pasó por ninguno de los estados de entrada a QA "
            "configurados (%s)",
            key_hu, sorted(estados_qa),
        )
        return None

    def vincular_test_plan_a_hu(self, key_hu: str, key_test_plan: str) -> None:
        """
        Crea el issue link entre la HU y un Test Plan (usado cuando se crea
        un Test Plan nuevo porque no se encontró ninguno existente -- así la
        próxima vez `detectar_test_plan()` ya lo encuentra solo).

        Importante (corregido tras un error real en producción): el campo
        `type.name` que espera la API NO es ninguno de los dos textos
        visibles del link ("Será atendido por" / "Atiende") -- esos son los
        textos `inward`/`outward` de visualización. El `name` es el nombre
        interno del tipo de link, que puede ser un tercer string distinto
        (ej. "Blocks" tiene inward "is blocked by" y outward "blocks", pero
        ninguno de esos dos es el `name`). Por eso este método resuelve el
        `name` real consultando `/rest/api/3/issueLinkType` en vez de
        asumirlo, buscando cuál tipo tiene "Será atendido por" o "Atiende"
        como inward/outward.

        Dirección confirmada por el usuario contra su instancia: parado en
        la HU se ve "Será atendido por" (inward, apunta al Test Plan);
        parado en el Test Plan se ve "Atiende" (outward, apunta a la HU).
        Por eso HU = `inwardIssue`, Test Plan = `outwardIssue`.
        """
        nombre_real = self._resolver_nombre_real_de_link()

        url = f"{self._base_url}/rest/api/3/issueLink"
        body = {
            "type": {"name": nombre_real},
            "inwardIssue": {"key": key_hu},
            "outwardIssue": {"key": key_test_plan},
        }

        _log.info(
            "Vinculando Test Plan %s a HU %s vía tipo de link '%s'",
            key_test_plan, key_hu, nombre_real,
        )
        try:
            response = self._client.post(url, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detalle = self._extraer_detalle_error(exc.response)
            _log.error(
                "Jira respondió %s al vincular %s con %s. Detalle: %s",
                exc.response.status_code, key_hu, key_test_plan, detalle,
            )
            raise ValueError(
                f"Jira respondió {exc.response.status_code} al vincular {key_hu} "
                f"con {key_test_plan}: {detalle}"
            ) from exc
        except httpx.RequestError:
            _log.exception("Fallo de conexión con Jira al vincular %s con %s", key_hu, key_test_plan)
            raise

    def _resolver_nombre_real_de_link(self) -> str:
        """
        Busca, entre todos los tipos de issue link configurados en la
        instancia, el que tiene "Será atendido por" o "Atiende" como
        `inward`/`outward`, y devuelve su `name` interno real (el que la API
        de creación de links exige en `type.name`).

        Resultado cacheado en la instancia: los tipos de link no cambian
        durante una sesión, así que no hace falta volver a pedirlos.
        """
        if self._cache_tipos_de_link is None:
            self._cache_tipos_de_link = self._cargar_tipos_de_link()

        textos_esperados = {"será atendido por", "atiende"}
        for nombre, (inward, outward) in self._cache_tipos_de_link.items():
            if inward.strip().lower() in textos_esperados or outward.strip().lower() in textos_esperados:
                return nombre

        disponibles = ", ".join(sorted(self._cache_tipos_de_link.keys())) or "(ninguno)"
        raise ValueError(
            "No se encontró ningún tipo de issue link cuyo inward/outward sea "
            "'Será atendido por' o 'Atiende' en esta instancia de Jira. "
            f"Tipos de link disponibles (por su nombre interno): {disponibles}. "
            "Revisa el nombre exacto del link en Jira (Configuración > "
            "Incidencias > Tipos de vínculo de incidencias)."
        )

    def _cargar_tipos_de_link(self) -> dict[str, tuple[str, str]]:
        """
        Trae todos los tipos de issue link de la instancia vía
        `/rest/api/3/issueLinkType`, devolviendo un dict
        {name: (inward, outward)}.
        """
        url = f"{self._base_url}/rest/api/3/issueLinkType"

        _log.info("Cargando tipos de issue link disponibles en Jira")
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _log.error("Jira respondió %s al pedir los tipos de issue link", exc.response.status_code)
            raise
        except httpx.RequestError:
            _log.exception("Fallo de conexión con Jira al pedir los tipos de issue link")
            raise

        data = response.json()
        return {
            tipo["name"]: (tipo.get("inward", ""), tipo.get("outward", ""))
            for tipo in data.get("issueLinkTypes", [])
        }

    @staticmethod
    def _extraer_detalle_error(response: httpx.Response) -> str:
        """
        Jira normalmente devuelve detalles útiles del error en el body JSON
        (`errorMessages`, `errors`), que httpx no expone en el mensaje de
        excepción por defecto (solo da "404 Not Found" genérico). Esto
        intenta extraer ese detalle para que el mensaje de error sea
        diagnosticable sin tener que inspeccionar logs HTTP crudos.
        """
        try:
            cuerpo = response.json()
        except ValueError:
            return response.text or "(sin cuerpo de respuesta)"

        mensajes = cuerpo.get("errorMessages") or []
        errores_por_campo = cuerpo.get("errors") or {}
        partes = list(mensajes) + [f"{campo}: {msg}" for campo, msg in errores_por_campo.items()]
        return "; ".join(partes) if partes else str(cuerpo)

    def cerrar(self) -> None:
        """Cierra el cliente HTTP. Llamar al terminar de usar el adapter."""
        self._client.close()


    @staticmethod
    def _parsear_fecha_jira(fecha_str: str) -> datetime:
        """
        Convierte un timestamp de Jira (ej. "2026-08-17T12:26:03.228-0500")
        a un `datetime` con timezone.

        Usa `strptime` con `%z` en vez de `datetime.fromisoformat()`: Jira
        devuelve el offset sin los dos puntos ("-0500", no "-05:00"), y
        `fromisoformat()` solo tolera ese formato de manera consistente
        desde Python 3.11 -- `strptime` con `%z` lo soporta desde antes,
        sin depender de qué versión de Python corra el entorno real.
        """
        return datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M:%S.%f%z")

    @staticmethod
    def _adf_a_texto(nodo_adf: dict | None) -> str:
        """
        Convierte un documento ADF (o un nodo cualquiera del árbol) a texto
        plano, recorriendo recursivamente sus nodos hijos.

        Soporta los tipos de nodo más comunes en descripciones de HU:
        paragraph, text, bulletList/orderedList + listItem, heading,
        hardBreak. Cualquier tipo no reconocido simplemente se ignora a nivel
        de marca/formato pero se sigue recorriendo su `content` si lo tiene,
        para no perder texto anidado dentro de estructuras menos comunes
        (ej. tablas, paneles de información).
        """
        if not nodo_adf:
            return ""

        lineas: list[str] = []
        JiraCloudAdapter._recorrer_nodo_adf(nodo_adf, lineas)
        return "\n".join(linea for linea in lineas if linea is not None).strip()

    @staticmethod
    def _recorrer_nodo_adf(nodo: dict, lineas: list[str], prefijo: str = "") -> None:
        tipo = nodo.get("type")
        contenido = nodo.get("content", [])

        if tipo == "text":


            texto = nodo.get("text", "")
            if lineas and not lineas[-1].endswith(("\n", "")) and lineas[-1] != "":
                lineas[-1] += texto
            else:
                lineas.append(prefijo + texto)
            return

        if tipo == "hardBreak":
            lineas.append("")
            return

        if tipo in ("bulletList", "orderedList"):
            for hijo in contenido:
                JiraCloudAdapter._recorrer_nodo_adf(hijo, lineas, prefijo="- ")
            return

        if tipo == "listItem":


            sub_lineas: list[str] = []
            for hijo in contenido:
                JiraCloudAdapter._recorrer_nodo_adf(hijo, sub_lineas)
            texto_item = " ".join(l for l in sub_lineas if l)
            lineas.append(f"{prefijo}{texto_item}")
            return

        if tipo in ("paragraph", "heading"):
            sub_lineas: list[str] = []
            for hijo in contenido:
                JiraCloudAdapter._recorrer_nodo_adf(hijo, sub_lineas)
            texto_parrafo = "".join(l for l in sub_lineas if l is not None)
            lineas.append(texto_parrafo)
            return


        for hijo in contenido:
            JiraCloudAdapter._recorrer_nodo_adf(hijo, lineas, prefijo)
