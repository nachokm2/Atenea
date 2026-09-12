"""Rutas HTTP del módulo `ingestion` (§7.5, §8.1, §8.2, §8.3).

Se monta una app mínima con este router y se sustituyen `get_db` y `get_current_user`:
así se prueba el contrato de la API sin depender de `app/main.py` ni del router raíz,
que pertenecen a otros agentes.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import register_exception_handlers
from app.models.identity import User
from app.modules.ingestion import servicio
from app.modules.ingestion.router import router
from app.worker import cola
from tests.ingestion.conftest import docx_minimo, pdf_en_blanco, texto_largo

MATERIAL = (
    "# Manual de SQL\n\n## LEFT JOIN\n\nUn LEFT JOIN conserva la tabla izquierda.\n\n"
    + texto_largo(420, "contenido")
)


@pytest.fixture
def cliente(db: Session, usuario: User) -> Any:
    """Cliente HTTP con la sesión de prueba y el usuario ya autenticado."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario
    with TestClient(app) as cliente_http:
        yield cliente_http


def _clave() -> dict[str, str]:
    """Cabecera `Idempotency-Key` con un UUID v4 nuevo (§8.3)."""
    return {"Idempotency-Key": str(uuid.uuid4())}


# ---------------------------------------------------------------------------
# POST /documents y /documents/paste
# ---------------------------------------------------------------------------


def test_post_documents_paste_crea_el_material(cliente: Any) -> None:
    """`201` con el documento y su trabajo; los enums salen por su **valor** (§8.8)."""
    respuesta = cliente.post(
        "/api/v1/documents/paste",
        json={"title": "Apuntes de SQL", "text": MATERIAL},
        headers=_clave(),
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["document"]["title"] == "Apuntes de SQL"
    assert cuerpo["document"]["document_type"] == "pasted_text"
    assert cuerpo["document"]["status"] == "queued"
    assert cuerpo["document"]["current_version"]["version_number"] == 1
    assert cuerpo["job"]["job_type"] == "document_ingestion"
    assert cuerpo["job"]["status"] == "pending"
    assert cuerpo["duplicate"] is False
    # La clave del almacén jamás sale al cliente (§8.7).
    assert "storage_key" not in cuerpo["document"]["current_version"]


def test_post_documents_paste_sin_idempotency_key_es_400(cliente: Any) -> None:
    """§8.3: la cabecera es obligatoria en las rutas de alta."""
    respuesta = cliente.post(
        "/api/v1/documents/paste", json={"title": "Apuntes", "text": MATERIAL}
    )
    assert respuesta.status_code == 400
    assert respuesta.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_post_documents_paste_repetido_responde_200(cliente: Any) -> None:
    """§8.3: el reintento con la misma clave devuelve la misma respuesta con `200`."""
    cabecera = _clave()
    primero = cliente.post(
        "/api/v1/documents/paste",
        json={"title": "Apuntes", "text": MATERIAL},
        headers=cabecera,
    )
    segundo = cliente.post(
        "/api/v1/documents/paste",
        json={"title": "Apuntes", "text": MATERIAL},
        headers=cabecera,
    )
    assert primero.status_code == 201
    assert segundo.status_code == 200
    assert segundo.json()["retry"] is True
    assert segundo.json()["document"]["id"] == primero.json()["document"]["id"]


def test_post_documents_paste_con_texto_vacio_es_422(cliente: Any) -> None:
    """Pydantic rechaza el texto vacío con `VALIDATION_ERROR` y `field_errors` (§8.1)."""
    respuesta = cliente.post(
        "/api/v1/documents/paste", json={"title": "Vacío", "text": ""}, headers=_clave()
    )
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()["error"]
    assert cuerpo["code"] == "VALIDATION_ERROR"
    assert cuerpo["field_errors"]


def test_post_documents_sube_un_archivo(cliente: Any) -> None:
    """`POST /documents` multipart: el tipo se decide por contenido, no por extensión."""
    respuesta = cliente.post(
        "/api/v1/documents",
        files={"file": ("manual.txt", docx_minimo(["Un párrafo del manual."]), "text/plain")},
        headers=_clave(),
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["document"]["document_type"] == "docx"


def test_post_documents_con_formato_no_admitido_es_415(cliente: Any) -> None:
    """§8.1 `UNSUPPORTED_FILE_TYPE`: un ejecutable disfrazado de PDF se rechaza."""
    respuesta = cliente.post(
        "/api/v1/documents",
        files={"file": ("manual.pdf", b"MZ\x90\x00" + b"\x00" * 512, "application/pdf")},
        headers=_clave(),
    )
    assert respuesta.status_code == 415
    assert respuesta.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_post_documents_duplicado_responde_200(cliente: Any) -> None:
    """El mismo binario con otra clave no se reprocesa: `200` y `duplicate = true`."""
    binario = pdf_en_blanco(paginas=1)
    primero = cliente.post(
        "/api/v1/documents",
        files={"file": ("escaneado.pdf", binario, "application/pdf")},
        headers=_clave(),
    )
    segundo = cliente.post(
        "/api/v1/documents",
        files={"file": ("copia.pdf", binario, "application/pdf")},
        headers=_clave(),
    )
    assert primero.status_code == 201
    assert segundo.status_code == 200
    assert segundo.json()["duplicate"] is True


# ---------------------------------------------------------------------------
# GET /documents, detalle y borrado
# ---------------------------------------------------------------------------


def test_get_documents_devuelve_el_sobre_de_paginacion(cliente: Any) -> None:
    """§8.2: `{items, page:{limit, next_cursor, has_more, total}}`."""
    for indice in range(3):
        cliente.post(
            "/api/v1/documents/paste",
            json={"title": f"Documento {indice}", "text": MATERIAL + f"\n\nVariante {indice}."},
            headers=_clave(),
        )

    respuesta = cliente.get("/api/v1/documents", params={"limit": 2})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo["items"]) == 2
    assert cuerpo["page"]["limit"] == 2
    assert cuerpo["page"]["has_more"] is True
    assert cuerpo["page"]["total"] == 3

    siguiente = cliente.get(
        "/api/v1/documents", params={"limit": 2, "cursor": cuerpo["page"]["next_cursor"]}
    )
    assert siguiente.status_code == 200
    assert len(siguiente.json()["items"]) == 1


def test_get_document_ajeno_es_404(cliente: Any) -> None:
    """§8.7: un id que no existe (o no es del usuario) responde `404`, nunca `403`."""
    respuesta = cliente.get(f"/api/v1/documents/{uuid.uuid4()}")
    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "NOT_FOUND"


def test_delete_document_responde_204(cliente: Any) -> None:
    """El borrado lógico responde `204` sin cuerpo y saca el material del listado."""
    creado = cliente.post(
        "/api/v1/documents/paste",
        json={"title": "Temporal", "text": MATERIAL},
        headers=_clave(),
    ).json()

    borrado = cliente.delete(f"/api/v1/documents/{creado['document']['id']}")
    assert borrado.status_code == 204
    assert borrado.content == b""
    assert cliente.get("/api/v1/documents").json()["items"] == []


# ---------------------------------------------------------------------------
# GET /jobs/{id} y GET /chunks/{id}
# ---------------------------------------------------------------------------


def test_get_job_devuelve_el_estado_para_el_sondeo(cliente: Any) -> None:
    """`JobOut` `{id, job_type, status, progress_pct, progress_label, error}` (§7.5)."""
    creado = cliente.post(
        "/api/v1/documents/paste",
        json={"title": "Apuntes", "text": MATERIAL},
        headers=_clave(),
    ).json()

    respuesta = cliente.get(f"/api/v1/jobs/{creado['job']['id']}")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["id"] == creado["job"]["id"]
    assert cuerpo["job_type"] == "document_ingestion"
    assert cuerpo["status"] == "pending"
    assert cuerpo["progress_pct"] == 0.0
    assert cuerpo["error"] is None


def test_get_job_inexistente_es_404(cliente: Any) -> None:
    """Un trabajo que no existe responde `404 NOT_FOUND`."""
    assert cliente.get(f"/api/v1/jobs/{uuid.uuid4()}").status_code == 404


def test_get_chunk_devuelve_texto_y_procedencia(
    cliente: Any, db: Session, usuario: User, cfg: Any
) -> None:
    """`ChunkOut`: documento, páginas y texto; nunca el embedding."""
    creado = cliente.post(
        "/api/v1/documents/paste",
        json={"title": "Manual de SQL", "text": MATERIAL},
        headers=_clave(),
    ).json()
    version = servicio.version_vigente(db, uuid.UUID(creado["document"]["id"]))
    servicio.procesar_version(db, version, cfg=cfg)
    fragmento = servicio.fragmentos_de_version(db, version.id)[0]

    respuesta = cliente.get(f"/api/v1/chunks/{fragmento.id}")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["document_title"] == "Manual de SQL"
    assert cuerpo["chunk_index"] == 0
    assert cuerpo["chunk_type"] in ("prose", "code", "table", "list")
    assert "LEFT JOIN" in cuerpo["text"]
    assert "embedding" not in cuerpo


def test_get_chunk_inexistente_es_404(cliente: Any) -> None:
    """Un fragmento ajeno o inexistente responde `404`."""
    assert cliente.get(f"/api/v1/chunks/{uuid.uuid4()}").status_code == 404


# ---------------------------------------------------------------------------
# GET /paths/{id}/generation y /paths/{id}/sources
# ---------------------------------------------------------------------------


def test_generation_y_sources_de_una_ruta_inexistente_son_404(cliente: Any) -> None:
    """§8.7: una ruta que no es visible para el usuario responde `404`."""
    path_id = uuid.uuid4()
    assert cliente.get(f"/api/v1/paths/{path_id}/generation").status_code == 404
    assert cliente.get(f"/api/v1/paths/{path_id}/sources").status_code == 404


def test_todas_las_rutas_de_la_seccion_7_5_estan_montadas() -> None:
    """El router expone exactamente las nueve rutas de §7.5 que le tocan a este módulo."""
    montadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        for metodo in ruta.methods  # type: ignore[attr-defined]
        if metodo != "HEAD"
    }
    assert montadas == {
        ("POST", "/documents"),
        ("POST", "/documents/paste"),
        ("GET", "/documents"),
        ("GET", "/documents/{document_id}"),
        ("DELETE", "/documents/{document_id}"),
        ("GET", "/jobs/{job_id}"),
        ("GET", "/chunks/{chunk_id}"),
        ("GET", "/paths/{path_id}/generation"),
        ("GET", "/paths/{path_id}/sources"),
    }


def test_el_router_no_encola_nada_por_su_cuenta(db: Session) -> None:
    """Cordura: sin peticiones, la cola de ingesta de esta transacción está vacía."""
    assert cola.pendientes(db, colas=[cola.COLA_INGESTA]) == 0
