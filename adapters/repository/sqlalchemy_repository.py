"""
Adapter concreto del port `Repository`, usando SQLAlchemy + PostgreSQL.

Fase 3. Implementa los métodos definidos en `ports/repository.py`,
traduciendo entre las dataclasses de dominio (`domain/models.py`) y las
clases ORM (`infrastructure/db/models_orm.py`).

Decisión de diseño (adoptada para este diseño): sesión inyectada, no
administrada por este adapter. `SqlAlchemyRepository` recibe una `Session`
de SQLAlchemy ya abierta en su constructor -- no crea ni cierra su propia
sesión, y no hace `commit()` ni `rollback()` por su cuenta. Quien
orquesta (un caso de uso en `application/`, ej. `generar_test_cases.py`) es
responsable de abrir la sesión con `infrastructure.db.conexion.obtener_sesion()`
y de envolver en ese mismo bloque todas las llamadas a este Repository que
deban ser atómicas entre sí.

Por qué importa esto para el caso real del usuario: si
`generar_test_cases.py` llama a `guardar_hu()` y luego a
`guardar_test_cases()` para una lista de 5 test cases, y el tercero falla,
todo el bloque se revierte (incluida la HU) -- no queda un estado a medias
en la base de datos.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from domain.models import EstadoTestCase, HistoriaUsuario, MensajeFeedback, TestCase, TipoCobertura
from infrastructure.db.models_orm import (
    HistoriaUsuarioORM,
    MensajeFeedbackORM,
    TestCaseORM,
)
from ports.repository import Repository


class SqlAlchemyRepository(Repository):
    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    @staticmethod
    def _a_uuid(test_case_id: str) -> uuid.UUID:
        """
        Convierte el `id` de dominio (siempre `str`, ver
        `domain.models.TestCase.id`) al tipo real de la columna ORM
        (`uuid.UUID`, ver `infrastructure.db.models_orm.TestCaseORM.id`).

        Centralizado en un solo lugar porque los tres métodos que reciben
        `test_case_id` (`actualizar_estado`, `guardar_feedback`,
        `obtener_test_case`) necesitan esta misma conversión -- repetirla
        en cada uno fue justo el bug real detectado al probar este
        adapter contra una base de datos real (SQLAlchemy no convierte el
        string automáticamente, falla con un AttributeError poco claro al
        hacer flush/commit).

        Lanza `ValueError` con mensaje claro si `test_case_id` no es un
        UUID válido, en vez de dejar que el error críptico de SQLAlchemy
        llegue hasta el caller.
        """
        try:
            return uuid.UUID(test_case_id)
        except (ValueError, AttributeError) as error:
            raise ValueError(
                f"test_case_id={test_case_id!r} no es un UUID válido."
            ) from error

    def guardar_hu(self, hu: HistoriaUsuario) -> None:
        """
        Inserta o actualiza la HU.

        Usa `merge()` (UPSERT por PK) en vez de `add()` directo: si la
        misma HU ya se había generado antes (ej. el usuario vuelve a pegar
        la misma key para regenerar test cases), no debe fallar con un
        error de PK duplicada -- simplemente actualiza la fila existente
        con los datos más recientes (título/descripción pueden haber
        cambiado en Jira desde la última vez).

        Nota (fase de agentes humanizados): a propósito NO se incluyen acá
        `vera_score`/`vera_aprobada`/`vera_motivo_bloqueo` ni
        `fecha_fin_proceso` -- esos campos se actualizan solo vía
        `actualizar_evaluacion_vera()` y `actualizar_fecha_fin_proceso()`,
        que hacen un update explícito (get + set) en vez de un merge de
        objeto completo. Si se incluyeran acá, cada vez que se regenera una
        HU (este método se llama de nuevo) se pisarían con `None` los
        valores ya calculados en una corrida anterior.
        """
        hu_orm = HistoriaUsuarioORM(
            key=hu.key,
            titulo=hu.titulo,
            descripcion=hu.descripcion,
            test_plan_key=hu.test_plan_key,
            fecha_inicio_proceso=hu.fecha_inicio_proceso,
        )
        self._sesion.merge(hu_orm)

    def guardar_test_cases(self, test_cases: list[TestCase]) -> None:
        """
        Inserta los test cases generados.

        A diferencia de `guardar_hu()`, acá se usa `add_all()` (inserción
        simple), no `merge()`: cada `TestCase.id` es un UUID generado al
        crear el objeto en memoria (ver `domain/models.py`), así que en el
        flujo normal -- guardar al momento de generar, ver decisión
        adoptada para este diseño -- estos IDs son siempre nuevos y no hay
        riesgo de colisión con filas existentes.

        El historial de feedback (`historial_feedback`) NO se persiste
        acá: en el momento de generar, los test cases recién creados
        todavía no tienen feedback (`historial_feedback` viene vacío por
        default en el dominio). El feedback se persiste después, mensaje a
        mensaje, vía `guardar_feedback()`, cuando el usuario realmente
        rechaza y escribe algo.
        """
        test_cases_orm = [
            TestCaseORM(
                id=self._a_uuid(tc.id),
                hu_key=tc.hu_key,
                titulo=tc.titulo,
                gherkin=tc.gherkin,
                estado=tc.estado.value,
                xray_test_key=tc.xray_test_key,
                version_contenido=tc.version_contenido,
                alucinacion_detectada=tc.alucinacion_detectada,
                alucinacion_detalle=tc.alucinacion_detalle,


                alucinacion_detectada_alguna_vez=tc.alucinacion_detectada,
                version_contenido_al_detectar_alucinacion=(
                    tc.version_contenido if tc.alucinacion_detectada else None
                ),
                tipo_cobertura=tc.tipo_cobertura.value if tc.tipo_cobertura else None,
            )
            for tc in test_cases
        ]
        self._sesion.add_all(test_cases_orm)

    def actualizar_estado(self, test_case_id: str, estado: str, autor: str) -> None:
        """
        Actualiza el estado de un test case ya persistido.

        Valida `estado` contra `EstadoTestCase` (el Enum de dominio) ANTES
        de tocar la base de datos -- aunque la columna en Postgres sea
        VARCHAR sin restricción a nivel de esquema (decisión confirmada:
        VARCHAR, no ENUM nativo, para no necesitar una migración cada vez
        que el dominio agregue un estado nuevo), la validación de qué
        valores son válidos sigue viviendo en esta capa, apoyándose en el
        Enum de Python que ya es robusto.

        El parámetro `autor` ("usuario" o "agente", ver `ports/repository.py`)
        no se persiste en `test_cases` -- esa tabla no tiene una columna
        para quién hizo el cambio de estado. Se recibe en la firma porque
        así lo define el port, pero por ahora no hay un lugar de Fase 3
        donde guardarlo de forma significativa (ver nota en
        `ports/repository.py` sobre trazabilidad por persona física,
        pendiente para una fase futura si el equipo crece a varios QA).
        """


        EstadoTestCase(estado)

        test_case_orm = self._sesion.get(TestCaseORM, self._a_uuid(test_case_id))
        if test_case_orm is None:
            raise ValueError(
                f"No se encontró el test case con id={test_case_id} para "
                "actualizar su estado. ¿Se guardó con guardar_test_cases() "
                "antes de intentar actualizarlo?"
            )

        test_case_orm.estado = estado

    def actualizar_test_case_completo(self, test_case: TestCase) -> None:
        """
        Sincroniza gherkin, titulo, estado y version_contenido con la base
        de datos -- usado tras una regeneración, donde estos 4 campos
        cambian simultáneamente (ver docstring en ports/repository.py).
        """
        test_case_orm = self._sesion.get(TestCaseORM, self._a_uuid(test_case.id))
        if test_case_orm is None:
            raise ValueError(
                f"No se encontró el test case con id={test_case.id} para "
                "sincronizarlo. ¿Se guardó con guardar_test_cases() antes?"
            )

        test_case_orm.gherkin = test_case.gherkin
        test_case_orm.titulo = test_case.titulo
        test_case_orm.estado = test_case.estado.value
        test_case_orm.version_contenido = test_case.version_contenido

    def actualizar_alucinacion(
        self,
        test_case_id: str,
        alucinacion_detectada: bool,
        alucinacion_detalle: str | None,
    ) -> None:
        """
        Sincroniza el resultado de verificar_alucinacion() para un test case
        ya persistido. Separado de actualizar_test_case_completo() -- ver
        justificación en ports/repository.py.
        """
        test_case_orm = self._sesion.get(TestCaseORM, self._a_uuid(test_case_id))
        if test_case_orm is None:
            raise ValueError(
                f"No se encontró el test case con id={test_case_id} para "
                "sincronizar su estado de alucinación. ¿Se guardó con "
                "guardar_test_cases() antes?"
            )

        test_case_orm.alucinacion_detectada = alucinacion_detectada
        test_case_orm.alucinacion_detalle = alucinacion_detalle


        if alucinacion_detectada and not test_case_orm.alucinacion_detectada_alguna_vez:
            test_case_orm.alucinacion_detectada_alguna_vez = True
            test_case_orm.version_contenido_al_detectar_alucinacion = (
                test_case_orm.version_contenido
            )

    def actualizar_evaluacion_vera(
        self,
        hu_key: str,
        score: int | None,
        aprobada: bool,
        motivo_bloqueo: str | None,
        umbral_aplicado: int | None = None,
    ) -> None:
        """
        Sincroniza el resultado de Vera con la HU ya persistida (ver
        justificación de por qué es un método separado de `guardar_hu()`
        en el docstring de ese método, y en `ports/repository.py`).
        """
        hu_orm = self._sesion.get(HistoriaUsuarioORM, hu_key)
        if hu_orm is None:
            raise ValueError(
                f"No se encontró la HU {hu_key} para actualizar la evaluación "
                "de Vera. ¿Se guardó con guardar_hu() antes?"
            )
        hu_orm.vera_score = score
        hu_orm.vera_aprobada = aprobada
        hu_orm.vera_motivo_bloqueo = motivo_bloqueo
        hu_orm.vera_umbral_aplicado = umbral_aplicado

    def registrar_generacion(
        self,
        hu_key: str,
        forzada: bool,
        descripcion_usada: str | None,
    ) -> None:
        """Ver la justificación en `ports/repository.py`."""
        hu_orm = self._sesion.get(HistoriaUsuarioORM, hu_key)
        if hu_orm is None:
            raise ValueError(
                f"No se encontró la HU {hu_key} para registrar la generación. "
                "¿Se guardó con guardar_hu() antes?"
            )
        hu_orm.generacion_forzada = forzada


        if descripcion_usada is not None:
            hu_orm.descripcion_usada = descripcion_usada

    def actualizar_fecha_fin_proceso(self, hu_key: str) -> None:
        """
        Marca `fecha_fin_proceso = ahora` para la HU, llamado desde
        `application/subir_a_xray.py` cuando un test case de esa HU se sube
        a Xray. Se puede llamar más de una vez para la misma HU (si tiene
        varios test cases y cada uno se sube por separado) -- el valor final
        que queda es el del último llamado, que es exactamente lo que se
        quiere medir (cuándo terminó de subirse todo el lote).
        """
        hu_orm = self._sesion.get(HistoriaUsuarioORM, hu_key)
        if hu_orm is None:
            raise ValueError(
                f"No se encontró la HU {hu_key} para marcar fecha_fin_proceso. "
                "¿Se guardó con guardar_hu() antes?"
            )
        hu_orm.fecha_fin_proceso = datetime.now(timezone.utc)

    def guardar_feedback(self, test_case_id: str, autor: str, mensaje: str) -> None:
        """
        Agrega un mensaje al historial de feedback de un test case.

        El orden del chat se reconstruye después por `fecha_creacion`
        (ver `order_by` en la relación `TestCaseORM.historial_feedback`,
        en `models_orm.py`) -- no hace falta un campo de "orden" manual.
        """
        mensaje_orm = MensajeFeedbackORM(
            test_case_id=self._a_uuid(test_case_id), autor=autor, texto=mensaje
        )
        self._sesion.add(mensaje_orm)

    def obtener_test_case(self, test_case_id: str) -> TestCase | None:
        """
        Reconstruye un `TestCase` de dominio completo (incluyendo su
        `historial_feedback`) a partir de lo persistido.

        No es un método del port `Repository` -- el contrato actual no
        define ninguna operación de lectura, solo de escritura
        (`guardar_*`, `actualizar_estado`). Se agrega como método propio
        de este adapter porque va a ser necesario en Fase 3+ al migrar el
        chat de feedback de memoria de sesión a persistencia real (ver
        checklist de Fase 3, spec sección 14: "Migrar el chat de feedback
        de `st.session_state` a `Repository.guardar_feedback()`" --
        guardar es solo mitad del trabajo, leer de vuelta para reconstruir
        la UI es la otra mitad).

        Si en el futuro se decide que esto debe vivir en el port
        `Repository` formalmente (para que cualquier adapter que lo
        implemente esté obligado a darlo), es un cambio de una sola línea
        en `ports/repository.py` -- se deja como nota para cuando se
        conecte el frontend a esto.
        """
        test_case_orm = self._sesion.get(TestCaseORM, self._a_uuid(test_case_id))
        if test_case_orm is None:
            return None

        return TestCase(
            titulo=test_case_orm.titulo,
            gherkin=test_case_orm.gherkin,
            hu_key=test_case_orm.hu_key,
            id=str(test_case_orm.id),
            estado=EstadoTestCase(test_case_orm.estado),
            xray_test_key=test_case_orm.xray_test_key,
            historial_feedback=[
                MensajeFeedback(autor=m.autor, texto=m.texto)
                for m in test_case_orm.historial_feedback
            ],
            version_contenido=test_case_orm.version_contenido,
            alucinacion_detectada=test_case_orm.alucinacion_detectada,
            alucinacion_detalle=test_case_orm.alucinacion_detalle,
            tipo_cobertura=TipoCobertura(test_case_orm.tipo_cobertura)
            if test_case_orm.tipo_cobertura
            else None,
        )
