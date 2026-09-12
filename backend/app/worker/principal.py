"""Bucle del worker: toma trabajos de `generation_jobs` y los ejecuta (§1.2, §3.3).

Se arranca así, desde `backend/`::

    python -m app.worker.principal                     # todas las colas
    python -m app.worker.principal --queues ingest     # solo ingesta
    python -m app.worker.principal --once              # un trabajo y sale (depuración)
    python -m app.worker.principal --drain             # vacía la cola y termina

**Es seguro correr varias instancias a la vez**: la toma de trabajo usa
`FOR UPDATE SKIP LOCKED` (ver :mod:`app.worker.cola`), de modo que dos procesos nunca
reciben la misma fila y uno lento no bloquea a los demás. En Railway esto se traduce en
escalar el servicio `worker` sin tocar una línea de código.

Ciclo de vida de un trabajo:

```
PENDING ──tomar_siguiente──▶ RUNNING ──éxito──▶ SUCCEEDED
                               │
                               ├─fallo reintentable─▶ PENDING (retroceso 15·2ⁿ s, máx. 10 min)
                               ├─intentos agotados──▶ FAILED
                               ├─fallo definitivo───▶ FAILED        (material ilegible, 4xx)
                               └─sin manejador──────▶ NEEDS_ATTENTION
```

Qué sabe hacer cada cola:

| Cola | Trabajos | Ejecutor |
|---|---|---|
| `ingest` | `DOCUMENT_INGESTION`, `EMBEDDING_BATCH` | `app.modules.ingestion.servicio` |
| `generate` | `PATH_DESIGN`, `MODULE_GENERATION`, … | `app.modules.ai` |
| `housekeeping` | *(mantenimiento periódico)* | purga de documentos vencidos |

El worker **no** decide recompensas ni escribe XP u oro: la ingesta emite sus eventos de
dominio (`DOCUMENT_INGESTED`, `DOCUMENT_FAILED`) y es el motor de `gamification` quien,
si procede, reacciona. Los segundos de sondeo y de mantenimiento son parámetros de
infraestructura (no existen en §5) y por eso viven aquí como constantes.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import AteneaError
from app.core.logging import configure_logging, get_logger
from app.core.time import utcnow
from app.models.enums import JobStatus, JobType
from app.models.ingestion import DocumentVersion, GenerationJob
from app.worker import cola

logger = get_logger("atenea.worker")

#: Segundos de espera cuando no hay trabajo en la cola (sondeo barato sobre un índice).
SEGUNDOS_SONDEO = 2.0

#: Cada cuántos segundos se reclaman los trabajos huérfanos y se purga lo vencido.
SEGUNDOS_MANTENIMIENTO = 60.0

#: Identidad del proceso en los registros: permite seguir a un worker concreto.
NOMBRE_WORKER = os.environ.get("WORKER_NAME") or f"worker-{uuid.uuid4().hex[:8]}"

#: Firma de un ejecutor de trabajo: recibe la sesión, el trabajo y la configuración de
#: juego, y devuelve el resumen que se guarda en `generation_jobs.result`.
Manejador = Callable[[Session, GenerationJob, Any], dict[str, Any]]


class TrabajoNoSoportado(AteneaError):
    """No hay ejecutor registrado para ese `job_type`: el trabajo queda para revisión."""

    code = "GENERATION_FAILED"
    status_code = 502


class MaterialRechazado(AteneaError):
    """422 · El material no sirve; reintentarlo daría exactamente el mismo resultado."""

    code = "DOCUMENT_UNREADABLE"
    status_code = 422


# ---------------------------------------------------------------------------
# Ejecutores de la cola `ingest` (módulo `ingestion`)
# ---------------------------------------------------------------------------


def _version_del_trabajo(db: Session, trabajo: GenerationJob) -> DocumentVersion:
    """Localiza la `document_versions` que el trabajo debe procesar."""
    identificador = trabajo.document_version_id
    if identificador is None:
        crudo = (trabajo.payload or {}).get("document_version_id")
        if crudo:
            try:
                identificador = uuid.UUID(str(crudo))
            except ValueError:  # pragma: no cover - payload manipulado
                identificador = None
    if identificador is None:
        raise TrabajoNoSoportado(
            "El trabajo de ingesta no indica qué material procesar.",
            details={"job_id": str(trabajo.id)},
        )
    version = db.get(DocumentVersion, identificador)
    if version is None:
        raise TrabajoNoSoportado(
            "El material de ese trabajo ya no existe.",
            details={"document_version_id": str(identificador)},
        )
    return version


def ejecutar_ingesta(db: Session, trabajo: GenerationJob, cfg: Any) -> dict[str, Any]:
    """`DOCUMENT_INGESTION`: extraer, trocear y embeber una versión de documento.

    Un material rechazado (PDF escaneado, formato no admitido, texto insuficiente) **no
    es un fallo del sistema**: la versión queda `REJECTED`, se emite `DOCUMENT_FAILED` y
    aquí se levanta un error no reintentable para que el trabajo cierre con el mensaje
    que la app mostrará tal cual.
    """
    from app.modules.ingestion import servicio  # noqa: PLC0415 - carga perezosa del módulo

    version = _version_del_trabajo(db, trabajo)
    resultado = servicio.procesar_version(db, version, cfg=cfg, trabajo=trabajo)
    if resultado.rechazado:
        raise MaterialRechazado(
            version.error_message or "No pudimos leer el material.",
            details={
                "reason": resultado.motivo,
                "document_version_id": str(version.id),
            },
        )
    return {
        "document_version_id": str(version.id),
        "chunk_count": resultado.chunk_count,
        "token_count": resultado.token_count,
        "word_count": resultado.word_count,
        "language": resultado.language,
        "embedded": resultado.embebidos,
    }


def ejecutar_reindexado(db: Session, trabajo: GenerationJob, cfg: Any) -> dict[str, Any]:
    """`EMBEDDING_BATCH`: recalcula los embeddings de una versión ya troceada."""
    from app.modules.ingestion import servicio  # noqa: PLC0415

    version = _version_del_trabajo(db, trabajo)
    actualizados = servicio.reindexar_version(db, version, cfg=cfg, trabajo=trabajo)
    return {"document_version_id": str(version.id), "reindexed": actualizados}


# ---------------------------------------------------------------------------
# Ejecutores de la cola `generate` (módulo `ai`)
# ---------------------------------------------------------------------------


def _proveedor_ia(cfg: Any) -> Any:
    """Crea el proveedor de IA vigente (`mock` en desarrollo, Claude en producción)."""
    from app.modules.ai.proveedor import crear_proveedor  # noqa: PLC0415

    return crear_proveedor(cfg=cfg)


def ejecutar_diseno_de_ruta(db: Session, trabajo: GenerationJob, cfg: Any) -> dict[str, Any]:
    """`PATH_DESIGN`: Fase A del diseño de ruta, delegada íntegra al módulo `ai`."""
    from app.modules.ai import arquitecto_ruta  # noqa: PLC0415

    path_id = trabajo.learning_path_id or _id_del_payload(trabajo, "learning_path_id")
    if path_id is None:
        raise TrabajoNoSoportado(
            "El trabajo de diseño no indica qué ruta construir.",
            details={"job_id": str(trabajo.id)},
        )
    cola.marcar_progreso(db, trabajo, pct=10, label="Diseñando módulos")
    resultado = arquitecto_ruta.disenar_ruta(
        db,
        cfg,
        _proveedor_ia(cfg),
        learning_path_id=path_id,
        usuario_id=trabajo.user_id,
        forzar=bool((trabajo.payload or {}).get("force")),
    )
    return _resumen_de_resultado(resultado, {"learning_path_id": str(path_id)})


def ejecutar_generacion_de_modulo(
    db: Session, trabajo: GenerationJob, cfg: Any
) -> dict[str, Any]:
    """`MODULE_GENERATION`: lecciones, bloques y preguntas de un módulo (módulo `ai`)."""
    from app.modules.ai import autor_leccion  # noqa: PLC0415

    module_id = trabajo.target_id or _id_del_payload(trabajo, "module_id")
    if module_id is None:
        raise TrabajoNoSoportado(
            "El trabajo de generación no indica qué módulo construir.",
            details={"job_id": str(trabajo.id)},
        )
    cola.marcar_progreso(db, trabajo, pct=10, label="Escribiendo las lecciones")
    resultado = autor_leccion.generar_modulo(
        db,
        cfg,
        _proveedor_ia(cfg),
        module_id=module_id,
        usuario_id=trabajo.user_id,
        forzar=bool((trabajo.payload or {}).get("force")),
    )
    return _resumen_de_resultado(resultado, {"module_id": str(module_id)})


def _id_del_payload(trabajo: GenerationJob, clave: str) -> uuid.UUID | None:
    """Lee un identificador del `payload` del trabajo, tolerando basura."""
    crudo = (trabajo.payload or {}).get(clave)
    if not crudo:
        return None
    try:
        return uuid.UUID(str(crudo))
    except ValueError:  # pragma: no cover - payload manipulado
        return None


def _resumen_de_resultado(resultado: Any, base: dict[str, Any]) -> dict[str, Any]:
    """Convierte la dataclase que devuelve el módulo `ai` en JSON para `result`."""
    resumen = dict(base)
    for campo in ("modules", "topics", "lessons", "questions", "blocks", "desde_cache"):
        valor = getattr(resultado, campo, None)
        if isinstance(valor, (int, bool)):
            resumen[campo] = valor
        elif isinstance(valor, list):
            resumen[campo] = len(valor)
    return resumen


# ---------------------------------------------------------------------------
# Registro de ejecutores
# ---------------------------------------------------------------------------

#: Ejecutor por tipo de trabajo. Los tipos que aún no tienen dueño quedan fuera y su
#: trabajo termina en `NEEDS_ATTENTION`: se ve en el panel y no se pierde.
MANEJADORES: dict[JobType, Manejador] = {
    JobType.DOCUMENT_INGESTION: ejecutar_ingesta,
    JobType.EMBEDDING_BATCH: ejecutar_reindexado,
    JobType.PATH_DESIGN: ejecutar_diseno_de_ruta,
    JobType.MODULE_GENERATION: ejecutar_generacion_de_modulo,
}


def registrar_manejador(job_type: JobType, manejador: Manejador) -> None:
    """Registra (o sustituye) el ejecutor de un tipo de trabajo.

    Lo usan el módulo `ai` para añadir sus tipos y las pruebas para inyectar un doble.
    """
    MANEJADORES[job_type] = manejador


# ---------------------------------------------------------------------------
# Ejecución de un trabajo
# ---------------------------------------------------------------------------


def _es_reintentable(error: BaseException) -> bool:
    """Decide si merece la pena volver a intentarlo.

    Un `4xx` del catálogo de §8.1 describe un problema del dato de entrada: el material
    seguirá siendo ilegible dentro de quince segundos. Un `5xx` (red, proveedor caído,
    tiempo agotado) sí se reintenta, con retroceso exponencial. `429` es la excepción
    obvia: el límite se levanta solo.
    """
    if isinstance(error, AteneaError):
        return error.status_code >= 500 or error.status_code == 429
    return True


def procesar_trabajo(db: Session, trabajo: GenerationJob, *, cfg: Any | None = None) -> JobStatus:
    """Ejecuta un trabajo ya tomado y lo cierra; devuelve su estado final.

    La sesión se deja **sin commit**: quien llama decide la transacción (el bucle hace
    `commit` por trabajo; las pruebas trabajan dentro de una transacción que se revierte).
    """
    if cfg is None:
        from app.modules.gamification.servicio_config import (  # noqa: PLC0415
            obtener_servicio_config,
        )

        cfg = obtener_servicio_config(db)

    manejador = MANEJADORES.get(trabajo.job_type)
    if manejador is None:
        cola.necesita_atencion(
            db, trabajo, f"No hay ejecutor para trabajos de tipo «{trabajo.job_type}»."
        )
        return trabajo.status

    inicio = time.monotonic()
    try:
        resultado = manejador(db, trabajo, cfg)
    except Exception as error:  # noqa: BLE001 - cualquier fallo cierra el trabajo, no el worker
        mensaje = (
            error.message if isinstance(error, AteneaError) else "Fallo inesperado del worker."
        )
        detalles = dict(error.details) if isinstance(error, AteneaError) else {}
        if not isinstance(error, AteneaError):
            logger.exception("trabajo_error_inesperado", job_id=str(trabajo.id))
        cola.fallar(
            db,
            trabajo,
            mensaje,
            reintentable=_es_reintentable(error),
            detalles=detalles or None,
        )
        return trabajo.status

    cola.completar(db, trabajo, result=resultado)
    logger.info(
        "trabajo_ejecutado",
        worker=NOMBRE_WORKER,
        job_id=str(trabajo.id),
        job_type=str(trabajo.job_type),
        segundos=round(time.monotonic() - inicio, 3),
    )
    return trabajo.status


def ejecutar_uno(
    db: Session,
    *,
    colas: list[str] | tuple[str, ...] | None = None,
    cfg: Any | None = None,
) -> GenerationJob | None:
    """Toma un trabajo y lo ejecuta. Devuelve el trabajo, o `None` si la cola está vacía.

    Es la unidad que usan las pruebas para drenar la cola sin levantar el proceso.
    """
    trabajo = cola.tomar_siguiente(db, colas=colas)
    if trabajo is None:
        return None
    procesar_trabajo(db, trabajo, cfg=cfg)
    return trabajo


def drenar(
    db: Session,
    *,
    colas: list[str] | tuple[str, ...] | None = None,
    cfg: Any | None = None,
    tope: int = 100,
) -> int:
    """Ejecuta todos los trabajos disponibles hasta agotar la cola; devuelve cuántos."""
    hechos = 0
    while hechos < tope:
        if ejecutar_uno(db, colas=colas, cfg=cfg) is None:
            break
        hechos += 1
    return hechos


# ---------------------------------------------------------------------------
# Mantenimiento periódico
# ---------------------------------------------------------------------------


def mantenimiento(db: Session) -> dict[str, int]:
    """Reclama trabajos huérfanos y purga el material cuyo plazo de retención venció."""
    from app.modules.ingestion import servicio  # noqa: PLC0415

    reclamados = cola.reclamar_atascados(db)
    purgados = servicio.purgar_documentos(db)
    if reclamados or purgados:
        logger.info(
            "mantenimiento", worker=NOMBRE_WORKER, reclamados=reclamados, purgados=purgados
        )
    return {"reclamados": reclamados, "purgados": purgados}


# ---------------------------------------------------------------------------
# Bucle principal
# ---------------------------------------------------------------------------


def bucle(
    *,
    colas: list[str] | None = None,
    segundos_sondeo: float = SEGUNDOS_SONDEO,
    segundos_mantenimiento: float = SEGUNDOS_MANTENIMIENTO,
    max_trabajos: int | None = None,
    salir_si_vacio: bool = False,
    parar: threading.Event | None = None,
) -> int:
    """Bucle de consumo: toma, ejecuta y cierra trabajos hasta que se pide parar.

    Cada trabajo vive en **su propia transacción**: un fallo no arrastra al siguiente, y
    el estado `RUNNING` se confirma de inmediato para que `GET /jobs/{id}` lo vea. Si el
    proceso muere a mitad, `reclamar_atascados` devuelve el trabajo a `PENDING`.
    """
    detener = parar or threading.Event()
    colas_efectivas = list(colas) if colas else list(cola.COLAS)
    procesados = 0
    proximo_mantenimiento = 0.0

    logger.info(
        "worker_arrancado",
        worker=NOMBRE_WORKER,
        colas=colas_efectivas,
        entorno=settings.environment,
    )

    while not detener.is_set():
        ahora = time.monotonic()
        if ahora >= proximo_mantenimiento:
            proximo_mantenimiento = ahora + segundos_mantenimiento
            try:
                with SessionLocal() as sesion:
                    mantenimiento(sesion)
                    sesion.commit()
            except Exception:  # noqa: BLE001 - el mantenimiento nunca tumba el worker
                logger.exception("mantenimiento_fallido", worker=NOMBRE_WORKER)

        trabajo: GenerationJob | None = None
        try:
            with SessionLocal() as sesion:
                trabajo = cola.tomar_siguiente(sesion, colas=colas_efectivas)
                if trabajo is None:
                    sesion.commit()
                else:
                    # Se confirma la toma antes de trabajar: la app ve `RUNNING` ya.
                    sesion.commit()
                    sesion.refresh(trabajo)
                    procesar_trabajo(sesion, trabajo)
                    sesion.commit()
                    procesados += 1
        except Exception:  # noqa: BLE001 - un fallo de transporte no mata el proceso
            logger.exception("ciclo_fallido", worker=NOMBRE_WORKER)
            detener.wait(segundos_sondeo)
            continue

        if trabajo is None:
            if salir_si_vacio:
                break
            detener.wait(segundos_sondeo)
        if max_trabajos is not None and procesados >= max_trabajos:
            break

    logger.info("worker_detenido", worker=NOMBRE_WORKER, procesados=procesados)
    return procesados


def _instalar_senales(detener: threading.Event) -> None:
    """Apagado ordenado: `SIGINT`/`SIGTERM` terminan el trabajo en curso y salen."""

    def _manejar(numero: int, _marco: Any) -> None:
        logger.info("worker_señal", worker=NOMBRE_WORKER, señal=numero)
        detener.set()

    for nombre in ("SIGTERM", "SIGINT"):
        senal = getattr(signal, nombre, None)
        if senal is None:  # pragma: no cover - depende del sistema operativo
            continue
        try:
            signal.signal(senal, _manejar)
        except (ValueError, OSError):  # pragma: no cover - hilo secundario o Windows
            logger.debug("señal_no_instalable", señal=nombre)


def construir_parser() -> argparse.ArgumentParser:
    """Argumentos de línea de órdenes del worker."""
    parser = argparse.ArgumentParser(
        prog="python -m app.worker.principal",
        description="Worker de Atenea: consume la cola `generation_jobs`.",
    )
    parser.add_argument(
        "--queues",
        nargs="+",
        choices=list(cola.COLAS),
        default=None,
        help="Colas que atiende este proceso (por defecto, todas).",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=SEGUNDOS_SONDEO,
        help="Espera entre sondeos cuando no hay trabajo.",
    )
    parser.add_argument(
        "--maintenance-seconds",
        type=float,
        default=SEGUNDOS_MANTENIMIENTO,
        help="Periodo del mantenimiento (huérfanos y purga).",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Sale tras ejecutar este número de trabajos (pruebas y depuración).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Atiende un solo trabajo y termina (y sale enseguida si la cola está vacía).",
    )
    parser.add_argument(
        "--drain",
        action="store_true",
        help="Vacía la cola y termina, en vez de quedarse esperando trabajo nuevo.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de `python -m app.worker.principal`."""
    argumentos = construir_parser().parse_args(argv)
    configure_logging()

    detener = threading.Event()
    _instalar_senales(detener)

    inicio = utcnow()
    procesados = bucle(
        colas=argumentos.queues,
        segundos_sondeo=argumentos.poll_seconds,
        segundos_mantenimiento=argumentos.maintenance_seconds,
        max_trabajos=1 if argumentos.once else argumentos.max_jobs,
        salir_si_vacio=argumentos.once or argumentos.drain,
        parar=detener,
    )
    logger.info(
        "worker_resumen",
        worker=NOMBRE_WORKER,
        procesados=procesados,
        segundos=(utcnow() - inicio).total_seconds(),
    )
    return 0


__all__ = [
    "MANEJADORES",
    "NOMBRE_WORKER",
    "SEGUNDOS_MANTENIMIENTO",
    "SEGUNDOS_SONDEO",
    "Manejador",
    "MaterialRechazado",
    "TrabajoNoSoportado",
    "bucle",
    "construir_parser",
    "drenar",
    "ejecutar_diseno_de_ruta",
    "ejecutar_generacion_de_modulo",
    "ejecutar_ingesta",
    "ejecutar_reindexado",
    "ejecutar_uno",
    "main",
    "mantenimiento",
    "procesar_trabajo",
    "registrar_manejador",
]


if __name__ == "__main__":  # pragma: no cover - punto de entrada del proceso
    sys.exit(main())
