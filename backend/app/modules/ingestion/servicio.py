"""Casos de uso del módulo `ingestion`: subir, pegar, procesar, listar y borrar material.

Este archivo es el que orquesta todo lo demás:

```
subir_archivo / pegar_texto  →  valida, deduplica, guarda, versiona y ENCOLA
                                        │
                                        ▼  (worker, app/worker/principal.py)
                              procesar_version  →  extraer → trocear → embeber → READY
                                        │
                                        └→ evento DOCUMENT_INGESTED (dispara el diseño de ruta)
```

Decisiones que conviene no perder de vista:

* **Deduplicación por hash**: si el usuario vuelve a subir exactamente el mismo binario
  (`content_hash` SHA-256), no se guarda otra copia ni se encola nada; se devuelve el
  documento que ya tenía. Es lo que impide pagar dos veces la ingesta del mismo PDF.
* **Versionado**: el mismo material con contenido distinto crea una `document_versions`
  nueva (`version_number + 1`) y jubila la anterior (`is_current = false`,
  `status = SUPERSEDED`). El documento —lo que ve la persona— sigue siendo uno.
* **Idempotencia (§8.3)**: `POST /documents` y `POST /documents/paste` exigen
  `Idempotency-Key`. `documents` no tiene columna para ella, así que la clave se persiste
  en `generation_jobs.idempotency_key` (única global) y un reintento con la misma clave
  devuelve el mismo documento y el mismo trabajo, con `200` en vez de `201`.
* **Aislamiento (§8.7)**: absolutamente toda consulta filtra por `user_id`, y lo que no
  es del usuario responde `404`, nunca `403`.
* **Ningún número de juego en el código**: los topes salen de `ingestion.*` en
  `game_configs` a través de `ServicioConfig`, con respaldo en `settings` solo cuando la
  configuración aún no está sembrada.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFound, ValidationFailed
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.enums import (
    ChunkType,
    DocumentStatus,
    DocumentType,
    EventType,
    JobStatus,
    JobType,
)
from app.models.ingestion import (
    Document,
    DocumentChunk,
    DocumentVersion,
    GenerationJob,
    KnowledgeBase,
)
from app.modules.ingestion import almacenamiento, embeddings, extraccion, fragmentacion
from app.worker import cola

logger = get_logger("atenea.ingestion.servicio")

#: Nombre de la biblioteca que se crea sola la primera vez que alguien sube material.
NOMBRE_BIBLIOTECA_POR_DEFECTO = "Mi material"

#: Tamaño de página por defecto y máximo (§8.2).
LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 100

#: Etapas visibles de la ingesta, en el orden en que las ve la app.
ETAPAS: tuple[tuple[str, int, str], ...] = (
    ("extract", 20, "Leyendo tu material"),
    ("chunk", 55, "Organizando el contenido"),
    ("embed", 85, "Indexando para la búsqueda"),
    ("finish", 100, "Material listo"),
)

#: Estados de `document_versions` que significan «todavía se está trabajando».
ESTADOS_EN_CURSO: frozenset[DocumentStatus] = frozenset(
    {
        DocumentStatus.UPLOADED,
        DocumentStatus.QUEUED,
        DocumentStatus.EXTRACTING,
        DocumentStatus.CHUNKING,
        DocumentStatus.EMBEDDING,
    }
)


# ---------------------------------------------------------------------------
# Lectura de configuración (§5.8) con respaldo en `settings`
# ---------------------------------------------------------------------------


def _entero(cfg: Any | None, clave: str, respaldo: int) -> int:
    """Lee un entero de `game_configs`; cae al respaldo de infraestructura si falta."""
    if cfg is None:
        return respaldo
    try:
        return int(cfg.obtener_int(clave, respaldo))
    except Exception:
        return respaldo


def _mapa(cfg: Any | None, clave: str, respaldo: dict[str, Any]) -> dict[str, Any]:
    """Lee un mapa de `game_configs` con respaldo documentado."""
    if cfg is None:
        return dict(respaldo)
    try:
        valor = cfg.obtener_json(clave, respaldo)
    except Exception:
        return dict(respaldo)
    return dict(valor or respaldo)


@dataclass(slots=True)
class LimitesIngesta:
    """Topes vigentes de `ingestion.*` (§5.8)."""

    max_file_bytes: int
    max_pdf_pages: int
    max_files_per_path: int
    max_corpus_tokens: int
    min_words_for_path: int
    scanned_pdf_min_chars_per_page: int
    purge_after_days: int
    chunk: dict[str, Any]


def limites(cfg: Any | None = None) -> LimitesIngesta:
    """Resuelve los límites de ingesta vigentes."""
    return LimitesIngesta(
        max_file_bytes=_entero(cfg, "ingestion.max_file_mb", settings.max_file_mb) * 1024 * 1024,
        max_pdf_pages=_entero(cfg, "ingestion.max_pdf_pages", settings.max_pdf_pages),
        max_files_per_path=_entero(cfg, "ingestion.max_files_per_path", settings.max_files_per_path),
        max_corpus_tokens=_entero(cfg, "ingestion.max_corpus_tokens", settings.max_corpus_tokens),
        min_words_for_path=_entero(cfg, "ingestion.min_words_for_path", settings.min_words_for_path),
        scanned_pdf_min_chars_per_page=_entero(cfg, "ingestion.scanned_pdf_min_chars_per_page", 50),
        purge_after_days=_entero(cfg, "ingestion.purge_after_days", settings.purge_documents_after_days),
        chunk=_mapa(cfg, "ingestion.chunk", fragmentacion.CHUNK_POR_DEFECTO),
    )


# ---------------------------------------------------------------------------
# Paginación por cursor opaco (§8.2)
# ---------------------------------------------------------------------------


def codificar_cursor(clave: dict[str, Any]) -> str:
    """Codifica la última clave de orden como cursor opaco `base64(json)`."""
    crudo = json.dumps(clave, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(crudo).decode("ascii")


def decodificar_cursor(cursor: str | None) -> dict[str, Any] | None:
    """Decodifica un cursor; uno corrupto es `422`, nunca un `500`."""
    if not cursor:
        return None
    try:
        relleno = "=" * (-len(cursor) % 4)
        clave = json.loads(base64.urlsafe_b64decode(cursor + relleno).decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValidationFailed(
            "El cursor de paginación no es válido.",
            field_errors=[{"field": "cursor", "message": "Cursor ilegible."}],
        ) from exc
    if not isinstance(clave, dict):
        raise ValidationFailed(
            "El cursor de paginación no es válido.",
            field_errors=[{"field": "cursor", "message": "Cursor ilegible."}],
        )
    return clave


def normalizar_limite(limit: int | None) -> int:
    """Aplica el límite por defecto (20) y el máximo (100) del contrato."""
    if limit is None:
        return LIMITE_POR_DEFECTO
    return max(1, min(int(limit), LIMITE_MAXIMO))


@dataclass(slots=True)
class PaginaDocumentos:
    """Sobre de paginación de §8.2 aplicado a la lista de documentos."""

    items: list[Document] = field(default_factory=list)
    limit: int = LIMITE_POR_DEFECTO
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ResultadoDocumento:
    """Documento recién creado (o recuperado) junto a su versión y su trabajo."""

    document: Document
    version: DocumentVersion
    job: GenerationJob | None
    #: `True` si el binario ya estaba subido (mismo `content_hash`): no se reprocesa.
    duplicado: bool = False
    #: `True` si la petición repitió una `Idempotency-Key` ya usada: responde `200`.
    reintento: bool = False

    @property
    def nuevo(self) -> bool:
        """`True` cuando la petición creó material nuevo (responde `201`)."""
        return not (self.duplicado or self.reintento)


@dataclass(slots=True)
class ResultadoIngesta:
    """Resumen de procesar una versión de documento."""

    version: DocumentVersion
    chunk_count: int
    token_count: int
    word_count: int
    language: str | None
    embebidos: int
    rechazado: bool = False
    motivo: str | None = None


# ---------------------------------------------------------------------------
# Bibliotecas
# ---------------------------------------------------------------------------


def biblioteca_por_defecto(db: Session, usuario_id: uuid.UUID) -> KnowledgeBase:
    """Devuelve (creándola si hace falta) la biblioteca por defecto del usuario."""
    biblioteca = db.execute(
        sa.select(KnowledgeBase)
        .where(KnowledgeBase.user_id == usuario_id, KnowledgeBase.is_default.is_(True))
        .order_by(KnowledgeBase.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if biblioteca is not None:
        return biblioteca
    biblioteca = KnowledgeBase(
        user_id=usuario_id,
        name=NOMBRE_BIBLIOTECA_POR_DEFECTO,
        description="Material que subiste o pegaste en Atenea.",
        is_default=True,
    )
    db.add(biblioteca)
    db.flush()
    return biblioteca


def resolver_biblioteca(
    db: Session, usuario_id: uuid.UUID, knowledge_base_id: uuid.UUID | None
) -> KnowledgeBase:
    """Carga la biblioteca indicada comprobando la propiedad; si no hay, la por defecto."""
    if knowledge_base_id is None:
        return biblioteca_por_defecto(db, usuario_id)
    biblioteca = db.execute(
        sa.select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == usuario_id
        )
    ).scalar_one_or_none()
    if biblioteca is None:
        raise NotFound("No encontramos esa biblioteca de material.")
    return biblioteca


def recontar_biblioteca(db: Session, biblioteca: KnowledgeBase) -> KnowledgeBase:
    """Recalcula `document_count` y `total_tokens` desde las versiones vigentes."""
    documentos = int(
        db.execute(
            sa.select(sa.func.count(Document.id)).where(
                Document.knowledge_base_id == biblioteca.id, Document.deleted_at.is_(None)
            )
        ).scalar()
        or 0
    )
    tokens = int(
        db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(DocumentVersion.token_count), 0))
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.knowledge_base_id == biblioteca.id,
                Document.deleted_at.is_(None),
                DocumentVersion.is_current.is_(True),
            )
        ).scalar()
        or 0
    )
    biblioteca.document_count = documentos
    biblioteca.total_tokens = tokens
    db.flush()
    return biblioteca


# ---------------------------------------------------------------------------
# Eventos de dominio (§4.2 · Contenido, ingesta y generación)
# ---------------------------------------------------------------------------


def _emitir(
    db: Session,
    *,
    usuario_id: uuid.UUID | None,
    tipo: EventType,
    payload: dict[str, Any],
    clave: str,
    zona: str | None = None,
) -> None:
    """Persiste un evento de dominio de ingesta.

    Los cuatro eventos de este módulo (`DOCUMENT_UPLOADED`, `TEXT_PASTED`,
    `DOCUMENT_INGESTED`, `DOCUMENT_FAILED`) solo tienen consumidores de analítica y de
    interfaz (§4.2): **no otorgan recompensas**, así que se escriben con la primitiva del
    bus (`crear_evento_dominio`) en vez de arrancar la cascada del motor.
    """
    from app.modules.gamification import eventos  # noqa: PLC0415 - evita el ciclo de importación

    eventos.crear_evento_dominio(
        db,
        usuario_id=usuario_id,
        tipo=tipo,
        payload=payload,
        idempotency_key=clave[:120],
        source_module="ingestion",
        timezone=zona,
    )


# ---------------------------------------------------------------------------
# Alta de material
# ---------------------------------------------------------------------------


def _buscar_por_hash(
    db: Session, usuario_id: uuid.UUID, content_hash: str
) -> DocumentVersion | None:
    """Busca una versión viva del usuario con el mismo binario (deduplicación)."""
    return db.execute(
        sa.select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Document.user_id == usuario_id,
            Document.deleted_at.is_(None),
            DocumentVersion.content_hash == content_hash,
            DocumentVersion.status != DocumentStatus.REJECTED,
        )
        .order_by(DocumentVersion.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _documento_por_titulo(
    db: Session, *, usuario_id: uuid.UUID, knowledge_base_id: uuid.UUID, titulo: str
) -> Document | None:
    """Documento vivo con el mismo título en la misma biblioteca (para versionarlo)."""
    return db.execute(
        sa.select(Document).where(
            Document.user_id == usuario_id,
            Document.knowledge_base_id == knowledge_base_id,
            Document.title == titulo,
            Document.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def _nueva_version(
    db: Session,
    documento: Document,
    *,
    content_hash: str,
    storage_key: str,
    byte_size: int,
    momento: dt.datetime,
) -> DocumentVersion:
    """Crea la versión siguiente del documento y jubila la vigente."""
    anteriores = list(
        db.execute(
            sa.select(DocumentVersion).where(DocumentVersion.document_id == documento.id)
        )
        .scalars()
        .all()
    )
    siguiente = max((fila.version_number for fila in anteriores), default=0) + 1
    for fila in anteriores:
        if fila.is_current:
            fila.is_current = False
            if fila.status == DocumentStatus.READY:
                fila.status = DocumentStatus.SUPERSEDED
    db.flush()

    version = DocumentVersion(
        document_id=documento.id,
        version_number=siguiente,
        content_hash=content_hash,
        storage_key=storage_key,
        byte_size=byte_size,
        status=DocumentStatus.QUEUED,
        is_current=True,
    )
    db.add(version)
    documento.version_count = len(anteriores) + 1
    documento.status = DocumentStatus.QUEUED
    documento.updated_at = momento
    db.flush()
    return version


def _resultado_desde_trabajo(db: Session, trabajo: GenerationJob) -> ResultadoDocumento | None:
    """Reconstruye la respuesta de una petición idempotente ya atendida (§8.3)."""
    if trabajo.document_version_id is None:
        return None
    version = db.get(DocumentVersion, trabajo.document_version_id)
    if version is None:
        return None
    documento = db.get(Document, version.document_id)
    if documento is None:  # pragma: no cover - integridad referencial lo impide
        return None
    return ResultadoDocumento(
        document=documento, version=version, job=trabajo, duplicado=False, reintento=True
    )


def subir_archivo(
    db: Session,
    *,
    usuario_id: uuid.UUID,
    contenido: bytes,
    nombre_archivo: str | None,
    idempotency_key: str,
    knowledge_base_id: uuid.UUID | None = None,
    titulo: str | None = None,
    cfg: Any | None = None,
    zona: str | None = None,
    momento: dt.datetime | None = None,
) -> ResultadoDocumento:
    """`POST /documents`: valida, guarda con nombre opaco, versiona y encola la ingesta.

    El tipo se decide por **contenido** (magic bytes), no por la extensión; el tamaño se
    comprueba contra `ingestion.max_file_mb` antes de tocar el disco; y el binario idéntico
    ya subido se devuelve tal cual, sin reprocesar.
    """
    ahora = momento or utcnow()
    topes = limites(cfg)

    reintento = cola.por_clave(db, idempotency_key)
    if reintento is not None:
        previo = _resultado_desde_trabajo(db, reintento)
        if previo is not None:
            return previo

    extraccion.validar_tamano(contenido, max_bytes=topes.max_file_bytes)
    tipo = extraccion.detectar_tipo(nombre_archivo, contenido)
    content_hash = almacenamiento.hash_bytes(contenido)

    duplicada = _buscar_por_hash(db, usuario_id, content_hash)
    if duplicada is not None:
        documento = db.get(Document, duplicada.document_id)
        trabajos = cola.trabajos_de_version(db, duplicada.id)
        logger.info(
            "documento_duplicado",
            user_id=str(usuario_id),
            document_id=str(duplicada.document_id),
            content_hash=content_hash[:12],
        )
        return ResultadoDocumento(
            document=documento,  # type: ignore[arg-type]
            version=duplicada,
            job=trabajos[0] if trabajos else None,
            duplicado=True,
        )

    biblioteca = resolver_biblioteca(db, usuario_id, knowledge_base_id)
    nombre_visible = (titulo or nombre_archivo or "Material sin título").strip()[:255]

    documento = _documento_por_titulo(
        db, usuario_id=usuario_id, knowledge_base_id=biblioteca.id, titulo=nombre_visible
    )
    if documento is None:
        documento = Document(
            knowledge_base_id=biblioteca.id,
            user_id=usuario_id,
            title=nombre_visible,
            document_type=tipo.document_type,
            original_filename=(nombre_archivo or None),
            status=DocumentStatus.UPLOADED,
            version_count=0,
        )
        db.add(documento)
        db.flush()
    else:
        documento.document_type = tipo.document_type
        documento.original_filename = nombre_archivo or documento.original_filename

    storage_key = almacenamiento.nueva_clave(str(tipo.document_type))
    almacenamiento.guardar(storage_key, contenido)

    version = _nueva_version(
        db,
        documento,
        content_hash=content_hash,
        storage_key=storage_key,
        byte_size=len(contenido),
        momento=ahora,
    )
    recontar_biblioteca(db, biblioteca)

    _emitir(
        db,
        usuario_id=usuario_id,
        tipo=EventType.DOCUMENT_UPLOADED,
        payload={
            "document_id": str(documento.id),
            "document_version_id": str(version.id),
            "document_type": str(tipo.document_type),
            "byte_size": len(contenido),
            "extension_mismatch": tipo.extension_incoherente,
        },
        clave=f"document-uploaded:{usuario_id}:{version.id}",
        zona=zona,
    )

    trabajo = cola.encolar(
        db,
        job_type=JobType.DOCUMENT_INGESTION,
        queue=cola.COLA_INGESTA,
        usuario_id=usuario_id,
        payload={"document_version_id": str(version.id), "document_id": str(documento.id)},
        target_type="document",
        target_id=documento.id,
        document_version_id=version.id,
        priority=50,
        provider=embeddings.ajustes_de(cfg).provider,
        idempotency_key=idempotency_key,
        progress_label="En cola",
        momento=ahora,
    )
    return ResultadoDocumento(document=documento, version=version, job=trabajo)


def pegar_texto(
    db: Session,
    *,
    usuario_id: uuid.UUID,
    titulo: str,
    texto: str,
    idempotency_key: str,
    knowledge_base_id: uuid.UUID | None = None,
    cfg: Any | None = None,
    zona: str | None = None,
    momento: dt.datetime | None = None,
) -> ResultadoDocumento:
    """`POST /documents/paste`: material pegado como `DocumentType.PASTED_TEXT`.

    Se guarda igualmente en el almacén (UTF-8) para que el reprocesado y la trazabilidad
    funcionen exactamente igual que con un archivo subido.
    """
    ahora = momento or utcnow()
    topes = limites(cfg)

    reintento = cola.por_clave(db, idempotency_key)
    if reintento is not None:
        previo = _resultado_desde_trabajo(db, reintento)
        if previo is not None:
            return previo

    limpio = extraccion.limpiar_texto(texto or "")
    if not limpio.strip():
        raise ValidationFailed(
            "Pega algún texto antes de continuar.",
            field_errors=[{"field": "text", "message": "El texto no puede estar vacío."}],
        )

    contenido = limpio.encode("utf-8")
    extraccion.validar_tamano(contenido, max_bytes=topes.max_file_bytes)
    content_hash = almacenamiento.hash_bytes(contenido)

    duplicada = _buscar_por_hash(db, usuario_id, content_hash)
    if duplicada is not None:
        documento = db.get(Document, duplicada.document_id)
        trabajos = cola.trabajos_de_version(db, duplicada.id)
        return ResultadoDocumento(
            document=documento,  # type: ignore[arg-type]
            version=duplicada,
            job=trabajos[0] if trabajos else None,
            duplicado=True,
        )

    biblioteca = resolver_biblioteca(db, usuario_id, knowledge_base_id)
    nombre_visible = (titulo or "Texto pegado").strip()[:255] or "Texto pegado"

    documento = _documento_por_titulo(
        db, usuario_id=usuario_id, knowledge_base_id=biblioteca.id, titulo=nombre_visible
    )
    if documento is None:
        documento = Document(
            knowledge_base_id=biblioteca.id,
            user_id=usuario_id,
            title=nombre_visible,
            document_type=DocumentType.PASTED_TEXT,
            original_filename=None,
            status=DocumentStatus.UPLOADED,
            version_count=0,
        )
        db.add(documento)
        db.flush()

    storage_key = almacenamiento.nueva_clave(str(DocumentType.PASTED_TEXT))
    almacenamiento.guardar(storage_key, contenido)

    version = _nueva_version(
        db,
        documento,
        content_hash=content_hash,
        storage_key=storage_key,
        byte_size=len(contenido),
        momento=ahora,
    )
    recontar_biblioteca(db, biblioteca)

    _emitir(
        db,
        usuario_id=usuario_id,
        tipo=EventType.TEXT_PASTED,
        payload={
            "document_id": str(documento.id),
            "document_version_id": str(version.id),
            "word_count": extraccion.contar_palabras(limpio),
        },
        clave=f"text-pasted:{usuario_id}:{version.id}",
        zona=zona,
    )

    trabajo = cola.encolar(
        db,
        job_type=JobType.DOCUMENT_INGESTION,
        queue=cola.COLA_INGESTA,
        usuario_id=usuario_id,
        payload={"document_version_id": str(version.id), "document_id": str(documento.id)},
        target_type="document",
        target_id=documento.id,
        document_version_id=version.id,
        priority=50,
        provider=embeddings.ajustes_de(cfg).provider,
        idempotency_key=idempotency_key,
        progress_label="En cola",
        momento=ahora,
    )
    return ResultadoDocumento(document=documento, version=version, job=trabajo)


# ---------------------------------------------------------------------------
# Pipeline de ingesta (lo ejecuta el worker)
# ---------------------------------------------------------------------------


def _rechazar(
    db: Session,
    version: DocumentVersion,
    documento: Document,
    *,
    motivo: str,
    mensaje: str,
    detalles: dict[str, Any],
    zona: str | None,
    momento: dt.datetime,
) -> ResultadoIngesta:
    """Marca la versión como `REJECTED` y emite `DOCUMENT_FAILED` (§4.2)."""
    version.status = DocumentStatus.REJECTED
    version.error_message = mensaje
    version.processed_at = momento
    documento.status = DocumentStatus.REJECTED
    db.flush()
    _emitir(
        db,
        usuario_id=documento.user_id,
        tipo=EventType.DOCUMENT_FAILED,
        payload={
            "document_id": str(documento.id),
            "document_version_id": str(version.id),
            "reason": motivo,
            **detalles,
        },
        clave=f"document-failed:{documento.user_id}:{version.id}",
        zona=zona,
    )
    logger.warning(
        "documento_rechazado",
        document_id=str(documento.id),
        document_version_id=str(version.id),
        reason=motivo,
    )
    return ResultadoIngesta(
        version=version,
        chunk_count=0,
        token_count=0,
        word_count=version.word_count or 0,
        language=version.language,
        embebidos=0,
        rechazado=True,
        motivo=motivo,
    )


def procesar_version(
    db: Session,
    version: DocumentVersion,
    *,
    cfg: Any | None = None,
    trabajo: GenerationJob | None = None,
    proveedor: embeddings.ProveedorEmbeddings | None = None,
    zona: str | None = None,
    momento: dt.datetime | None = None,
) -> ResultadoIngesta:
    """Extrae, trocea y embebe una versión de documento hasta dejarla `READY`.

    Es **reentrante**: borra los fragmentos previos de la versión antes de insertar los
    nuevos, así que reprocesar (por reintento o por cambio de modelo de embeddings) no
    duplica nada. Los pasos se anotan en `generation_jobs.steps` para poder reanudar.

    Un rechazo del material (PDF escaneado, formato no admitido, material insuficiente)
    **no es reintentable**: se marca la versión `REJECTED`, se emite `DOCUMENT_FAILED` y
    se devuelve el resultado; el worker cierra el trabajo sin reintentar.
    """
    ahora = momento or utcnow()
    topes = limites(cfg)
    documento = db.get(Document, version.document_id)
    if documento is None:  # pragma: no cover - integridad referencial lo impide
        raise NotFound("No encontramos el documento de esa versión.")

    def progreso(paso: str) -> None:
        """Refleja la etapa en el trabajo, si lo hay."""
        if trabajo is None:
            return
        for nombre, pct, etiqueta in ETAPAS:
            if nombre == paso:
                cola.marcar_progreso(db, trabajo, pct=pct, label=etiqueta)
                return

    # --- 1. Extracción -----------------------------------------------------
    version.status = DocumentStatus.EXTRACTING
    documento.status = DocumentStatus.EXTRACTING
    db.flush()

    try:
        datos = almacenamiento.leer(version.storage_key)
    except (FileNotFoundError, OSError) as exc:
        raise NotFound("El archivo de ese material ya no está disponible.") from exc

    try:
        extraido = extraccion.extraer(
            datos,
            documento.document_type,
            max_paginas=topes.max_pdf_pages,
            min_chars_por_pagina=topes.scanned_pdf_min_chars_per_page,
        )
        extraccion.validar_material_suficiente(extraido, min_palabras=topes.min_words_for_path)
    except (
        extraccion.DocumentoIlegible,
        extraccion.TipoNoAdmitido,
        extraccion.ArchivoDemasiadoGrande,
    ) as exc:
        detalles = dict(exc.details or {})
        motivo = str(detalles.pop("reason", "unreadable"))
        return _rechazar(
            db,
            version,
            documento,
            motivo=motivo,
            mensaje=exc.message,
            detalles=detalles,
            zona=zona,
            momento=ahora,
        )

    version.word_count = extraido.word_count
    version.token_count = extraido.token_count
    version.language = extraido.language
    if extraido.page_count is not None:
        version.page_count = extraido.page_count
    db.flush()
    progreso("extract")
    if trabajo is not None:
        cola.registrar_paso(
            db, trabajo, "extract", {"word_count": extraido.word_count}, momento=ahora
        )

    # --- 2. Troceado -------------------------------------------------------
    version.status = DocumentStatus.CHUNKING
    documento.status = DocumentStatus.CHUNKING
    db.flush()

    parametros = fragmentacion.parametros_de(topes.chunk)
    fragmentos = fragmentacion.fragmentar(
        extraido.texto, parametros=parametros, paginas=extraido.paginas
    )
    if not fragmentos:
        return _rechazar(
            db,
            version,
            documento,
            motivo="no_chunks",
            mensaje="No encontramos contenido aprovechable en el material.",
            detalles={"min_words": topes.min_words_for_path},
            zona=zona,
            momento=ahora,
        )

    # Reentrada limpia: la tabla es append-only, así que se reemplaza el lote entero.
    db.execute(
        sa.delete(DocumentChunk).where(DocumentChunk.document_version_id == version.id)
    )
    filas: list[DocumentChunk] = []
    for fragmento in fragmentos:
        filas.append(
            DocumentChunk(
                document_version_id=version.id,
                document_id=documento.id,
                knowledge_base_id=documento.knowledge_base_id,
                user_id=documento.user_id,
                chunk_index=fragmento.chunk_index,
                chunk_type=fragmento.chunk_type,
                heading_path=list(fragmento.heading_path),
                text=fragmento.texto,
                token_count=fragmento.token_count,
                page_start=fragmento.page_start,
                page_end=fragmento.page_end,
                char_start=fragmento.char_start,
                char_end=fragmento.char_end,
                language=extraido.language,
                content_hash=fragmento.content_hash,
            )
        )
    db.add_all(filas)
    db.flush()
    progreso("chunk")
    if trabajo is not None:
        cola.registrar_paso(db, trabajo, "chunk", {"chunks": len(filas)}, momento=ahora)

    # --- 3. Embeddings -----------------------------------------------------
    version.status = DocumentStatus.EMBEDDING
    documento.status = DocumentStatus.EMBEDDING
    db.flush()

    ajustes = embeddings.ajustes_de(cfg)
    motor = proveedor or embeddings.obtener_proveedor(cfg)
    textos = [
        fragmentacion.texto_para_embeber(fragmento) for fragmento in fragmentos
    ]
    vectores = embeddings.embeber_por_lotes(motor, textos, batch_size=ajustes.batch_size)
    embebidos = 0
    for fila, vector in zip(filas, vectores, strict=False):
        if not vector or len(vector) != ajustes.dimensions:
            continue
        fila.embedding = vector
        fila.embedding_model = motor.modelo
        fila.embedding_dim = len(vector)
        embebidos += 1
    db.flush()
    progreso("embed")
    if trabajo is not None:
        cola.registrar_paso(
            db, trabajo, "embed", {"embedded": embebidos, "model": motor.modelo}, momento=ahora
        )

    # --- 4. Cierre ---------------------------------------------------------
    version.chunk_count = len(filas)
    version.token_count = sum(fila.token_count for fila in filas) or extraido.token_count
    version.status = DocumentStatus.READY
    version.error_message = None
    version.processed_at = ahora
    documento.status = DocumentStatus.READY
    db.flush()

    biblioteca = db.get(KnowledgeBase, documento.knowledge_base_id)
    if biblioteca is not None:
        recontar_biblioteca(db, biblioteca)

    _emitir(
        db,
        usuario_id=documento.user_id,
        tipo=EventType.DOCUMENT_INGESTED,
        payload={
            "document_id": str(documento.id),
            "document_version_id": str(version.id),
            "chunk_count": version.chunk_count,
            "token_count": version.token_count,
            "language": version.language,
        },
        clave=f"document-ingested:{documento.user_id}:{version.id}",
        zona=zona,
    )
    progreso("finish")
    logger.info(
        "documento_ingerido",
        document_id=str(documento.id),
        document_version_id=str(version.id),
        chunks=version.chunk_count,
        embebidos=embebidos,
    )
    return ResultadoIngesta(
        version=version,
        chunk_count=version.chunk_count,
        token_count=version.token_count,
        word_count=version.word_count or 0,
        language=version.language,
        embebidos=embebidos,
    )


def reindexar_version(
    db: Session,
    version: DocumentVersion,
    *,
    cfg: Any | None = None,
    proveedor: embeddings.ProveedorEmbeddings | None = None,
    trabajo: GenerationJob | None = None,
) -> int:
    """Recalcula los embeddings de una versión sin volver a extraer ni trocear.

    Es lo que hace `JobType.EMBEDDING_BATCH` cuando cambia el modelo del proveedor:
    `document_chunks.embedding_model` permite saber exactamente qué hay que reindexar.
    """
    ajustes = embeddings.ajustes_de(cfg)
    motor = proveedor or embeddings.obtener_proveedor(cfg)
    filas = list(
        db.execute(
            sa.select(DocumentChunk)
            .where(DocumentChunk.document_version_id == version.id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        .scalars()
        .all()
    )
    if not filas:
        return 0
    textos = [
        (" > ".join(fila.heading_path or []) + "\n\n" + fila.text).strip()
        if fila.heading_path
        else fila.text
        for fila in filas
    ]
    vectores = embeddings.embeber_por_lotes(motor, textos, batch_size=ajustes.batch_size)
    actualizados = 0
    for fila, vector in zip(filas, vectores, strict=False):
        if not vector or len(vector) != ajustes.dimensions:
            continue
        fila.embedding = vector
        fila.embedding_model = motor.modelo
        fila.embedding_dim = len(vector)
        actualizados += 1
    db.flush()
    if trabajo is not None:
        cola.registrar_paso(db, trabajo, "reindex", {"updated": actualizados})
    return actualizados


# ---------------------------------------------------------------------------
# Consultas de la API
# ---------------------------------------------------------------------------


def obtener_documento(db: Session, usuario_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    """Carga un documento del usuario; lo ajeno o lo borrado responde `404` (§8.7)."""
    documento = db.execute(
        sa.select(Document).where(
            Document.id == document_id,
            Document.user_id == usuario_id,
            Document.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if documento is None:
        raise NotFound("No encontramos ese material.")
    return documento


def version_vigente(db: Session, document_id: uuid.UUID) -> DocumentVersion | None:
    """Versión vigente (`is_current`) de un documento."""
    return db.execute(
        sa.select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id, DocumentVersion.is_current.is_(True))
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()


def versiones_vigentes(
    db: Session, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, DocumentVersion]:
    """Versiones vigentes de varios documentos, en una sola consulta."""
    if not document_ids:
        return {}
    filas = (
        db.execute(
            sa.select(DocumentVersion).where(
                DocumentVersion.document_id.in_(document_ids),
                DocumentVersion.is_current.is_(True),
            )
        )
        .scalars()
        .all()
    )
    return {fila.document_id: fila for fila in filas}


def listar_documentos(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    knowledge_base_id: uuid.UUID | None = None,
    estado: DocumentStatus | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> PaginaDocumentos:
    """`GET /documents`: lista paginada por cursor opaco, más reciente primero (§8.2)."""
    tamano = normalizar_limite(limit)
    consulta = sa.select(Document).where(
        Document.user_id == usuario_id, Document.deleted_at.is_(None)
    )
    if knowledge_base_id is not None:
        consulta = consulta.where(Document.knowledge_base_id == knowledge_base_id)
    if estado is not None:
        consulta = consulta.where(Document.status == estado)

    clave = decodificar_cursor(cursor)
    if clave:
        try:
            creado = dt.datetime.fromisoformat(str(clave["created_at"]).replace("Z", "+00:00"))
            ultimo = uuid.UUID(str(clave["id"]))
        except (KeyError, ValueError) as exc:
            raise ValidationFailed(
                "El cursor de paginación no es válido.",
                field_errors=[{"field": "cursor", "message": "Cursor ilegible."}],
            ) from exc
        consulta = consulta.where(
            sa.tuple_(Document.created_at, Document.id) < sa.tuple_(creado, ultimo)
        )

    filas = list(
        db.execute(
            consulta.order_by(Document.created_at.desc(), Document.id.desc()).limit(tamano + 1)
        )
        .scalars()
        .all()
    )
    hay_mas = len(filas) > tamano
    filas = filas[:tamano]
    siguiente = None
    if hay_mas and filas:
        ultimo_doc = filas[-1]
        siguiente = codificar_cursor(
            {
                "created_at": ultimo_doc.created_at.isoformat().replace("+00:00", "Z"),
                "id": str(ultimo_doc.id),
            }
        )
    total = int(
        db.execute(
            sa.select(sa.func.count(Document.id)).where(
                Document.user_id == usuario_id, Document.deleted_at.is_(None)
            )
        ).scalar()
        or 0
    )
    return PaginaDocumentos(
        items=filas, limit=tamano, next_cursor=siguiente, has_more=hay_mas, total=total
    )


def borrar_documento(
    db: Session,
    usuario_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    cfg: Any | None = None,
    momento: dt.datetime | None = None,
) -> Document:
    """`DELETE /documents/{id}`: borrado lógico inmediato y purga física diferida.

    El binario y los fragmentos siguen un tiempo (`ingestion.purge_after_days`, 30 días)
    para que el contenido ya generado a partir de ellos conserve su trazabilidad; el
    worker de mantenimiento los borra después.
    """
    ahora = momento or utcnow()
    documento = obtener_documento(db, usuario_id, document_id)
    topes = limites(cfg)

    documento.deleted_at = ahora
    documento.purge_after = ahora + dt.timedelta(days=topes.purge_after_days)
    documento.status = DocumentStatus.DELETED
    db.execute(
        sa.update(DocumentVersion)
        .where(DocumentVersion.document_id == documento.id)
        .values(status=DocumentStatus.DELETED, is_current=False)
        .execution_options(synchronize_session=False)
    )
    # Solo se cancelan los trabajos de **este** material, nunca los del usuario en bloque.
    for version in (
        db.execute(sa.select(DocumentVersion).where(DocumentVersion.document_id == documento.id))
        .scalars()
        .all()
    ):
        cola.cancelar_pendientes(
            db, document_version_id=version.id, motivo="Material eliminado.", momento=ahora
        )
    db.flush()

    biblioteca = db.get(KnowledgeBase, documento.knowledge_base_id)
    if biblioteca is not None:
        recontar_biblioteca(db, biblioteca)
    return documento


def obtener_fragmento(db: Session, usuario_id: uuid.UUID, chunk_id: uuid.UUID) -> DocumentChunk:
    """`GET /chunks/{id}`: fragmento original para la hoja «Fuente» de la app."""
    fragmento = db.execute(
        sa.select(DocumentChunk).where(
            DocumentChunk.id == chunk_id, DocumentChunk.user_id == usuario_id
        )
    ).scalar_one_or_none()
    if fragmento is None:
        raise NotFound("No encontramos ese fragmento.")
    return fragmento


def fragmentos_de_version(
    db: Session, document_version_id: uuid.UUID, *, tipos: list[ChunkType] | None = None
) -> list[DocumentChunk]:
    """Fragmentos de una versión, en orden de lectura."""
    consulta = sa.select(DocumentChunk).where(
        DocumentChunk.document_version_id == document_version_id
    )
    if tipos:
        consulta = consulta.where(DocumentChunk.chunk_type.in_(tipos))
    return list(db.execute(consulta.order_by(DocumentChunk.chunk_index.asc())).scalars().all())


# ---------------------------------------------------------------------------
# Rutas de aprendizaje: fuentes y estado de generación (§7.5)
# ---------------------------------------------------------------------------


def _ruta_visible(db: Session, usuario_id: uuid.UUID, path_id: uuid.UUID):
    """Carga una ruta visible para el usuario (propia o Ruta del Reino)."""
    from app.models.content import LearningPath  # noqa: PLC0415 - import perezoso

    ruta = db.execute(
        sa.select(LearningPath).where(
            LearningPath.id == path_id,
            sa.or_(LearningPath.user_id == usuario_id, LearningPath.user_id.is_(None)),
        )
    ).scalar_one_or_none()
    if ruta is None:
        raise NotFound("No encontramos esa ruta.")
    return ruta


def documentos_de_ruta(
    db: Session,
    usuario_id: uuid.UUID,
    path_id: uuid.UUID,
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> PaginaDocumentos:
    """`GET /paths/{id}/sources`: documentos que respaldan una ruta.

    Son los de la biblioteca (`knowledge_bases`) asociada a la ruta. Una ruta sin
    material (`sin_fuente`) devuelve una página vacía, no un error.
    """
    ruta = _ruta_visible(db, usuario_id, path_id)
    if ruta.knowledge_base_id is None:
        return PaginaDocumentos(items=[], limit=normalizar_limite(limit), total=0)
    return listar_documentos(
        db,
        usuario_id,
        knowledge_base_id=ruta.knowledge_base_id,
        limit=limit,
        cursor=cursor,
    )


@dataclass(slots=True)
class EstadoGeneracion:
    """Estado agregado de la generación de una ruta (`GenerationStatusOut`, §7.5)."""

    status: str
    stage: str | None
    progress_pct: float
    first_module_ready: bool
    eta_seconds: int | None
    jobs: list[GenerationJob] = field(default_factory=list)


def estado_generacion(
    db: Session, usuario_id: uuid.UUID, path_id: uuid.UUID, *, cfg: Any | None = None
) -> EstadoGeneracion:
    """`GET /paths/{id}/generation`: etapas, porcentaje y si el módulo 1 ya está listo.

    `eta_seconds` se estima con `ai.generation_targets`
    (`{"skeleton_seconds": 90, "first_module_seconds": 90}`) y el progreso observado; es
    una estimación para la barra de la pantalla P06, no un compromiso.
    """
    _ruta_visible(db, usuario_id, path_id)
    trabajos = cola.trabajos_de_ruta(db, path_id)

    if not trabajos:
        return EstadoGeneracion(
            status=str(JobStatus.PENDING),
            stage=None,
            progress_pct=0.0,
            first_module_ready=False,
            eta_seconds=None,
            jobs=[],
        )

    estados = [trabajo.status for trabajo in trabajos]
    if any(estado == JobStatus.RUNNING for estado in estados):
        agregado = JobStatus.RUNNING
    elif any(estado == JobStatus.PENDING for estado in estados):
        agregado = JobStatus.PENDING
    elif any(estado == JobStatus.NEEDS_ATTENTION for estado in estados):
        agregado = JobStatus.NEEDS_ATTENTION
    elif any(estado == JobStatus.FAILED for estado in estados):
        agregado = JobStatus.FAILED
    elif all(estado == JobStatus.CANCELLED for estado in estados):
        agregado = JobStatus.CANCELLED
    else:
        agregado = JobStatus.SUCCEEDED

    porcentaje = sum(float(trabajo.progress_pct or 0) for trabajo in trabajos) / len(trabajos)
    en_curso = next((t for t in trabajos if t.status == JobStatus.RUNNING), None)
    etiqueta = (en_curso or trabajos[-1]).progress_label

    primer_modulo = any(
        trabajo.job_type == JobType.MODULE_GENERATION and trabajo.status == JobStatus.SUCCEEDED
        for trabajo in trabajos
    )

    objetivos = _mapa(
        cfg, "ai.generation_targets", {"skeleton_seconds": 90, "first_module_seconds": 90}
    )
    total_estimado = int(objetivos.get("skeleton_seconds", 90)) + int(
        objetivos.get("first_module_seconds", 90)
    )
    eta = None
    if agregado in (JobStatus.PENDING, JobStatus.RUNNING):
        eta = max(0, int(total_estimado * (1 - porcentaje / 100.0)))

    return EstadoGeneracion(
        status=str(agregado),
        stage=etiqueta,
        progress_pct=round(porcentaje, 2),
        first_module_ready=primer_modulo,
        eta_seconds=eta,
        jobs=trabajos,
    )


# ---------------------------------------------------------------------------
# Mantenimiento (worker, cola `housekeeping`)
# ---------------------------------------------------------------------------


def borrar_material_del_usuario(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    cfg: Any | None = None,
    momento: dt.datetime | None = None,
) -> int:
    """Marca para purga **todo** el material de un aprendiz. Devuelve cuántos.

    Es lo que ocurre cuando alguien da de baja su cuenta. Hasta ahora no ocurría:
    `borrar_cuenta` emitía `USER_DELETED` y su propio docstring afirmaba que
    «`ingestion` consume para purgar sus documentos», pero ese consumidor no
    existía en ninguna parte. El resultado era que los archivos que el aprendiz
    había subido se quedaban en el disco y en la base para siempre, aunque
    hubiera pedido irse.

    No borra aquí el binario: hace exactamente lo mismo que borrar un documento a
    mano —marca el borrado lógico y fija `purge_after`— y deja que el
    mantenimiento del worker lo borre del disco cuando venza el plazo. Así el
    plazo de retención es uno solo, el de §3.3, en vez de dos reglas distintas
    según por dónde se pidiera el borrado.
    """
    documentos = list(
        db.execute(
            sa.select(Document.id).where(
                Document.user_id == usuario_id, Document.deleted_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    for document_id in documentos:
        borrar_documento(db, usuario_id, document_id, cfg=cfg, momento=momento)

    if documentos:
        logger.info(
            "material.borrado_por_baja",
            usuario_id=str(usuario_id),
            documentos=len(documentos),
        )
    return len(documentos)


def purgar_documentos(db: Session, *, momento: dt.datetime | None = None, tope: int = 200) -> int:
    """Purga física de los documentos cuyo plazo de retención venció (§3.3, 30 días).

    Borra el binario del almacén y la fila del documento (los fragmentos y las versiones
    caen por `ON DELETE CASCADE`). La trazabilidad sobrevive: `content_provenance` apunta
    a los documentos con `SET NULL`, así que el contenido generado no se pierde.
    """
    ahora = momento or utcnow()
    vencidos = list(
        db.execute(
            sa.select(Document)
            .where(
                Document.deleted_at.is_not(None),
                Document.purge_after.is_not(None),
                Document.purge_after <= ahora,
            )
            .limit(tope)
        )
        .scalars()
        .all()
    )
    purgados = 0
    for documento in vencidos:
        claves = list(
            db.execute(
                sa.select(DocumentVersion.storage_key).where(
                    DocumentVersion.document_id == documento.id
                )
            )
            .scalars()
            .all()
        )
        for clave in claves:
            try:
                almacenamiento.borrar(clave)
            except OSError:  # pragma: no cover - el almacén puede estar remoto
                logger.warning("purga_binario_fallida", storage_key=clave)
        db.delete(documento)
        purgados += 1
    db.flush()
    if purgados:
        logger.info("documentos_purgados", total=purgados)
    return purgados


__all__ = [
    "ESTADOS_EN_CURSO",
    "ETAPAS",
    "LIMITE_MAXIMO",
    "LIMITE_POR_DEFECTO",
    "NOMBRE_BIBLIOTECA_POR_DEFECTO",
    "EstadoGeneracion",
    "LimitesIngesta",
    "PaginaDocumentos",
    "ResultadoDocumento",
    "ResultadoIngesta",
    "biblioteca_por_defecto",
    "borrar_documento",
    "borrar_material_del_usuario",
    "codificar_cursor",
    "decodificar_cursor",
    "documentos_de_ruta",
    "estado_generacion",
    "fragmentos_de_version",
    "limites",
    "listar_documentos",
    "normalizar_limite",
    "obtener_documento",
    "obtener_fragmento",
    "pegar_texto",
    "procesar_version",
    "purgar_documentos",
    "recontar_biblioteca",
    "reindexar_version",
    "resolver_biblioteca",
    "subir_archivo",
    "version_vigente",
    "versiones_vigentes",
]
