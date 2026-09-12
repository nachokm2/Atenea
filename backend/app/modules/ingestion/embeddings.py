"""Proveedor de embeddings intercambiable: `mock` determinista y `voyage` real (§5.8).

El contrato fija `Vector(512)` y distancia coseno (D14), y deja el proveedor en
`ai.embeddings` de `game_configs`
(`{"provider": "voyage", "model": "voyage-3-lite", "dimensions": 512, "batch_size": 128}`).
El código nunca escribe esos valores: los lee de la configuración y cae a `settings`
cuando la configuración de juego todavía no está sembrada.

Dos implementaciones detrás de la misma interfaz:

* **`mock`** (por defecto en desarrollo y pruebas) — *hashing vectorizer* determinista:
  cada palabra se proyecta con `blake2b` a una de las 512 dimensiones con signo ±1, se
  suman y se normaliza a norma 1. Propiedades que importan: el **mismo texto siempre da
  el mismo vector** (sin red, sin coste, sin estado), y dos textos que comparten
  vocabulario quedan cerca en coseno, así que la recuperación híbrida se puede probar de
  verdad en local. Un texto sin palabras cae a un vector derivado del hash completo.
* **`voyage`** — llamada real a `voyage-3-lite` con `output_dimension=512`, por lotes de
  `batch_size`, con reintentos exponenciales. Nunca se invoca en pruebas.

Cambiar de proveedor no exige migración: `document_chunks.embedding_model` y
`embedding_dim` quedan grabados en cada fragmento para poder reindexar por lotes.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger("atenea.ingestion.embeddings")

#: Valores de respaldo de `ai.embeddings` (§5.8).
EMBEDDINGS_POR_DEFECTO: dict[str, Any] = {
    "provider": "voyage",
    "model": "voyage-3-lite",
    "dimensions": 512,
    "batch_size": 128,
}

#: Nombre del modelo que se graba en `document_chunks.embedding_model` con el proveedor mock.
MODELO_MOCK = "mock-hash-512"

#: Extremo de la API de Voyage AI.
URL_VOYAGE = "https://api.voyageai.com/v1/embeddings"

_TOKEN = re.compile(r"\w+", re.UNICODE)


@dataclass(slots=True)
class AjustesEmbeddings:
    """Ajustes efectivos del proveedor, resueltos desde `ai.embeddings`."""

    provider: str
    model: str
    dimensions: int
    batch_size: int


@runtime_checkable
class ProveedorEmbeddings(Protocol):
    """Interfaz mínima que debe cumplir cualquier proveedor de embeddings."""

    nombre: str
    modelo: str
    dimensiones: int

    def embeber(self, textos: list[str], *, consulta: bool = False) -> list[list[float]]:
        """Devuelve un vector por texto, en el mismo orden."""
        ...


# ---------------------------------------------------------------------------
# Proveedor mock determinista
# ---------------------------------------------------------------------------


def _normalizar(vector: list[float]) -> list[float]:
    """Normaliza a norma 1 para que el producto punto sea el coseno."""
    norma = math.sqrt(sum(valor * valor for valor in vector))
    if norma == 0.0:
        return vector
    return [valor / norma for valor in vector]


def _vector_de_hash(texto: str, dimensiones: int) -> list[float]:
    """Vector pseudoaleatorio pero determinista derivado del hash del texto completo."""
    crudo = bytearray()
    semilla = hashlib.sha256(texto.encode("utf-8")).digest()
    contador = 0
    while len(crudo) < dimensiones * 2:
        crudo += hashlib.sha256(semilla + contador.to_bytes(4, "big")).digest()
        contador += 1
    valores = [
        int.from_bytes(crudo[posicion * 2 : posicion * 2 + 2], "big", signed=True) / 32768.0
        for posicion in range(dimensiones)
    ]
    return _normalizar(valores)


class ProveedorMock:
    """Embeddings deterministas sin red ni coste (*hashing vectorizer* con signo).

    Invariante que las pruebas verifican: `embeber([t]) == embeber([t])` siempre, en
    cualquier proceso y en cualquier máquina, porque solo depende de `blake2b` sobre las
    palabras del texto.
    """

    nombre = "mock"

    def __init__(self, *, dimensiones: int = 512, modelo: str = MODELO_MOCK) -> None:
        self.dimensiones = int(dimensiones)
        self.modelo = modelo

    def _vector(self, texto: str) -> list[float]:
        """Proyecta las palabras del texto sobre el espacio de `dimensiones`."""
        acumulado = [0.0] * self.dimensiones
        tokens = _TOKEN.findall(texto.lower())
        if not tokens:
            return _vector_de_hash(texto, self.dimensiones)
        for token in tokens:
            huella = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            indice = int.from_bytes(huella[:4], "big") % self.dimensiones
            signo = 1.0 if huella[4] & 1 else -1.0
            acumulado[indice] += signo
        if not any(acumulado):  # pragma: no cover - colisión total, extremadamente raro
            return _vector_de_hash(texto, self.dimensiones)
        return _normalizar(acumulado)

    def embeber(self, textos: list[str], *, consulta: bool = False) -> list[list[float]]:
        """Devuelve un vector determinista por texto (el flag `consulta` no cambia nada)."""
        return [self._vector(texto or "") for texto in textos]


# ---------------------------------------------------------------------------
# Proveedor Voyage AI
# ---------------------------------------------------------------------------


class ProveedorVoyage:
    """Embeddings reales de Voyage AI (`voyage-3-lite`, 512 dimensiones, coseno)."""

    nombre = "voyage"

    def __init__(
        self,
        *,
        api_key: str,
        modelo: str = "voyage-3-lite",
        dimensiones: int = 512,
        tiempo_limite: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.modelo = modelo
        self.dimensiones = int(dimensiones)
        self.tiempo_limite = tiempo_limite

    def _llamar(self, textos: list[str], tipo: str) -> list[list[float]]:
        """Una llamada al extremo de embeddings, con reintentos exponenciales."""
        import httpx  # noqa: PLC0415 - importación perezosa: solo con proveedor real
        from tenacity import (  # noqa: PLC0415
            retry,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential,
        )

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        )
        def _peticion() -> list[list[float]]:
            respuesta = httpx.post(
                URL_VOYAGE,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": textos,
                    "model": self.modelo,
                    "input_type": tipo,
                    "output_dimension": self.dimensiones,
                },
                timeout=self.tiempo_limite,
            )
            respuesta.raise_for_status()
            cuerpo = respuesta.json()
            datos = sorted(cuerpo.get("data", []), key=lambda fila: fila.get("index", 0))
            return [list(fila["embedding"]) for fila in datos]

        try:
            return _peticion()
        except Exception as exc:  # noqa: BLE001 - se traduce al error del catálogo
            logger.warning("embeddings_voyage_error", error=str(exc))
            raise ExternalServiceError(
                "No pudimos indexar tu material en este momento. Inténtalo de nuevo.",
                details={"provider": "voyage", "model": self.modelo},
            ) from exc

    def embeber(self, textos: list[str], *, consulta: bool = False) -> list[list[float]]:
        """Embeddings de Voyage; `consulta=True` usa `input_type="query"`."""
        if not textos:
            return []
        vectores = self._llamar(textos, "query" if consulta else "document")
        if len(vectores) != len(textos):
            raise ExternalServiceError(
                "No pudimos indexar tu material en este momento. Inténtalo de nuevo.",
                details={"provider": "voyage", "expected": len(textos), "received": len(vectores)},
            )
        return vectores


# ---------------------------------------------------------------------------
# Selección del proveedor
# ---------------------------------------------------------------------------


def ajustes_de(cfg: Any | None = None) -> AjustesEmbeddings:
    """Resuelve `ai.embeddings` de `game_configs`, con respaldo en `settings`."""
    datos = dict(EMBEDDINGS_POR_DEFECTO)
    if cfg is not None:
        try:
            datos.update(cfg.obtener_json("ai.embeddings", EMBEDDINGS_POR_DEFECTO) or {})
        except Exception:  # noqa: BLE001 - sin configuración sembrada se usa el respaldo
            logger.debug("embeddings_config_ausente")
    # `EMBEDDINGS_PROVIDER` del entorno manda en desarrollo y pruebas: permite forzar
    # el proveedor sin tocar `game_configs`.
    proveedor = str(settings.embeddings_provider or datos.get("provider") or "mock")
    if proveedor == "mock":
        datos["provider"] = "mock"
    return AjustesEmbeddings(
        provider=str(datos.get("provider") or "mock"),
        model=str(datos.get("model") or EMBEDDINGS_POR_DEFECTO["model"]),
        dimensions=int(datos.get("dimensions") or settings.embeddings_dim),
        batch_size=max(1, int(datos.get("batch_size") or 128)),
    )


def obtener_proveedor(cfg: Any | None = None, *, forzar: str | None = None) -> ProveedorEmbeddings:
    """Devuelve el proveedor vigente; cae al `mock` si falta la clave del proveedor real."""
    ajustes = ajustes_de(cfg)
    nombre = (forzar or ajustes.provider or "mock").lower()

    if nombre == "voyage":
        clave = settings.voyage_api_key
        if not clave:
            logger.warning("embeddings_sin_api_key", provider="voyage")
            return ProveedorMock(dimensiones=ajustes.dimensions)
        return ProveedorVoyage(
            api_key=clave, modelo=ajustes.model, dimensiones=ajustes.dimensions
        )

    if nombre != "mock":
        logger.warning("embeddings_proveedor_desconocido", provider=nombre)
    return ProveedorMock(dimensiones=ajustes.dimensions)


def embeber_por_lotes(
    proveedor: ProveedorEmbeddings,
    textos: list[str],
    *,
    batch_size: int = 128,
    consulta: bool = False,
) -> list[list[float]]:
    """Embebe una lista larga en lotes del tamaño que admite el proveedor."""
    vectores: list[list[float]] = []
    for inicio in range(0, len(textos), max(1, batch_size)):
        vectores.extend(proveedor.embeber(textos[inicio : inicio + batch_size], consulta=consulta))
    return vectores


__all__ = [
    "EMBEDDINGS_POR_DEFECTO",
    "MODELO_MOCK",
    "URL_VOYAGE",
    "AjustesEmbeddings",
    "ProveedorEmbeddings",
    "ProveedorMock",
    "ProveedorVoyage",
    "ajustes_de",
    "embeber_por_lotes",
    "obtener_proveedor",
]
