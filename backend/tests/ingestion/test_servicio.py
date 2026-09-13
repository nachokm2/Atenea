"""Casos de uso de `ingestion`: subir, pegar, procesar, listar y borrar (§7.5, §8.2, §8.3).

Dos pruebas cumplen aquí una exigencia explícita del contrato interno del módulo:

* `test_subir_el_mismo_binario_dos_veces_no_reprocesa` — **la deduplicación por hash
  evita reprocesar**, que es lo que impide pagar dos veces la ingesta del mismo PDF.
* `test_un_pdf_escaneado_deja_la_version_rechazada_y_el_trabajo_fallido` — el PDF sin
  capa de texto se rechaza con el mensaje del contrato, de punta a punta.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from tests.ingestion.conftest import pdf_con_texto, pdf_en_blanco, texto_largo

from app.core.errors import DEFAULT_MESSAGES, NotFound, ValidationFailed
from app.models.enums import DocumentStatus, DocumentType, EventType, JobStatus, JobType
from app.models.gamification import DomainEvent
from app.models.identity import User
from app.models.ingestion import Document, DocumentChunk, DocumentVersion, KnowledgeBase
from app.modules.ingestion import almacenamiento, servicio
from app.worker import cola, principal

MATERIAL = (
    "# Manual de SQL\n\n"
    "## LEFT JOIN\n\n"
    "Un LEFT JOIN devuelve todas las filas de la tabla izquierda y las coincidencias "
    "de la derecha; cuando no hay coincidencia, las columnas de la derecha valen NULL.\n\n"
    "```sql\nSELECT c.nombre FROM clientes c LEFT JOIN pedidos p ON p.cliente_id = c.id;\n```\n\n"
    + texto_largo(420, "contenido")
)


def _clave() -> str:
    """Una `Idempotency-Key` nueva (UUID v4, §8.3)."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Alta de material
# ---------------------------------------------------------------------------


def test_pegar_texto_crea_documento_version_y_trabajo(
    db: Session, usuario: User, cfg: Any
) -> None:
    """`POST /documents/paste` deja el material listo para que lo tome el worker."""
    resultado = servicio.pegar_texto(
        db,
        usuario_id=usuario.id,
        titulo="Apuntes de SQL",
        texto=MATERIAL,
        idempotency_key=_clave(),
        cfg=cfg,
    )
    assert resultado.nuevo is True
    assert resultado.document.document_type == DocumentType.PASTED_TEXT
    assert resultado.document.title == "Apuntes de SQL"
    assert resultado.version.version_number == 1
    assert resultado.version.is_current is True
    assert resultado.version.status == DocumentStatus.QUEUED
    assert resultado.job is not None
    assert resultado.job.job_type == JobType.DOCUMENT_INGESTION
    assert resultado.job.queue == cola.COLA_INGESTA
    assert resultado.job.status == JobStatus.PENDING
    # El binario se guarda con clave opaca, no con el título ni el nombre del archivo.
    assert almacenamiento.existe(resultado.version.storage_key)
    assert "Apuntes" not in resultado.version.storage_key


def test_pegar_texto_vacio_es_422(db: Session, usuario: User, cfg: Any) -> None:
    """Un texto en blanco no es material: `422 VALIDATION_ERROR` con `field_errors`."""
    with pytest.raises(ValidationFailed) as excepcion:
        servicio.pegar_texto(
            db, usuario_id=usuario.id, titulo="Vacío", texto="   \n\n  ", idempotency_key=_clave(), cfg=cfg
        )
    assert excepcion.value.status_code == 422
    assert excepcion.value.field_errors[0]["field"] == "text"


def test_subir_archivo_detecta_el_tipo_por_contenido(
    db: Session, usuario: User, cfg: Any
) -> None:
    """El tipo persistido es el real (`pdf`), aunque la extensión diga otra cosa."""
    resultado = servicio.subir_archivo(
        db,
        usuario_id=usuario.id,
        contenido=pdf_con_texto(["Capitulo 1", texto_largo(400)]),
        nombre_archivo="material.txt",
        idempotency_key=_clave(),
        cfg=cfg,
    )
    assert resultado.document.document_type == DocumentType.PDF
    assert resultado.document.original_filename == "material.txt"
    assert resultado.version.storage_key.endswith(".pdf")


def test_se_crea_la_biblioteca_por_defecto_si_no_existe(
    db: Session, usuario: User, cfg: Any
) -> None:
    """La primera subida crea la biblioteca del usuario sin pedir nada al cliente."""
    resultado = servicio.pegar_texto(
        db, usuario_id=usuario.id, titulo="Primero", texto=MATERIAL, idempotency_key=_clave(), cfg=cfg
    )
    biblioteca = db.get(KnowledgeBase, resultado.document.knowledge_base_id)
    assert biblioteca is not None
    assert biblioteca.user_id == usuario.id
    assert biblioteca.is_default is True
    assert biblioteca.document_count == 1


def test_una_biblioteca_ajena_responde_404(db: Session, usuario: User, cfg: Any) -> None:
    """§8.7: no se puede subir material a la biblioteca de otra persona."""
    otro = User(email=f"otro-{uuid.uuid4().hex[:8]}@atenea.test", timezone="America/Santiago")
    db.add(otro)
    db.flush()
    ajena = KnowledgeBase(user_id=otro.id, name="Ajena", is_default=True)
    db.add(ajena)
    db.flush()

    with pytest.raises(NotFound):
        servicio.pegar_texto(
            db,
            usuario_id=usuario.id,
            titulo="Intruso",
            texto=MATERIAL,
            idempotency_key=_clave(),
            knowledge_base_id=ajena.id,
            cfg=cfg,
        )


# ---------------------------------------------------------------------------
# Idempotencia y deduplicación
# ---------------------------------------------------------------------------


def test_la_misma_idempotency_key_devuelve_la_misma_respuesta(
    db: Session, usuario: User, cfg: Any
) -> None:
    """§8.3: reintentar con la misma clave no crea nada nuevo y marca `reintento`."""
    clave = _clave()
    primero = servicio.pegar_texto(
        db, usuario_id=usuario.id, titulo="Apuntes", texto=MATERIAL, idempotency_key=clave, cfg=cfg
    )
    segundo = servicio.pegar_texto(
        db, usuario_id=usuario.id, titulo="Apuntes", texto=MATERIAL, idempotency_key=clave, cfg=cfg
    )
    assert segundo.reintento is True
    assert segundo.nuevo is False
    assert segundo.document.id == primero.document.id
    assert segundo.version.id == primero.version.id
    assert segundo.job.id == primero.job.id


def test_subir_el_mismo_binario_dos_veces_no_reprocesa(
    db: Session, usuario: User, cfg: Any
) -> None:
    """La deduplicación por SHA-256 evita pagar dos veces la ingesta del mismo material.

    Dos subidas distintas (claves de idempotencia diferentes) del **mismo binario** no
    crean una segunda versión ni un segundo trabajo: se devuelve lo que ya había.
    """
    contenido = pdf_con_texto(["Manual de SQL", texto_largo(500)])
    primero = servicio.subir_archivo(
        db,
        usuario_id=usuario.id,
        contenido=contenido,
        nombre_archivo="manual.pdf",
        idempotency_key=_clave(),
        cfg=cfg,
    )
    trabajos_antes = cola.pendientes(db, colas=[cola.COLA_INGESTA])

    segundo = servicio.subir_archivo(
        db,
        usuario_id=usuario.id,
        contenido=contenido,
        nombre_archivo="manual-copia.pdf",
        idempotency_key=_clave(),
        cfg=cfg,
    )

    assert segundo.duplicado is True
    assert segundo.nuevo is False
    assert segundo.version.id == primero.version.id
    assert segundo.version.content_hash == primero.version.content_hash
    assert cola.pendientes(db, colas=[cola.COLA_INGESTA]) == trabajos_antes

    versiones = db.execute(
        sa.select(sa.func.count(DocumentVersion.id)).where(
            DocumentVersion.document_id == primero.document.id
        )
    ).scalar()
    assert versiones == 1


def test_material_distinto_con_el_mismo_titulo_crea_una_version_nueva(
    db: Session, usuario: User, cfg: Any
) -> None:
    """Versionado: el documento sigue siendo uno y la versión anterior se jubila."""
    primero = servicio.pegar_texto(
        db, usuario_id=usuario.id, titulo="Apuntes", texto=MATERIAL, idempotency_key=_clave(), cfg=cfg
    )
    segundo = servicio.pegar_texto(
        db,
        usuario_id=usuario.id,
        titulo="Apuntes",
        texto=MATERIAL + "\n\nAmpliación del capitulo con mas contenido.",
        idempotency_key=_clave(),
        cfg=cfg,
    )
    assert segundo.document.id == primero.document.id
    assert segundo.version.version_number == 2
    assert segundo.version.is_current is True
    db.refresh(primero.version)
    assert primero.version.is_current is False
    assert segundo.document.version_count == 2


# ---------------------------------------------------------------------------
# Pipeline de ingesta
# ---------------------------------------------------------------------------


def test_procesar_version_trocea_embebe_y_deja_ready(
    db: Session, usuario: User, cfg: Any
) -> None:
    """De `QUEUED` a `READY`: fragmentos con embedding, métricas y evento emitido."""
    subida = servicio.pegar_texto(
        db, usuario_id=usuario.id, titulo="Manual", texto=MATERIAL, idempotency_key=_clave(), cfg=cfg
    )
    resultado = servicio.procesar_version(db, subida.version, cfg=cfg, trabajo=subida.job)

    assert resultado.rechazado is False
    assert resultado.chunk_count > 0
    assert resultado.embebidos == resultado.chunk_count
    assert subida.version.status == DocumentStatus.READY
    assert subida.document.status == DocumentStatus.READY
    assert subida.version.processed_at is not None
    assert subida.version.language == "es"

    fragmentos = servicio.fragmentos_de_version(db, subida.version.id)
    assert [f.chunk_index for f in fragmentos] == list(range(len(fragmentos)))
    assert all(f.user_id == usuario.id for f in fragmentos)
    assert all(f.embedding is not None and len(f.embedding) == 512 for f in fragmentos)
    assert all(f.embedding_dim == 512 for f in fragmentos)

    # El bloque de código llegó entero a su fragmento.
    codigo = [f for f in fragmentos if "LEFT JOIN pedidos p" in f.text]
    assert len(codigo) == 1

    evento = db.execute(
        sa.select(DomainEvent).where(
            DomainEvent.event_type == EventType.DOCUMENT_INGESTED,
            DomainEvent.user_id == usuario.id,
        )
    ).scalar_one_or_none()
    assert evento is not None
    assert evento.payload["document_version_id"] == str(subida.version.id)
    assert evento.source_module == "ingestion"


def test_reprocesar_una_version_no_duplica_fragmentos(
    db: Session, usuario: User, cfg: Any
) -> None:
    """El pipeline es reentrante: un reintento sustituye el lote, no lo suma."""
    subida = servicio.pegar_texto(
        db, usuario_id=usuario.id, titulo="Manual", texto=MATERIAL, idempotency_key=_clave(), cfg=cfg
    )
    primera = servicio.procesar_version(db, subida.version, cfg=cfg)
    segunda = servicio.procesar_version(db, subida.version, cfg=cfg)
    assert segunda.chunk_count == primera.chunk_count
    total = db.execute(
        sa.select(sa.func.count(DocumentChunk.id)).where(
            DocumentChunk.document_version_id == subida.version.id
        )
    ).scalar()
    assert total == primera.chunk_count


def test_material_demasiado_corto_se_rechaza(db: Session, usuario: User, cfg: Any) -> None:
    """`ingestion.min_words_for_path`: sin material no hay ruta que construir."""
    subida = servicio.pegar_texto(
        db,
        usuario_id=usuario.id,
        titulo="Breve",
        texto="Apenas unas pocas palabras sueltas.",
        idempotency_key=_clave(),
        cfg=cfg,
    )
    resultado = servicio.procesar_version(db, subida.version, cfg=cfg)
    assert resultado.rechazado is True
    assert resultado.motivo == "insufficient_content"
    assert subida.version.status == DocumentStatus.REJECTED


def test_un_pdf_escaneado_deja_la_version_rechazada_y_el_trabajo_fallido(
    db: Session, usuario: User, cfg: Any
) -> None:
    """De punta a punta: subida → worker → `DOCUMENT_FAILED` con el mensaje del contrato."""
    subida = servicio.subir_archivo(
        db,
        usuario_id=usuario.id,
        contenido=pdf_en_blanco(paginas=3),
        nombre_archivo="escaneado.pdf",
        idempotency_key=_clave(),
        cfg=cfg,
    )
    assert subida.job is not None

    ejecutado = principal.ejecutar_uno(db, colas=[cola.COLA_INGESTA], cfg=cfg)
    assert ejecutado is not None
    assert ejecutado.id == subida.job.id

    db.refresh(subida.version)
    db.refresh(subida.document)
    assert subida.version.status == DocumentStatus.REJECTED
    assert subida.document.status == DocumentStatus.REJECTED
    assert subida.version.error_message == DEFAULT_MESSAGES["DOCUMENT_UNREADABLE"]

    # El trabajo se cierra sin reintentar: el PDF seguirá estando escaneado.
    assert ejecutado.status == JobStatus.FAILED
    assert ejecutado.error_message == DEFAULT_MESSAGES["DOCUMENT_UNREADABLE"]
    assert ejecutado.result["error"]["reason"] == "scanned_pdf_no_text"

    evento = db.execute(
        sa.select(DomainEvent).where(
            DomainEvent.event_type == EventType.DOCUMENT_FAILED,
            DomainEvent.user_id == usuario.id,
        )
    ).scalar_one_or_none()
    assert evento is not None
    assert evento.payload["reason"] == "scanned_pdf_no_text"


def test_reindexar_recalcula_los_embeddings(db: Session, usuario: User, cfg: Any) -> None:
    """`EMBEDDING_BATCH`: cambiar de modelo no exige volver a extraer ni trocear."""
    subida = servicio.pegar_texto(
        db, usuario_id=usuario.id, titulo="Manual", texto=MATERIAL, idempotency_key=_clave(), cfg=cfg
    )
    servicio.procesar_version(db, subida.version, cfg=cfg)
    actualizados = servicio.reindexar_version(db, subida.version, cfg=cfg)
    assert actualizados == subida.version.chunk_count


# ---------------------------------------------------------------------------
# Consulta, paginación y borrado
# ---------------------------------------------------------------------------


def test_listado_pagina_por_cursor_opaco(db: Session, usuario: User, cfg: Any) -> None:
    """§8.2: cursor `base64(json)`, orden determinista y `has_more` coherente."""
    for indice in range(5):
        servicio.pegar_texto(
            db,
            usuario_id=usuario.id,
            titulo=f"Documento {indice}",
            texto=MATERIAL + f"\n\nVariante {indice}.",
            idempotency_key=_clave(),
            cfg=cfg,
        )

    primera = servicio.listar_documentos(db, usuario.id, limit=2)
    assert len(primera.items) == 2
    assert primera.has_more is True
    assert primera.total == 5
    assert primera.next_cursor

    segunda = servicio.listar_documentos(db, usuario.id, limit=2, cursor=primera.next_cursor)
    assert len(segunda.items) == 2
    ids_primera = {fila.id for fila in primera.items}
    assert not ids_primera & {fila.id for fila in segunda.items}


def test_un_cursor_corrupto_es_422_y_no_500(db: Session, usuario: User) -> None:
    """Un cursor manipulado es un error de validación, nunca una traza."""
    with pytest.raises(ValidationFailed) as excepcion:
        servicio.listar_documentos(db, usuario.id, cursor="no-es-base64-valido!!")
    assert excepcion.value.status_code == 422


def test_el_limite_se_acota_al_maximo_del_contrato() -> None:
    """§8.2: por defecto 20, máximo 100."""
    assert servicio.normalizar_limite(None) == 20
    assert servicio.normalizar_limite(1000) == 100
    assert servicio.normalizar_limite(0) == 1


def test_borrar_es_logico_con_purga_diferida(db: Session, usuario: User, cfg: Any) -> None:
    """`DELETE /documents/{id}`: desaparece ya; el binario se purga a los 30 días."""
    subida = servicio.pegar_texto(
        db, usuario_id=usuario.id, titulo="Temporal", texto=MATERIAL, idempotency_key=_clave(), cfg=cfg
    )
    documento = servicio.borrar_documento(db, usuario.id, subida.document.id, cfg=cfg)

    assert documento.deleted_at is not None
    assert documento.status == DocumentStatus.DELETED
    assert documento.purge_after is not None
    assert (documento.purge_after - documento.deleted_at).days == 30

    # Ya no aparece en el listado ni se puede volver a pedir.
    assert servicio.listar_documentos(db, usuario.id).items == []
    with pytest.raises(NotFound):
        servicio.obtener_documento(db, usuario.id, subida.document.id)

    # Y su trabajo pendiente queda cancelado: nadie procesa material borrado.
    db.refresh(subida.job)
    assert subida.job.status == JobStatus.CANCELLED


def test_la_purga_borra_el_binario_cuando_vence_el_plazo(
    db: Session, usuario: User, cfg: Any
) -> None:
    """Pasados los 30 días, el material desaparece del almacén y de la base."""
    subida = servicio.pegar_texto(
        db, usuario_id=usuario.id, titulo="Temporal", texto=MATERIAL, idempotency_key=_clave(), cfg=cfg
    )
    clave_almacen = subida.version.storage_key
    document_id = subida.document.id
    servicio.borrar_documento(db, usuario.id, document_id, cfg=cfg)

    futuro = dt.datetime.now(dt.UTC) + dt.timedelta(days=31)
    assert servicio.purgar_documentos(db, momento=futuro) >= 1
    assert almacenamiento.existe(clave_almacen) is False
    assert db.get(Document, document_id) is None


def test_un_documento_ajeno_responde_404(db: Session, usuario: User, cfg: Any) -> None:
    """§8.7: se responde `404` y no `403`, para no filtrar que el recurso existe."""
    otro = User(email=f"otro-{uuid.uuid4().hex[:8]}@atenea.test", timezone="America/Santiago")
    db.add(otro)
    db.flush()
    subida = servicio.pegar_texto(
        db, usuario_id=otro.id, titulo="Suyo", texto=MATERIAL, idempotency_key=_clave(), cfg=cfg
    )
    with pytest.raises(NotFound) as excepcion:
        servicio.obtener_documento(db, usuario.id, subida.document.id)
    assert excepcion.value.status_code == 404


def test_un_fragmento_ajeno_responde_404(db: Session, usuario: User, cfg: Any) -> None:
    """`GET /chunks/{id}` filtra por dueño igual que todo lo demás."""
    otro = User(email=f"otro-{uuid.uuid4().hex[:8]}@atenea.test", timezone="America/Santiago")
    db.add(otro)
    db.flush()
    subida = servicio.pegar_texto(
        db, usuario_id=otro.id, titulo="Suyo", texto=MATERIAL, idempotency_key=_clave(), cfg=cfg
    )
    servicio.procesar_version(db, subida.version, cfg=cfg)
    fragmento = servicio.fragmentos_de_version(db, subida.version.id)[0]

    assert servicio.obtener_fragmento(db, otro.id, fragmento.id).id == fragmento.id
    with pytest.raises(NotFound):
        servicio.obtener_fragmento(db, usuario.id, fragmento.id)
