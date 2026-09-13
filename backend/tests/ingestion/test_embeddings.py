"""Proveedor de embeddings intercambiable y almacenamiento privado (§5.8, §8.7, D14).

La prueba exigida por el contrato interno del módulo es la primera: **el proveedor
`mock` devuelve siempre el mismo vector para el mismo texto**. De ahí cuelga todo lo
demás: sin determinismo no se puede probar la recuperación híbrida en local, ni
reproducir un fallo, ni comparar dos ejecuciones del pipeline.
"""

from __future__ import annotations

import math
import subprocess
import sys

import pytest

from app.core.errors import ValidationFailed
from app.modules.ingestion import almacenamiento, embeddings

TEXTO = "Un LEFT JOIN conserva todas las filas de la tabla izquierda."


# ---------------------------------------------------------------------------
# Proveedor mock determinista
# ---------------------------------------------------------------------------


def test_el_mock_da_siempre_el_mismo_vector_para_el_mismo_texto() -> None:
    """Mismo texto, mismo vector: bit a bit, llamada tras llamada y entre instancias."""
    primero = embeddings.ProveedorMock(dimensiones=512)
    segundo = embeddings.ProveedorMock(dimensiones=512)

    uno = primero.embeber([TEXTO])[0]
    otro = primero.embeber([TEXTO])[0]
    tercero = segundo.embeber([TEXTO])[0]

    assert uno == otro
    assert uno == tercero
    assert len(uno) == 512


def test_el_mock_es_determinista_entre_procesos() -> None:
    """El determinismo sobrevive a un proceso nuevo: no depende del hash aleatorio de Python.

    `hash()` de Python está aleatorizado por proceso (`PYTHONHASHSEED`); el proveedor usa
    `blake2b`, que no lo está. Esta prueba lo demuestra arrancando otro intérprete.
    """
    guion = (
        "from app.modules.ingestion.embeddings import ProveedorMock;"
        f"print(ProveedorMock(dimensiones=512).embeber([{TEXTO!r}])[0][:8])"
    )
    salida = subprocess.run(
        [sys.executable, "-c", guion], capture_output=True, text=True, check=True
    ).stdout.strip()
    esperado = str(embeddings.ProveedorMock(dimensiones=512).embeber([TEXTO])[0][:8])
    assert salida == esperado


def test_el_vector_del_mock_esta_normalizado() -> None:
    """Norma 1: con `Vector(512)` y distancia coseno, el producto punto es el coseno (D14)."""
    vector = embeddings.ProveedorMock(dimensiones=512).embeber([TEXTO])[0]
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)


def test_textos_parecidos_quedan_mas_cerca_que_textos_ajenos() -> None:
    """La cercanía tiene sentido semántico mínimo: por eso sirve para probar el RAG."""
    proveedor = embeddings.ProveedorMock(dimensiones=512)
    consulta, vecino, ajeno = proveedor.embeber(
        [
            "LEFT JOIN filas izquierda",
            "Un LEFT JOIN conserva todas las filas de la tabla izquierda.",
            "La fotosintesis convierte la luz solar en energia quimica.",
        ]
    )
    coseno = lambda a, b: sum(x * y for x, y in zip(a, b, strict=True))  # noqa: E731
    assert coseno(consulta, vecino) > coseno(consulta, ajeno)


def test_texto_vacio_tambien_produce_un_vector_valido() -> None:
    """Un fragmento sin palabras no debe reventar el pipeline ni devolver `None`."""
    vector = embeddings.ProveedorMock(dimensiones=512).embeber([""])[0]
    assert len(vector) == 512
    assert any(vector)


def test_por_lotes_conserva_el_orden() -> None:
    """`embeber_por_lotes` devuelve un vector por texto, en el mismo orden."""
    proveedor = embeddings.ProveedorMock(dimensiones=512)
    textos = [f"fragmento numero {indice}" for indice in range(7)]
    vectores = embeddings.embeber_por_lotes(proveedor, textos, batch_size=3)
    assert len(vectores) == 7
    assert vectores[4] == proveedor.embeber([textos[4]])[0]


# ---------------------------------------------------------------------------
# Selección del proveedor
# ---------------------------------------------------------------------------


def test_ajustes_por_defecto_son_los_del_contrato() -> None:
    """Sin `game_configs` sembrado se usan los valores documentados de §5.8."""
    ajustes = embeddings.ajustes_de(None)
    assert ajustes.dimensions == 512
    assert ajustes.model == "voyage-3-lite"
    assert ajustes.batch_size == 128


def test_el_proveedor_por_defecto_es_el_mock_en_desarrollo() -> None:
    """`EMBEDDINGS_PROVIDER=mock` manda: ninguna prueba llama a la red ni gasta dinero."""
    proveedor = embeddings.obtener_proveedor(None)
    assert isinstance(proveedor, embeddings.ProveedorMock)
    assert proveedor.nombre == "mock"


def test_voyage_sin_api_key_cae_al_mock() -> None:
    """Pedir `voyage` sin credencial no puede tumbar la ingesta: se degrada al mock."""
    proveedor = embeddings.obtener_proveedor(None, forzar="voyage")
    assert isinstance(proveedor, embeddings.ProveedorMock)


def test_el_proveedor_real_declara_modelo_y_dimension() -> None:
    """`document_chunks.embedding_model` y `embedding_dim` permiten reindexar (D14)."""
    proveedor = embeddings.ProveedorVoyage(api_key="x", modelo="voyage-3-lite", dimensiones=512)
    assert proveedor.nombre == "voyage"
    assert proveedor.modelo == "voyage-3-lite"
    assert proveedor.dimensiones == 512


# ---------------------------------------------------------------------------
# Almacenamiento privado (§8.7)
# ---------------------------------------------------------------------------


def test_la_clave_de_almacen_es_opaca() -> None:
    """Ni el nombre original, ni el usuario, ni nada adivinable: solo un UUID4."""
    clave = almacenamiento.nueva_clave("pdf")
    assert clave.startswith("documents/")
    assert clave.endswith(".pdf")
    assert almacenamiento.nueva_clave("pdf") != clave


def test_guardar_y_leer_el_binario() -> None:
    """Escritura atómica y lectura por clave; el tamaño coincide."""
    clave = almacenamiento.nueva_clave("txt")
    datos = b"contenido del material"
    assert almacenamiento.guardar(clave, datos) == len(datos)
    assert almacenamiento.leer(clave) == datos
    assert almacenamiento.existe(clave) is True
    assert almacenamiento.tamano(clave) == len(datos)
    assert almacenamiento.borrar(clave) is True
    assert almacenamiento.existe(clave) is False


@pytest.mark.parametrize(
    "clave",
    ["../../../etc/passwd", "/etc/passwd", "C:/Windows/win.ini", "documents/../../fuera.txt", ""],
)
def test_una_clave_manipulada_nunca_sale_del_almacen(clave: str) -> None:
    """Escapes de directorio, rutas absolutas y unidades de Windows se rechazan."""
    with pytest.raises(ValidationFailed):
        almacenamiento.ruta_local(clave)


def test_los_hashes_son_sha256_estables() -> None:
    """`content_hash` deduplica subidas idénticas: mismo contenido, mismo hash."""
    assert almacenamiento.hash_bytes(b"abc") == almacenamiento.hash_bytes(b"abc")
    assert len(almacenamiento.hash_bytes(b"abc")) == 64
    assert almacenamiento.hash_texto("abc") == almacenamiento.hash_bytes(b"abc")
