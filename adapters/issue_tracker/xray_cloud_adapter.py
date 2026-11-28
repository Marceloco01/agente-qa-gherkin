"""
Adapter concreto para Xray Cloud — esqueleto de referencia para Fase 2.

NO se usa en Fase 1. Se incluye desde ya porque la spec (sección 5) identificó
algo importante: Xray usa un mecanismo de autenticación DISTINTO al de Jira.

- Jira: Basic Auth (email + API token personal).
- Xray: Client ID + Client Secret (generados desde la sección "API Keys" de la
  configuración de la app Xray en Jira, no desde la cuenta personal de
  Atlassian), con un flujo de autenticación en dos pasos:
    1. POST a /api/v2/authenticate con {client_id, client_secret} -> devuelve
       un token de sesión (string JWT).
    2. Ese token se usa como Bearer token en cada llamada posterior a la API
       de Xray.
  El Client ID/Secret no expiran, pero el token de sesión sí: expira a las 24
  horas. El adapter debe regenerarlo automáticamente cuando haga falta, no
  asumir que un token obtenido una vez sigue siendo válido para siempre.

Por eso es un adapter separado de `jira_cloud_adapter.py`: mezclar dos
mecanismos de auth distintos en una sola clase sería confuso y frágil.

Nota de diseño: esta clase NO implementa el port `IssueTracker` completo (no
hereda de `ABC` de ese contrato). Solo tiene el método `crear_test()`, que es
lo único que le compete a Xray. Si heredara de `IssueTracker` pero dejara
`obtener_hu()` y `detectar_test_plan()` sin implementación real, cualquier
código que reciba un `IssueTracker` esperando que esos métodos funcionen
podría romperse al recibir esta clase en su lugar (viola el Principio de
Sustitución de Liskov). En Fase 2, la capa de aplicación usará
`JiraCloudAdapter` para HU/Test Plan y `XrayCloudAdapter` para crear el Test,
como dos colaboradores distintos — no como dos implementaciones
intercambiables de la misma interfaz.

Fase 2 implementa `crear_test()` aquí, contra la API GraphQL de Xray
(confirmada como la opción correcta para tests tipo Cucumber/Gherkin, en vez
de la REST clásica que tiene menos soporte para este tipo de test).
"""

from __future__ import annotations

import time

import httpx

from domain.models import TestCase
from infrastructure.config import obtener_logger
from ports.test_management import TestManagementSystem

_log = obtener_logger(__name__)

_URL_AUTENTICACION = "https://xray.cloud.getxray.app/api/v2/authenticate"
_URL_GRAPHQL = "https://xray.cloud.getxray.app/api/v2/graphql"


_MARGEN_SEGURIDAD_SEGUNDOS = 5 * 60
_DURACION_TOKEN_SEGUNDOS = 24 * 60 * 60


_PATRON_ERROR_REINDEXACION = "may need to be re-indexed"
_REINTENTOS_REINDEXACION = 4
_ESPERA_INICIAL_REINDEXACION_SEGUNDOS = 2.0


class XrayCloudAdapter(TestManagementSystem):
    def __init__(self, client_id: str, client_secret: str, timeout: float = 30.0):
        """
        Args:
            client_id: Client ID generado en la app Xray dentro de Jira.
            client_secret: Client Secret asociado a ese Client ID.
            timeout: timeout en segundos para las llamadas HTTP.
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = httpx.Client(timeout=timeout)
        self._token: str | None = None
        self._token_obtenido_en: float = 0.0

    def _token_valido(self) -> str:
        """
        Devuelve un token de sesión válido, autenticándose de nuevo si no hay
        token todavía o si el que hay está a punto de expirar (con margen de
        seguridad de 5 minutos antes del límite real de 24 horas).
        """
        ahora = time.monotonic()
        token_por_expirar = (
            self._token is None
            or (ahora - self._token_obtenido_en) >= (_DURACION_TOKEN_SEGUNDOS - _MARGEN_SEGURIDAD_SEGUNDOS)
        )

        if token_por_expirar:
            _log.info("Autenticando contra Xray (token nuevo o por expirar)")
            try:
                respuesta = self._client.post(
                    _URL_AUTENTICACION,
                    json={"client_id": self._client_id, "client_secret": self._client_secret},
                )
                respuesta.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _log.error("Xray rechazó la autenticación: %s", exc.response.status_code)
                raise
            except httpx.RequestError:
                _log.exception("Fallo de conexión al autenticar contra Xray")
                raise


            self._token = respuesta.json()
            self._token_obtenido_en = ahora

        assert self._token is not None
        return self._token

    def _ejecutar_graphql(self, query: str) -> dict:
        """
        Ejecuta una query/mutación GraphQL contra Xray, manejando auth y
        errores de forma centralizada para no repetir ese código en cada
        método público.

        Nota sobre errores de GraphQL: a diferencia de REST, GraphQL puede
        devolver HTTP 200 con un campo "errors" en el body cuando algo salió
        mal (ej. JQL inválido, campo de Jira inexistente). Por eso se chequea
        ese campo explícitamente además del status HTTP.
        """
        token = self._token_valido()

        try:
            respuesta = self._client.post(
                _URL_GRAPHQL,
                json={"query": query},
                headers={"Authorization": f"Bearer {token}"},
            )
            respuesta.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _log.error("Xray GraphQL respondió %s", exc.response.status_code)
            raise
        except httpx.RequestError:
            _log.exception("Fallo de conexión con Xray GraphQL")
            raise

        cuerpo = respuesta.json()
        if cuerpo.get("errors"):
            _log.error("Xray GraphQL devolvió errores: %s", cuerpo["errors"])
            raise ValueError(f"Xray GraphQL devolvió errores: {cuerpo['errors']}")

        return cuerpo["data"]

    def _ejecutar_graphql_con_reintento_de_indexacion(self, query: str) -> dict:
        """
        Igual que `_ejecutar_graphql()`, pero reintenta automáticamente con
        espera creciente (2s, 4s, 8s, 16s) si el error es específicamente de
        re-indexación pendiente en Xray (mensaje "...may need to be
        re-indexed", visto en la práctica justo después de crear un Test o
        Test Plan nuevo -- Xray no tiene todavía la info de Jira de ese
        issue disponible internamente). Cualquier otro tipo de error de
        GraphQL se propaga de inmediato, sin reintentar.
        """
        espera = _ESPERA_INICIAL_REINDEXACION_SEGUNDOS

        for intento in range(1, _REINTENTOS_REINDEXACION + 1):
            try:
                return self._ejecutar_graphql(query)
            except ValueError as exc:
                if _PATRON_ERROR_REINDEXACION not in str(exc) or intento == _REINTENTOS_REINDEXACION:
                    raise
                _log.warning(
                    "Xray todavía no tiene indexada la info de Jira para este "
                    "issue (intento %s/%s). Reintentando en %.0fs...",
                    intento, _REINTENTOS_REINDEXACION, espera,
                )
                time.sleep(espera)
                espera *= 2


        raise AssertionError("No debería llegar aquí: _REINTENTOS_REINDEXACION debe ser >= 1.")

    def crear_test(
        self,
        test_case: TestCase,
        key_test_plan: str | None,
        project_key_destino: str | None = None,
    ) -> str:
        if not project_key_destino:
            raise ValueError(
                "project_key_destino es obligatorio: XrayCloudAdapter no conoce "
                "Jira, así que no puede resolverlo por su cuenta a partir del "
                "Test Plan. Quien llama (capa de aplicación) debe resolverlo "
                "primero, ej. con JiraCloudAdapter.project_key_de(key_test_plan)."
            )

        issue_id = self._crear_test_xray(test_case, project_key_destino)

        if key_test_plan:
            self._vincular_a_test_plan(issue_id_test=issue_id, key_test_plan=key_test_plan)
        else:
            _log.info(
                "Test %s creado sin Test Plan vinculado (no se encontró Test "
                "Plan o el usuario decidió continuar sin vínculo).",
                issue_id,
            )

        return self._obtener_key_de_issue_id(issue_id)

    def crear_test_plan(self, summary: str, project_key: str) -> str:
        """
        Crea un Test Plan nuevo en Xray, sin tests asociados todavía.

        Se usa cuando `JiraCloudAdapter.detectar_test_plan()` no encontró
        ningún Test Plan existente para la HU y el usuario decide crear uno
        nuevo en vez de continuar sin vínculo.

        Args:
            summary: título del Test Plan (ej. "Test Plan - <título de la HU>").
            project_key: proyecto Jira donde crear el Test Plan.

        Returns:
            La key de Jira del Test Plan creado (ej. "PROJ-50").
        """
        summary_escapado = self._escapar_para_graphql(summary)

        query = f"""
        mutation {{
            createTestPlan(
                jira: {{
                    fields: {{ summary: "{summary_escapado}", project: {{ key: "{project_key}" }} }}
                }}
            ) {{
                testPlan {{
                    issueId
                }}
                warnings
            }}
        }}
        """

        _log.info("Creando Test Plan '%s' en proyecto %s", summary, project_key)
        datos = self._ejecutar_graphql(query)

        resultado = datos["createTestPlan"]
        if resultado.get("warnings"):
            _log.warning("Xray devolvió warnings al crear el Test Plan: %s", resultado["warnings"])

        issue_id = resultado["testPlan"]["issueId"]
        return self._obtener_key_de_issue_id_test_plan(issue_id)


    def _crear_test_xray(self, test_case: TestCase, project_key: str) -> str:
        """
        Crea el Test tipo Cucumber en Xray vía la mutación `createTest`, y
        devuelve su `issueId` interno (NO la key de Jira -- ese es un campo
        aparte que se resuelve después, ver `_obtener_key_de_issue_id`).
        """
        gherkin_escapado = self._escapar_para_graphql(test_case.gherkin)
        titulo_escapado = self._escapar_para_graphql(test_case.titulo or "(sin título)")

        query = f"""
        mutation {{
            createTest(
                testType: {{ name: "Cucumber" }},
                gherkin: "{gherkin_escapado}",
                jira: {{
                    fields: {{ summary: "{titulo_escapado}", project: {{ key: "{project_key}" }} }}
                }}
            ) {{
                test {{
                    issueId
                }}
                warnings
            }}
        }}
        """

        _log.info("Creando Test en Xray para %s (proyecto %s)", test_case.hu_key, project_key)
        datos = self._ejecutar_graphql(query)

        resultado = datos["createTest"]
        if resultado.get("warnings"):
            _log.warning("Xray devolvió warnings al crear el Test: %s", resultado["warnings"])

        return resultado["test"]["issueId"]

    def _vincular_a_test_plan(self, issue_id_test: str, key_test_plan: str) -> None:
        """
        Vincula el Test recién creado al Test Plan indicado. Primero resuelve
        el `issueId` interno del Test Plan a partir de su key (la mutación
        `addTestsToTestPlan` exige `issueId`, no la key de Jira).
        """
        issue_id_test_plan = self._resolver_issue_id_de_test_plan(key_test_plan)

        query = f"""
        mutation {{
            addTestsToTestPlan(
                issueId: "{issue_id_test_plan}",
                testIssueIds: ["{issue_id_test}"]
            ) {{
                addedTests
                warning
            }}
        }}
        """

        _log.info("Vinculando Test %s al Test Plan %s", issue_id_test, key_test_plan)
        datos = self._ejecutar_graphql(query)

        resultado = datos["addTestsToTestPlan"]
        if resultado.get("warning"):
            _log.warning("Xray devolvió warning al vincular al Test Plan: %s", resultado["warning"])
        if issue_id_test not in (resultado.get("addedTests") or []):
            _log.error(
                "El Test %s no figura entre los addedTests al vincular a %s",
                issue_id_test, key_test_plan,
            )
            raise ValueError(
                f"No se pudo confirmar la vinculación del Test al Test Plan {key_test_plan}."
            )

    def _resolver_issue_id_de_test_plan(self, key_test_plan: str) -> str:
        query = f"""
        {{
            getTestPlans(jql: "key = {key_test_plan}", limit: 1) {{
                results {{
                    issueId
                }}
            }}
        }}
        """
        datos = self._ejecutar_graphql(query)
        resultados = datos["getTestPlans"]["results"]
        if not resultados:
            raise ValueError(f"Xray no encontró ningún Test Plan con key {key_test_plan}.")
        return resultados[0]["issueId"]

    def _obtener_key_de_issue_id(self, issue_id: str) -> str:
        """
        Usa la query singular `getTest(issueId: ...)` en vez de `getTests`
        con JQL. Importante: justo después de crear un issue, una búsqueda
        por JQL puede no encontrarlo todavía -- Jira no garantiza
        consistencia inmediata entre escritura y búsqueda (el índice de
        búsqueda puede tardar unos segundos en reflejar el cambio). La query
        singular por `issueId` no depende de ese índice, así que no tiene
        ese problema.

        Aun con la query singular, Xray puede devolver un error de
        re-indexación pendiente al pedir los campos de `jira(...)` de un
        issue recién creado -- por eso se usa el helper con reintento, no
        `_ejecutar_graphql()` directo.
        """
        query = f"""
        {{
            getTest(issueId: "{issue_id}") {{
                jira(fields: ["key"])
            }}
        }}
        """
        datos = self._ejecutar_graphql_con_reintento_de_indexacion(query)
        resultado = datos.get("getTest")
        if not resultado:
            raise ValueError(f"No se pudo recuperar la key de Jira para el Test {issue_id} recién creado.")
        return resultado["jira"]["key"]

    def _obtener_key_de_issue_id_test_plan(self, issue_id: str) -> str:
        """
        Usa la query singular `getTestPlan(issueId: ...)` por la misma razón
        que `_obtener_key_de_issue_id`, incluyendo el reintento ante errores
        de re-indexación pendiente.
        """
        query = f"""
        {{
            getTestPlan(issueId: "{issue_id}") {{
                jira(fields: ["key"])
            }}
        }}
        """
        datos = self._ejecutar_graphql_con_reintento_de_indexacion(query)
        resultado = datos.get("getTestPlan")
        if not resultado:
            raise ValueError(f"No se pudo recuperar la key de Jira para el Test Plan {issue_id} recién creado.")
        return resultado["jira"]["key"]

    @staticmethod
    def _escapar_para_graphql(texto: str) -> str:
        """
        Escapa un string para insertarlo de forma segura dentro de una query
        GraphQL construida como texto plano (comillas dobles y saltos de
        línea, que son los caracteres que rompen la sintaxis si no se
        escapan). El Gherkin generado por el LLM siempre tiene saltos de
        línea, así que esto es obligatorio, no un caso límite raro.
        """
        return texto.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def cerrar(self) -> None:
        """Cierra el cliente HTTP. Llamar al terminar de usar el adapter."""
        self._client.close()
