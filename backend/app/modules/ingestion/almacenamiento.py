"""Almacenamiento privado del material del usuario (CONTRACT.md §3.3, §8.7).

El binario que sube una persona **nunca** se guarda con su nombre original ni en una
ruta adivinable: `document_versions.storage_key` es una clave **opaca** y agnóstica del
proveedor (`documents/ab/ab3f…c9.pdf`), de modo que el mismo valor sirva para el disco
local en desarrollo y para el bucket de Railway en producción sin migrar datos.

Reglas aplicadas aquí:

* La clave no contiene el identificador del usuario, ni el nombre del fichero, ni la
  extensión real declarada por el cliente: solo un UUID4 y el sufijo del tipo **detectado
  por contenido**. Así el nombre no filtra información ni permite enumerar material ajeno.
* Toda clave se valida contra escapes de directorio (`..`, rutas absolutas, unidades de
  Windows) antes de tocar el disco: una clave manipulada nunca sale de `STORAGE_DIR`.
* La escritura es atómica (fichero temporal + `os.replace`) para que un worker que muera
  a medias no deje un binario truncado que el pipeline daría por bueno.

El directorio base sale de `settings.storage_path`; las pruebas lo redirigen con
`fijar_directorio()` sin tocar la configuración global.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.errors import ValidationFailed

#: Prefijo lógico de todo el material documental dentro del almacén.
PREFIJO_DOCUMENTOS = "documents"

#: Sufijo de archivo por tipo detectado. Es cosmético: el tipo real vive en la base.
SUFIJOS: dict[str, str] = {
    "pdf": ".pdf",
    "docx": ".docx",
    "markdown": ".md",
    "txt": ".txt",
    "pasted_text": ".txt",
}

#: Sobrescritura del directorio base (solo pruebas y scripts). `None` = usar `settings`.
_DIRECTORIO: Path | None = None


def fijar_directorio(ruta: str | Path | None) -> None:
    """Redirige el almacén a otro directorio (pruebas); `None` restaura `settings`."""
    global _DIRECTORIO
    _DIRECTORIO = Path(ruta).resolve() if ruta is not None else None


def directorio_base() -> Path:
    """Directorio raíz del almacén, creado si aún no existe."""
    base = _DIRECTORIO if _DIRECTORIO is not None else settings.storage_path
    base.mkdir(parents=True, exist_ok=True)
    return base


# ---------------------------------------------------------------------------
# Claves opacas
# ---------------------------------------------------------------------------


def nueva_clave(tipo: str) -> str:
    """Devuelve una `storage_key` opaca y única para un tipo de documento.

    Formato: `documents/<2 hex>/<32 hex><sufijo>`. El fragmento de dos caracteres
    reparte los ficheros en 256 subdirectorios y evita directorios con millones de
    entradas; el resto es un UUID4 sin guiones.
    """
    opaco = uuid.uuid4().hex
    sufijo = SUFIJOS.get(str(tipo), "")
    return f"{PREFIJO_DOCUMENTOS}/{opaco[:2]}/{opaco}{sufijo}"


def validar_clave(storage_key: str) -> str:
    """Normaliza y valida una clave; lanza `ValidationFailed` si intenta escapar."""
    clave = str(storage_key or "").strip().replace("\\", "/")
    if not clave:
        raise ValidationFailed(
            "No pudimos localizar el archivo del documento.",
            field_errors=[{"field": "storage_key", "message": "Clave vacía."}],
        )
    partes = [parte for parte in clave.split("/") if parte not in ("", ".")]
    if any(parte == ".." for parte in partes) or clave.startswith("/") or ":" in clave:
        raise ValidationFailed(
            "No pudimos localizar el archivo del documento.",
            field_errors=[{"field": "storage_key", "message": "Clave inválida."}],
        )
    return "/".join(partes)


def ruta_local(storage_key: str) -> Path:
    """Traduce una clave a una ruta absoluta dentro del almacén, ya validada."""
    base = directorio_base()
    destino = (base / validar_clave(storage_key)).resolve()
    try:
        destino.relative_to(base.resolve())
    except ValueError as exc:  # pragma: no cover - lo impide `validar_clave`
        raise ValidationFailed(
            "No pudimos localizar el archivo del documento.",
            field_errors=[{"field": "storage_key", "message": "Clave fuera del almacén."}],
        ) from exc
    return destino


# ---------------------------------------------------------------------------
# Lectura y escritura
# ---------------------------------------------------------------------------


def guardar(storage_key: str, datos: bytes) -> int:
    """Escribe el binario de forma atómica y devuelve su tamaño en bytes."""
    destino = ruta_local(storage_key)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{destino.name}.{uuid.uuid4().hex[:8]}.tmp")
    temporal.write_bytes(datos)
    os.replace(temporal, destino)
    return len(datos)


def leer(storage_key: str) -> bytes:
    """Lee el binario guardado; lanza `FileNotFoundError` si ya fue purgado."""
    return ruta_local(storage_key).read_bytes()


def existe(storage_key: str) -> bool:
    """Indica si el binario sigue disponible en el almacén."""
    try:
        return ruta_local(storage_key).is_file()
    except ValidationFailed:
        return False


def tamano(storage_key: str) -> int:
    """Tamaño en bytes del binario guardado (0 si no existe)."""
    ruta = ruta_local(storage_key)
    return ruta.stat().st_size if ruta.is_file() else 0


def borrar(storage_key: str) -> bool:
    """Borra el binario (purga física). Devuelve `True` si había algo que borrar."""
    try:
        ruta = ruta_local(storage_key)
    except ValidationFailed:
        return False
    if not ruta.is_file():
        return False
    ruta.unlink()
    return True


# ---------------------------------------------------------------------------
# Huellas
# ---------------------------------------------------------------------------


def hash_bytes(datos: bytes) -> str:
    """SHA-256 hexadecimal del binario (`document_versions.content_hash`)."""
    return hashlib.sha256(datos).hexdigest()


def hash_texto(texto: str) -> str:
    """SHA-256 hexadecimal de un texto normalizado (`document_chunks.content_hash`)."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


__all__ = [
    "PREFIJO_DOCUMENTOS",
    "SUFIJOS",
    "borrar",
    "directorio_base",
    "existe",
    "fijar_directorio",
    "guardar",
    "hash_bytes",
    "hash_texto",
    "leer",
    "nueva_clave",
    "ruta_local",
    "tamano",
    "validar_clave",
]
