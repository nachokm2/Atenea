"""Rutas HTTP del módulo `ingestion` (contrato §7.5).

| Método | Ruta | Notas |
|---|---|---|
| POST | `/documents` | multipart, **Idempotency-Key** |
| POST | `/documents/paste` | **Idempotency-Key** |
| GET | `/documents` | `Page<DocumentOut>` |
| GET | `/documents/{document_id}` | |
| DELETE | `/documents/{document_id}` | `204`, borrado lógico + purga diferida |
| GET | `/jobs/{job_id}` | polling cada 2–3 s |
| GET | `/chunks/{chunk_id}` | hoja «Fuente» |
| GET | `/paths/{path_id}/generation` | pantalla P06 |
| GET | `/paths/{path_id}/sources` | `Page<DocumentOut>` |

El router se expone como `router = APIRouter()` **sin prefijo**: el `/api/v1` y el
montaje los pone el agente de integración en `app/api/v1/__init__.py`.

Tres reglas que este archivo respeta sin excepción:

* **Aislamiento (§8.7)**: toda consulta pasa por el servicio, que filtra por `user_id`;
  lo ajeno responde `404`, nunca `403`, para no filtrar existencia.
* **Idempotencia (§8.3)**: las dos rutas de alta exigen `Idempotency-Key`; un reintento
  con la misma clave devuelve el mismo cuerpo con `200` en vez de `201`.
* **Ningún número de juego aquí**: los topes de subida los aplica `servicio` leyendo
  `ingestion.*` de `game_configs` a través de `ServicioConfig`.

TODO(A1/A8): aplicar el límite general de 60 req/min de §8.7 cuando `slowapi` esté
montado en `app/main.py`; la subida de material se beneficia además del tope diario
`ai.quotas_per_day.upload_mb`, que vive en el módulo `ai`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, IdempotencyDep
from app.core.limites import freno
from app.models.enums import DocumentStatus
from app.models.ingestion import Document, DocumentVersion, GenerationJob
from app.modules.gamification.servicio_config import obtener_servicio_config
from app.modules.ingestion import extraccion, servicio
from app.modules.ingestion.schemas import (
    ChunkOut,
    DocumentCreatedOut,
    DocumentOut,
    DocumentVersionOut,
    GenerationStatusOut,
    JobOut,
    PageDocumentsOut,
    PageOut,
    PasteTextIn,
)
from app.worker import cola

router = APIRouter()

#: Margen de lectura sobre el tope: permite detectar el exceso sin cargar todo en memoria.
_MARGEN_LECTURA = 1024


# ---------------------------------------------------------------------------
# Conversión de dominio a esquema
# ---------------------------------------------------------------------------


def _job(trabajo: GenerationJob | None) -> JobOut | None:
    """Adapta un `generation_jobs` al `JobOut` del contrato."""
    if trabajo is None:
        return None
    return JobOut(
        id=trabajo.id,
        job_type=trabajo.job_type,
        status=trabajo.status,
        queue=trabajo.queue,
        progress_pct=float(trabajo.progress_pct or 0),
        progress_label=trabajo.progress_label,
        error=trabajo.error_message,
        attempt_count=trabajo.attempt_count,
        max_attempts=trabajo.max_attempts,
        learning_path_id=trabajo.learning_path_id,
        document_version_id=trabajo.document_version_id,
        created_at=trabajo.created_at,
        started_at=trabajo.started_at,
        finished_at=trabajo.finished_at,
    )


def _documento(documento: Document, version: DocumentVersion | None) -> DocumentOut:
    """Adapta un documento y su versión vigente al `DocumentOut` del contrato."""
    return DocumentOut(
        id=documento.id,
        knowledge_base_id=documento.knowledge_base_id,
        title=documento.title,
        document_type=documento.document_type,
        original_filename=documento.original_filename,
        status=documento.status,
        version_count=documento.version_count,
        created_at=documento.created_at,
        updated_at=documento.updated_at,
        current_version=(
            DocumentVersionOut.model_validate(version) if version is not None else None
        ),
    )


def _pagina(db: Session, pagina: servicio.PaginaDocumentos) -> PageDocumentsOut:
    """Adapta una página de documentos cargando sus versiones vigentes en una consulta."""
    versiones = servicio.versiones_vigentes(db, [fila.id for fila in pagina.items])
    return PageDocumentsOut(
        items=[_documento(fila, versiones.get(fila.id)) for fila in pagina.items],
        page=PageOut(
            limit=pagina.limit,
            next_cursor=pagina.next_cursor,
            has_more=pagina.has_more,
            total=pagina.total,
        ),
    )


async def _leer_subida(archivo: UploadFile, *, max_bytes: int) -> bytes:
    """Lee el fichero subido con un tope duro, sin confiar en `Content-Length`.

    Se leen como mucho `max_bytes + margen`: si el cliente miente sobre el tamaño, el
    servidor no se queda sin memoria y responde `413 FILE_TOO_LARGE` igual que si lo
    hubiese declarado bien.
    """
    trozos: list[bytes] = []
    leidos = 0
    tope = max_bytes + _MARGEN_LECTURA
    while True:
        trozo = await archivo.read(1024 * 1024)
        if not trozo:
            break
        leidos += len(trozo)
        trozos.append(trozo)
        if leidos > tope:
            raise extraccion.ArchivoDemasiadoGrande(
                "El archivo es demasiado grande. El máximo es "
                f"{max_bytes // (1024 * 1024)} MB.",
                details={"max_bytes": max_bytes},
            )
    return b"".join(trozos)


# ---------------------------------------------------------------------------
# Alta de material
# ---------------------------------------------------------------------------


@router.post(
    "/documents",
    response_model=DocumentCreatedOut,
    status_code=status.HTTP_201_CREATED,
    tags=["material"],
    summary="Sube un archivo y encola su ingesta",
    # Como dependencia y no como decorador: esta ruta usa `UploadFile` y `Form`,
    # y el envoltorio del decorador impide que FastAPI resuelva esos tipos.
    dependencies=[Depends(freno(settings.rate_limit_upload))],
)
async def subir_documento(
    user: CurrentUser,
    db: DbSession,
    idem: IdempotencyDep,
    respuesta: Response,
    file: UploadFile = File(..., description="PDF, DOCX, Markdown o TXT."),
    title: str | None = Form(default=None, description="Título visible; por defecto el del archivo."),
    knowledge_base_id: uuid.UUID | None = Form(default=None, description="Biblioteca destino."),
) -> DocumentCreatedOut:
    """`POST /documents`: valida por contenido, guarda con nombre opaco y encola.

    El tipo real se decide por **magic bytes**, no por la extensión (§8.7): un `.pdf`
    que en realidad es otra cosa se rechaza con `415 UNSUPPORTED_FILE_TYPE`, y un PDF
    escaneado sin capa de texto con `422 DOCUMENT_UNREADABLE`.
    """
    clave = idem.require()
    cfg = obtener_servicio_config(db)
    topes = servicio.limites(cfg)

    contenido = await _leer_subida(file, max_bytes=topes.max_file_bytes)
    resultado = servicio.subir_archivo(
        db,
        usuario_id=user.id,
        contenido=contenido,
        nombre_archivo=file.filename,
        idempotency_key=clave,
        knowledge_base_id=knowledge_base_id,
        titulo=title,
        cfg=cfg,
        zona=getattr(user, "timezone", None),
    )
    db.commit()

    if not resultado.nuevo:
        respuesta.status_code = status.HTTP_200_OK
    return DocumentCreatedOut(
        document=_documento(resultado.document, resultado.version),
        job=_job(resultado.job),
        duplicate=resultado.duplicado,
        retry=resultado.reintento,
    )


@router.post(
    "/documents/paste",
    response_model=DocumentCreatedOut,
    status_code=status.HTTP_201_CREATED,
    tags=["material"],
    summary="Pega texto como material",
)
def pegar_documento(
    user: CurrentUser,
    db: DbSession,
    idem: IdempotencyDep,
    respuesta: Response,
    cuerpo: PasteTextIn,
) -> DocumentCreatedOut:
    """`POST /documents/paste`: el texto pegado se trata como cualquier otro material."""
    clave = idem.require()
    cfg = obtener_servicio_config(db)

    resultado = servicio.pegar_texto(
        db,
        usuario_id=user.id,
        titulo=cuerpo.title,
        texto=cuerpo.text,
        idempotency_key=clave,
        knowledge_base_id=cuerpo.knowledge_base_id,
        cfg=cfg,
        zona=getattr(user, "timezone", None),
    )
    db.commit()

    if not resultado.nuevo:
        respuesta.status_code = status.HTTP_200_OK
    return DocumentCreatedOut(
        document=_documento(resultado.document, resultado.version),
        job=_job(resultado.job),
        duplicate=resultado.duplicado,
        retry=resultado.reintento,
    )


# ---------------------------------------------------------------------------
# Consulta y borrado de material
# ---------------------------------------------------------------------------


@router.get(
    "/documents",
    response_model=PageDocumentsOut,
    tags=["material"],
    summary="Mis documentos",
)
def listar_documentos(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=servicio.LIMITE_POR_DEFECTO, ge=1, le=servicio.LIMITE_MAXIMO),
    cursor: str | None = Query(default=None, description="Cursor opaco de §8.2."),
    knowledge_base_id: uuid.UUID | None = Query(default=None, description="Filtra por biblioteca."),
    document_status: DocumentStatus | None = Query(
        default=None, alias="status", description="Filtra por estado de procesamiento."
    ),
) -> PageDocumentsOut:
    """`GET /documents`: lista paginada por cursor, más reciente primero (P21 → Datos)."""
    pagina = servicio.listar_documentos(
        db,
        user.id,
        knowledge_base_id=knowledge_base_id,
        estado=document_status,
        limit=limit,
        cursor=cursor,
    )
    return _pagina(db, pagina)


@router.get(
    "/documents/{document_id}",
    response_model=DocumentOut,
    tags=["material"],
    summary="Detalle y estado de procesamiento",
)
def obtener_documento(user: CurrentUser, db: DbSession, document_id: uuid.UUID) -> DocumentOut:
    """`GET /documents/{id}`: ficha del material con su versión vigente."""
    documento = servicio.obtener_documento(db, user.id, document_id)
    return _documento(documento, servicio.version_vigente(db, documento.id))


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["material"],
    summary="Borra el material (lógico + purga diferida)",
)
def borrar_documento(user: CurrentUser, db: DbSession, document_id: uuid.UUID) -> Response:
    """`DELETE /documents/{id}`: desaparece de inmediato; el binario se purga a los 30 días."""
    cfg = obtener_servicio_config(db)
    servicio.borrar_documento(db, user.id, document_id, cfg=cfg)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Trabajos y fragmentos
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}",
    response_model=JobOut,
    tags=["material"],
    summary="Estado de un trabajo",
)
def obtener_trabajo(user: CurrentUser, db: DbSession, job_id: uuid.UUID) -> JobOut:
    """`GET /jobs/{id}`: lo que la app consulta cada 2–3 s mientras espera."""
    trabajo = cola.obtener(db, job_id, usuario_id=user.id)
    salida = _job(trabajo)
    assert salida is not None  # `cola.obtener` ya lanzó 404 si no existía
    return salida


@router.get(
    "/chunks/{chunk_id}",
    response_model=ChunkOut,
    tags=["material"],
    summary="Fragmento original (hoja «Fuente»)",
)
def obtener_fragmento(user: CurrentUser, db: DbSession, chunk_id: uuid.UUID) -> ChunkOut:
    """`GET /chunks/{id}`: documento, páginas y texto que respaldan lo generado."""
    fragmento = servicio.obtener_fragmento(db, user.id, chunk_id)
    documento = db.get(Document, fragmento.document_id)
    return ChunkOut(
        id=fragmento.id,
        document_id=fragmento.document_id,
        document_version_id=fragmento.document_version_id,
        document_title=documento.title if documento is not None else None,
        chunk_index=fragmento.chunk_index,
        chunk_type=fragmento.chunk_type,
        heading_path=[str(titulo) for titulo in (fragmento.heading_path or [])],
        text=fragmento.text,
        token_count=fragmento.token_count,
        page_start=fragmento.page_start,
        page_end=fragmento.page_end,
        language=fragmento.language,
        created_at=fragmento.created_at,
    )


# ---------------------------------------------------------------------------
# Generación y fuentes de una ruta
# ---------------------------------------------------------------------------


@router.get(
    "/paths/{path_id}/generation",
    response_model=GenerationStatusOut,
    tags=["material"],
    summary="Estado agregado de la generación de una ruta",
)
def estado_generacion(user: CurrentUser, db: DbSession, path_id: uuid.UUID) -> GenerationStatusOut:
    """`GET /paths/{id}/generation`: etapas, porcentaje y si el módulo 1 ya está listo (P06)."""
    cfg = obtener_servicio_config(db)
    estado = servicio.estado_generacion(db, user.id, path_id, cfg=cfg)
    return GenerationStatusOut(
        status=estado.status,
        stage=estado.stage,
        progress_pct=estado.progress_pct,
        first_module_ready=estado.first_module_ready,
        eta_seconds=estado.eta_seconds,
        jobs=[trabajo for trabajo in (_job(fila) for fila in estado.jobs) if trabajo is not None],
    )


@router.get(
    "/paths/{path_id}/sources",
    response_model=PageDocumentsOut,
    tags=["material"],
    summary="Documentos que respaldan la ruta",
)
def fuentes_de_ruta(
    user: CurrentUser,
    db: DbSession,
    path_id: uuid.UUID,
    limit: int = Query(default=servicio.LIMITE_POR_DEFECTO, ge=1, le=servicio.LIMITE_MAXIMO),
    cursor: str | None = Query(default=None, description="Cursor opaco de §8.2."),
) -> PageDocumentsOut:
    """`GET /paths/{id}/sources`: una ruta sin material devuelve una página vacía."""
    pagina = servicio.documentos_de_ruta(db, user.id, path_id, limit=limit, cursor=cursor)
    return _pagina(db, pagina)


__all__ = ["router"]
