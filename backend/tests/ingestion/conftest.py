"""Fixtures del módulo `ingestion`.

Las pruebas que tocan datos usan la **base real de desarrollo** dentro de una
transacción que siempre se revierte: la sesión se crea sobre una conexión con una
transacción externa abierta y `join_transaction_mode="create_savepoint"`, de modo que
los `begin_nested()` del código de producción funcionen igual que en la API y nada
quede escrito al terminar.

El almacén de binarios se redirige a un directorio temporal con
`almacenamiento.fijar_directorio()`: ninguna prueba escribe en `STORAGE_DIR`.
"""

from __future__ import annotations

import io
import os
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.identity import User
from app.models.ingestion import KnowledgeBase
from app.modules.gamification.servicio_config import invalidar_cache
from app.modules.ingestion import almacenamiento

URL_PRUEBAS = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea_test"
)

#: Semilla de `game_configs` con los valores literales de §5.8.
CONFIGURACION_SEMILLA: dict[str, Any] = {
    "ingestion.max_file_mb": 25,
    "ingestion.max_pdf_pages": 300,
    "ingestion.max_files_per_path": 10,
    "ingestion.max_corpus_tokens": 150000,
    "ingestion.min_words_for_path": 300,
    "ingestion.max_ingest_minutes": 5,
    "ingestion.chunk": {
        "target_tokens": 450,
        "max_tokens": 800,
        "min_tokens": 80,
        "overlap_pct": 0.12,
    },
    "ingestion.scanned_pdf_min_chars_per_page": 50,
    "ingestion.purge_after_days": 30,
    "ai.embeddings": {
        "provider": "mock",
        "model": "voyage-3-lite",
        "dimensions": 512,
        "batch_size": 128,
    },
    "ai.retrieval": {
        "vector_top_k": 20,
        "lexical_top_k": 20,
        "rrf_k": 60,
        "design_bonus": 0.02,
        "final_top_k": 10,
        "reexplain_top_k": 6,
        "min_score_ratio": 0.4,
    },
    "ai.generation_targets": {"skeleton_seconds": 90, "first_module_seconds": 90},
}


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def engine() -> Any:
    """Motor síncrono contra la base de desarrollo."""
    motor = sa.create_engine(URL_PRUEBAS, future=True, pool_pre_ping=True)
    try:
        with motor.connect() as conexion:
            conexion.execute(sa.text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - entorno sin base
        pytest.skip(f"Base de datos de pruebas no disponible: {exc}")
    yield motor
    motor.dispose()


@pytest.fixture
def db(engine: Any) -> Session:
    """Sesión transaccional que se revierte por completo al final de cada prueba."""
    conexion = engine.connect()
    transaccion = conexion.begin()
    sesion = Session(
        bind=conexion,
        future=True,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()


# ---------------------------------------------------------------------------
# Almacén de binarios
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def almacen(tmp_path) -> Any:
    """Redirige `STORAGE_DIR` a un directorio temporal durante toda la prueba."""
    almacenamiento.fijar_directorio(tmp_path / "storage")
    yield tmp_path / "storage"
    almacenamiento.fijar_directorio(None)


# ---------------------------------------------------------------------------
# Semillas
# ---------------------------------------------------------------------------


class ConfigDePruebas:
    """Lector de `game_configs` en memoria con la misma interfaz que `ServicioConfig`.

    No se siembra la tabla real por una razón concreta: `game_configs` tiene
    `UNIQUE (key, version)` y la base de desarrollo la comparten varias suites a la vez;
    dos transacciones que insertan la misma clave se bloquean entre sí hasta que una
    termina. Con este doble, las pruebas del módulo son deterministas, no dependen de
    quién más esté trabajando y siguen leyendo **exactamente** los valores de §5.8.
    """

    __slots__ = ("valores",)

    def __init__(self, valores: dict[str, Any]) -> None:
        self.valores = dict(valores)

    def obtener(self, clave: str, por_defecto: Any = None) -> Any:
        """Valor crudo de la clave."""
        return self.valores.get(clave, por_defecto)

    def obtener_int(self, clave: str, por_defecto: Any = 0) -> int:
        """Valor entero de la clave."""
        return int(self.valores.get(clave, por_defecto))

    def obtener_json(self, clave: str, por_defecto: Any = None) -> dict[str, Any]:
        """Valor de tipo mapa de la clave."""
        return dict(self.valores.get(clave, por_defecto) or {})

    def obtener_lista(self, clave: str, por_defecto: Any = None) -> list[Any]:
        """Valor de tipo lista de la clave."""
        return list(self.valores.get(clave, por_defecto) or [])

    def obtener_str(self, clave: str, por_defecto: Any = "") -> str:
        """Valor de texto de la clave."""
        return str(self.valores.get(clave, por_defecto))

    def obtener_bool(self, clave: str, por_defecto: Any = False) -> bool:
        """Valor booleano de la clave."""
        return bool(self.valores.get(clave, por_defecto))


@pytest.fixture
def configuracion() -> dict[str, Any]:
    """Semilla de §5.8 que usan las pruebas del módulo."""
    return dict(CONFIGURACION_SEMILLA)


@pytest.fixture
def cfg(configuracion: dict[str, Any]) -> ConfigDePruebas:
    """Configuración de juego de la prueba, con los valores literales del contrato."""
    invalidar_cache()
    return ConfigDePruebas(configuracion)


@pytest.fixture
def usuario(db: Session) -> User:
    """Usuario de pruebas con zona horaria chilena."""
    fila = User(
        email=f"ingesta-{uuid.uuid4().hex[:12]}@atenea.test",
        password_hash=None,
        timezone="America/Santiago",
    )
    db.add(fila)
    db.flush()
    return fila


@pytest.fixture
def biblioteca(db: Session, usuario: User) -> KnowledgeBase:
    """Biblioteca por defecto del usuario de pruebas."""
    fila = KnowledgeBase(
        user_id=usuario.id,
        name="Mi material",
        description="Biblioteca de pruebas.",
        is_default=True,
    )
    db.add(fila)
    db.flush()
    return fila


# ---------------------------------------------------------------------------
# Fábricas de binarios
# ---------------------------------------------------------------------------


def pdf_en_blanco(paginas: int = 2) -> bytes:
    """PDF válido y sin capa de texto: lo que produce un escáner sin OCR."""
    from pypdf import PdfWriter

    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def pdf_con_texto(lineas: list[str]) -> bytes:
    """PDF mínimo de una página con una capa de texto real (Helvetica, Type1).

    Se construye a mano en lugar de con una dependencia de maquetación: el objetivo es
    que `pypdf.extract_text()` devuelva exactamente estas líneas, de forma determinista.
    """
    contenido = "BT /F1 12 Tf 1 0 0 1 40 800 Tm 14 TL\n"
    for linea in lineas:
        seguro = linea.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")
        contenido += f"({seguro}) Tj T*\n"
    contenido += "ET"
    flujo = contenido.encode("latin-1", errors="replace")

    objetos: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842]"
        b" /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(flujo)).encode() + b" >>\nstream\n" + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones: list[int] = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{numero} 0 obj\n".encode() + cuerpo + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n".encode() + b"0000000000 65535 f \n"
    for posicion in posiciones:
        salida += f"{posicion:010d} 00000 n \n".encode()
    salida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n"
    ).encode()
    return bytes(salida)


def docx_minimo(parrafos: list[str]) -> bytes:
    """DOCX real (ZIP con `word/document.xml`) construido con `python-docx`."""
    import docx

    documento = docx.Document()
    for texto in parrafos:
        documento.add_paragraph(texto)
    buffer = io.BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def texto_largo(palabras: int = 400, semilla: str = "aprendizaje") -> str:
    """Texto de prosa con el número de palabras pedido (supera `min_words_for_path`)."""
    return " ".join(f"{semilla}{indice % 37}" for indice in range(palabras))


@pytest.fixture
def fabrica_binarios() -> dict[str, Any]:
    """Acceso a las fábricas de binarios desde las pruebas."""
    return {
        "pdf_en_blanco": pdf_en_blanco,
        "pdf_con_texto": pdf_con_texto,
        "docx_minimo": docx_minimo,
        "texto_largo": texto_largo,
    }
