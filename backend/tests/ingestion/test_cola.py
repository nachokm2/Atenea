"""Cola de trabajos sobre `generation_jobs` y bucle del worker (§3.3, §1.2).

La prueba exigida por el contrato interno es
`test_dos_consumidores_no_reciben_el_mismo_trabajo`: sin `FOR UPDATE SKIP LOCKED` no se
puede escalar el worker en Railway, y dos instancias procesarían dos veces el mismo PDF
(y lo cobrarían dos veces al proveedor de IA).

Esa prueba **no** puede usar la sesión transaccional del resto del archivo: necesita dos
conexiones reales y simultáneas, así que abre las suyas y limpia lo que escribe.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.enums import JobStatus, JobType
from app.models.ingestion import GenerationJob
from app.worker import cola, principal

# ---------------------------------------------------------------------------
# Encolado e idempotencia
# ---------------------------------------------------------------------------


def test_encolar_deja_el_trabajo_pendiente(db: Session) -> None:
    """Un trabajo recién encolado está `PENDING`, sin intentos y con su cola y prioridad."""
    trabajo = cola.encolar(
        db,
        job_type=JobType.DOCUMENT_INGESTION,
        queue=cola.COLA_INGESTA,
        payload={"hola": "mundo"},
        priority=50,
    )
    assert trabajo.status == JobStatus.PENDING
    assert trabajo.queue == cola.COLA_INGESTA
    assert trabajo.attempt_count == 0
    assert trabajo.max_attempts == 3
    assert trabajo.queued_at is not None
    assert trabajo.payload == {"hola": "mundo"}


def test_la_misma_clave_de_idempotencia_no_duplica(db: Session) -> None:
    """§8.3: encolar dos veces con la misma clave devuelve el trabajo existente."""
    clave = str(uuid.uuid4())
    primero = cola.encolar(db, job_type=JobType.PATH_DESIGN, idempotency_key=clave)
    segundo = cola.encolar(db, job_type=JobType.PATH_DESIGN, idempotency_key=clave)
    assert primero.id == segundo.id
    assert cola.por_clave(db, clave).id == primero.id


def test_obtener_ajeno_responde_404_no_403(db: Session, usuario: Any) -> None:
    """§8.7: un id que no es del usuario devuelve `404`, para no filtrar existencia."""
    trabajo = cola.encolar(db, job_type=JobType.PATH_DESIGN, usuario_id=usuario.id)
    with pytest.raises(cola.TrabajoNoEncontrado) as excepcion:
        cola.obtener(db, trabajo.id, usuario_id=uuid.uuid4())
    assert excepcion.value.status_code == 404
    assert excepcion.value.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Toma de trabajo
# ---------------------------------------------------------------------------


def test_tomar_respeta_prioridad_y_antiguedad(db: Session) -> None:
    """Menor `priority` primero; a igual prioridad, el más antiguo."""
    tarde = cola.encolar(db, job_type=JobType.PATH_DESIGN, queue=cola.COLA_GENERACION, priority=100)
    urgente = cola.encolar(
        db, job_type=JobType.DOCUMENT_INGESTION, queue=cola.COLA_GENERACION, priority=10
    )
    tomado = cola.tomar_siguiente(db, colas=[cola.COLA_GENERACION])
    assert tomado is not None
    assert tomado.id == urgente.id
    assert tomado.status == JobStatus.RUNNING
    assert tomado.attempt_count == 1
    assert cola.tomar_siguiente(db, colas=[cola.COLA_GENERACION]).id == tarde.id


def test_solo_se_toman_los_trabajos_de_la_cola_pedida(db: Session) -> None:
    """Un worker de `ingest` jamás toca un trabajo de `generate`."""
    cola.encolar(db, job_type=JobType.PATH_DESIGN, queue=cola.COLA_GENERACION)
    assert cola.tomar_siguiente(db, colas=[cola.COLA_INGESTA]) is None


def test_un_trabajo_cancelado_no_se_vuelve_a_tomar(db: Session) -> None:
    """La cancelación es definitiva: `CANCELLED` es estado terminal."""
    trabajo = cola.encolar(db, job_type=JobType.PATH_DESIGN, queue=cola.COLA_GENERACION)
    cola.cancelar(db, trabajo.id, motivo="Material eliminado.")
    assert trabajo.status == JobStatus.CANCELLED
    assert cola.tomar_siguiente(db, colas=[cola.COLA_GENERACION]) is None


def test_cancelar_pendientes_nunca_cancela_todo_por_accidente(db: Session) -> None:
    """Sin un filtro concreto (documento o ruta) la cancelación en bloque no hace nada."""
    cola.encolar(db, job_type=JobType.PATH_DESIGN, queue=cola.COLA_GENERACION)
    assert cola.cancelar_pendientes(db) == 0


# ---------------------------------------------------------------------------
# Reintentos con retroceso exponencial
# ---------------------------------------------------------------------------


def test_un_fallo_reintentable_vuelve_a_pendiente_pero_espera(db: Session) -> None:
    """Tras fallar, el trabajo vuelve a `PENDING` y no se ofrece hasta pasado el retroceso."""
    trabajo = cola.encolar(db, job_type=JobType.PATH_DESIGN, queue=cola.COLA_GENERACION)
    tomado = cola.tomar_siguiente(db, colas=[cola.COLA_GENERACION])
    assert tomado is not None
    cola.fallar(db, tomado, "El proveedor no respondió.", reintentable=True)
    assert tomado.status == JobStatus.PENDING
    assert tomado.attempt_count == 1

    # Inmediatamente después, el retroceso (15 · 2¹ s) lo mantiene fuera de la cola.
    assert cola.tomar_siguiente(db, colas=[cola.COLA_GENERACION]) is None

    # Pasado el retroceso, vuelve a estar disponible.
    futuro = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=cola.RETROCESO_BASE_SEGUNDOS * 4)
    recuperado = cola.tomar_siguiente(db, colas=[cola.COLA_GENERACION], momento=futuro)
    assert recuperado is not None
    assert recuperado.id == trabajo.id
    assert recuperado.attempt_count == 2


def test_un_fallo_no_reintentable_cierra_el_trabajo(db: Session) -> None:
    """Material ilegible o esquema roto: reintentar daría el mismo resultado."""
    cola.encolar(db, job_type=JobType.DOCUMENT_INGESTION, queue=cola.COLA_INGESTA)
    tomado = cola.tomar_siguiente(db, colas=[cola.COLA_INGESTA])
    cola.fallar(db, tomado, "El PDF está escaneado.", reintentable=False)
    assert tomado.status == JobStatus.FAILED
    assert cola.tomar_siguiente(db, colas=[cola.COLA_INGESTA]) is None


def test_al_agotar_los_intentos_el_trabajo_queda_fallido(db: Session) -> None:
    """`max_attempts` acota el gasto: al tercer intento se cierra como `FAILED`."""
    trabajo = cola.encolar(
        db, job_type=JobType.PATH_DESIGN, queue=cola.COLA_GENERACION, max_attempts=2
    )
    momento = dt.datetime.now(dt.UTC)
    for vuelta in range(2):
        momento = momento + dt.timedelta(seconds=cola.RETROCESO_MAXIMO_SEGUNDOS)
        tomado = cola.tomar_siguiente(db, colas=[cola.COLA_GENERACION], momento=momento)
        assert tomado is not None, f"vuelta {vuelta}"
        cola.fallar(db, tomado, "fallo", reintentable=True, momento=momento)
    assert trabajo.status == JobStatus.FAILED
    assert trabajo.attempt_count == 2


def test_reclamar_atascados_devuelve_a_pendiente(db: Session) -> None:
    """Un worker que muere deja el trabajo `RUNNING`; el mantenimiento lo recupera."""
    cola.encolar(db, job_type=JobType.PATH_DESIGN, queue=cola.COLA_GENERACION)
    tomado = cola.tomar_siguiente(db, colas=[cola.COLA_GENERACION])
    assert tomado.status == JobStatus.RUNNING
    futuro = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=cola.MINUTOS_TRABAJO_ATASCADO + 1)
    assert cola.reclamar_atascados(db, momento=futuro) == 1
    db.refresh(tomado)
    assert tomado.status == JobStatus.PENDING


# ---------------------------------------------------------------------------
# Progreso y pasos persistidos
# ---------------------------------------------------------------------------


def test_progreso_y_pasos_se_persisten(db: Session) -> None:
    """`progress_pct`/`progress_label` alimentan P06; `steps` hace reanudable el reintento."""
    trabajo = cola.encolar(db, job_type=JobType.DOCUMENT_INGESTION, queue=cola.COLA_INGESTA)
    cola.marcar_progreso(db, trabajo, pct=55, label="Organizando el contenido")
    cola.registrar_paso(db, trabajo, "chunk", {"chunks": 12})

    assert float(trabajo.progress_pct) == 55.0
    assert trabajo.progress_label == "Organizando el contenido"
    assert cola.paso_hecho(trabajo, "chunk") is True
    assert cola.paso_hecho(trabajo, "embed") is False

    cola.completar(db, trabajo, result={"chunks": 12}, label="Material listo")
    assert trabajo.status == JobStatus.SUCCEEDED
    assert float(trabajo.progress_pct) == 100.0
    assert trabajo.result == {"chunks": 12}


def test_el_progreso_se_acota_entre_0_y_100(db: Session) -> None:
    """Un porcentaje fuera de rango no puede romper `Numeric(5, 2)` ni la barra de la app."""
    trabajo = cola.encolar(db, job_type=JobType.DOCUMENT_INGESTION, queue=cola.COLA_INGESTA)
    cola.marcar_progreso(db, trabajo, pct=980)
    assert float(trabajo.progress_pct) == 100.0
    cola.marcar_progreso(db, trabajo, pct=-5)
    assert float(trabajo.progress_pct) == 0.0


# ---------------------------------------------------------------------------
# LA prueba del contrato: dos consumidores, un solo trabajo
# ---------------------------------------------------------------------------


def test_dos_consumidores_no_reciben_el_mismo_trabajo(engine: Any) -> None:
    """`FOR UPDATE SKIP LOCKED`: dos workers simultáneos nunca toman la misma fila.

    Se usan **dos conexiones reales**: el patrón solo se puede observar con dos
    transacciones abiertas a la vez, y la sesión transaccional del resto del archivo
    comparte una sola conexión.
    """
    marca = f"concurrencia-{uuid.uuid4()}"
    with Session(engine, expire_on_commit=False) as siembra:
        trabajo = cola.encolar(
            siembra,
            job_type=JobType.DOCUMENT_INGESTION,
            queue=cola.COLA_INGESTA,
            idempotency_key=marca,
            priority=1,
        )
        siembra.commit()
        job_id = trabajo.id

    try:
        with Session(engine, expire_on_commit=False) as worker_a, Session(
            engine, expire_on_commit=False
        ) as worker_b:
            # A toma el trabajo y **no** confirma todavía: la fila queda bloqueada.
            tomado_a = cola.tomar_siguiente(worker_a, colas=[cola.COLA_INGESTA])
            assert tomado_a is not None
            assert tomado_a.id == job_id

            # B mira la misma cola en ese instante: la salta en vez de bloquearse.
            tomado_b = cola.tomar_siguiente(worker_b, colas=[cola.COLA_INGESTA])
            assert tomado_b is None or tomado_b.id != job_id

            worker_a.commit()
            worker_b.rollback()

        with Session(engine, expire_on_commit=False) as comprobacion:
            fila = comprobacion.get(GenerationJob, job_id)
            assert fila.status == JobStatus.RUNNING
            assert fila.attempt_count == 1, "el trabajo se tomó exactamente una vez"
    finally:
        with Session(engine) as limpieza:
            limpieza.execute(sa.delete(GenerationJob).where(GenerationJob.id == job_id))
            limpieza.commit()


# ---------------------------------------------------------------------------
# Bucle del worker
# ---------------------------------------------------------------------------


def test_el_worker_despacha_al_ejecutor_registrado(db: Session, cfg: Any) -> None:
    """`principal.ejecutar_uno` toma el trabajo, lo ejecuta y lo cierra como `SUCCEEDED`."""
    llamadas: list[uuid.UUID] = []

    def ejecutor(_db: Session, trabajo: GenerationJob, _cfg: Any) -> dict[str, Any]:
        llamadas.append(trabajo.id)
        return {"ok": True}

    original = principal.MANEJADORES.get(JobType.NARRATIVE_GENERATION)
    principal.registrar_manejador(JobType.NARRATIVE_GENERATION, ejecutor)
    try:
        trabajo = cola.encolar(
            db, job_type=JobType.NARRATIVE_GENERATION, queue=cola.COLA_GENERACION
        )
        hecho = principal.ejecutar_uno(db, colas=[cola.COLA_GENERACION], cfg=cfg)
        assert hecho is not None
        assert hecho.id == trabajo.id
        assert llamadas == [trabajo.id]
        assert trabajo.status == JobStatus.SUCCEEDED
        assert trabajo.result == {"ok": True}
        assert principal.ejecutar_uno(db, colas=[cola.COLA_GENERACION], cfg=cfg) is None
    finally:
        if original is None:
            principal.MANEJADORES.pop(JobType.NARRATIVE_GENERATION, None)
        else:  # pragma: no cover - solo si otro agente registra ese tipo
            principal.MANEJADORES[JobType.NARRATIVE_GENERATION] = original


def test_un_tipo_sin_ejecutor_queda_para_revision(db: Session, cfg: Any) -> None:
    """Nada se pierde en silencio: sin manejador el trabajo queda `NEEDS_ATTENTION`."""
    trabajo = cola.encolar(db, job_type=JobType.TERRITORY_NAMING, queue=cola.COLA_GENERACION)
    principal.ejecutar_uno(db, colas=[cola.COLA_GENERACION], cfg=cfg)
    assert trabajo.status == JobStatus.NEEDS_ATTENTION
    assert "TERRITORY_NAMING" in trabajo.error_message or "territory" in trabajo.error_message


def test_un_error_4xx_no_se_reintenta_y_un_5xx_si(db: Session, cfg: Any) -> None:
    """§8.1: un `4xx` describe el dato de entrada; solo el `5xx` merece otro intento."""
    from app.core.errors import AteneaError

    def fallo_definitivo(_db: Session, _trabajo: GenerationJob, _cfg: Any) -> dict[str, Any]:
        raise AteneaError("No pudimos leer el documento.", code="DOCUMENT_UNREADABLE")

    def fallo_transitorio(_db: Session, _trabajo: GenerationJob, _cfg: Any) -> dict[str, Any]:
        raise AteneaError("Proveedor caído.", code="GENERATION_FAILED")

    principal.registrar_manejador(JobType.GROUNDEDNESS_CHECK, fallo_definitivo)
    principal.registrar_manejador(JobType.REMEDIAL_EXERCISES, fallo_transitorio)
    try:
        definitivo = cola.encolar(
            db, job_type=JobType.GROUNDEDNESS_CHECK, queue=cola.COLA_GENERACION, priority=1
        )
        principal.ejecutar_uno(db, colas=[cola.COLA_GENERACION], cfg=cfg)
        assert definitivo.status == JobStatus.FAILED

        transitorio = cola.encolar(
            db, job_type=JobType.REMEDIAL_EXERCISES, queue=cola.COLA_GENERACION, priority=2
        )
        principal.ejecutar_uno(db, colas=[cola.COLA_GENERACION], cfg=cfg)
        assert transitorio.status == JobStatus.PENDING
    finally:
        principal.MANEJADORES.pop(JobType.GROUNDEDNESS_CHECK, None)
        principal.MANEJADORES.pop(JobType.REMEDIAL_EXERCISES, None)
