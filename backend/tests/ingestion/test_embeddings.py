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

from app.core.errors import ExternalServiceError, ValidationFailed
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


# ---------------------------------------------------------------------------
# Elección del proveedor
# ---------------------------------------------------------------------------
#
# El fallo que estas pruebas evitan no es que OpenAI no funcione: es que
# `EMBEDDINGS_PROVIDER=openai` devolvía el proveedor simulado **en silencio**,
# porque el nombre no estaba contemplado. El servidor habría escrito lecciones
# con citas tomadas de vectores de hash, sin que nada se pusiera en rojo.


def test_openai_devuelve_el_proveedor_de_openai(monkeypatch) -> None:
    """Con clave, `openai` tiene que dar el proveedor de OpenAI."""
    monkeypatch.setattr(embeddings.settings, "embeddings_provider", "openai")
    monkeypatch.setattr(embeddings.settings, "openai_api_key", "sk-de-mentira")

    proveedor = embeddings.obtener_proveedor()

    assert proveedor.nombre == "openai"
    assert proveedor.modelo == "text-embedding-3-small"
    assert proveedor.dimensiones == 512


def test_el_modelo_de_otro_proveedor_no_se_arrastra(monkeypatch) -> None:
    """`ai.embeddings.model` trae el de Voyage: OpenAI no puede usar ese nombre.

    Los nombres de modelo no son intercambiables entre proveedores. Pasarle
    `voyage-3-lite` a OpenAI daría un 400 en cada fragmento del material.
    """
    monkeypatch.setattr(embeddings.settings, "embeddings_provider", "openai")
    monkeypatch.setattr(embeddings.settings, "openai_api_key", "sk-de-mentira")

    proveedor = embeddings.obtener_proveedor(_ConfigConModelo("voyage-3-lite"))

    assert proveedor.modelo == "text-embedding-3-small"


def test_sin_clave_en_desarrollo_cae_al_simulado(monkeypatch) -> None:
    """En local se trabaja sin dar de alta ninguna cuenta."""
    monkeypatch.setattr(embeddings.settings, "embeddings_provider", "openai")
    monkeypatch.setattr(embeddings.settings, "openai_api_key", None)
    monkeypatch.setattr(embeddings.settings, "environment", "development")

    assert embeddings.obtener_proveedor().nombre == "mock"


def test_sin_clave_en_produccion_falla_en_vez_de_fingir(monkeypatch) -> None:
    """Vectores de hash en producción son peores que un error.

    La lección saldría igual de bonita, con sus citas, apoyada en fragmentos que
    no vienen al caso. Eso no se ve hasta que alguien lee con atención.
    """
    monkeypatch.setattr(embeddings.settings, "embeddings_provider", "openai")
    monkeypatch.setattr(embeddings.settings, "openai_api_key", None)
    monkeypatch.setattr(embeddings.settings, "environment", "production")

    with pytest.raises(ExternalServiceError):
        embeddings.obtener_proveedor()


def test_un_proveedor_desconocido_tampoco_finge_en_produccion(monkeypatch) -> None:
    """Un nombre mal escrito es un error de configuración, no una petición."""
    monkeypatch.setattr(embeddings.settings, "embeddings_provider", "voyaje")
    monkeypatch.setattr(embeddings.settings, "environment", "production")

    with pytest.raises(ExternalServiceError):
        embeddings.obtener_proveedor()


class _ConfigConModelo:
    """Configuración de juego mínima que solo declara el modelo."""

    def __init__(self, modelo: str) -> None:
        self._modelo = modelo

    def obtener_json(self, clave: str, por_defecto=None):
        return {"provider": "openai", "model": self._modelo, "dimensions": 512}


def test_la_peticion_a_openai_tiene_la_forma_que_espera_openai(monkeypatch) -> None:
    """Se comprueba el cuerpo y la cabecera sin gastar una llamada real.

    Un nombre de campo equivocado aquí no se ve hasta que alguien sube material
    en producción: la ingesta falla entera y el aprendiz se queda mirando la
    pantalla de generación.
    """
    import httpx

    capturado: dict = {}

    class _Respuesta:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {"index": 1, "embedding": [0.0] * 512},
                    {"index": 0, "embedding": [1.0] + [0.0] * 511},
                ]
            }

    def _post(url, **kwargs):
        capturado["url"] = url
        capturado.update(kwargs)
        return _Respuesta()

    monkeypatch.setattr(httpx, "post", _post)
    proveedor = embeddings.ProveedorOpenAI(api_key="sk-de-mentira")

    vectores = proveedor.embeber(["primero", "segundo"])

    assert capturado["url"] == "https://api.openai.com/v1/embeddings"
    assert capturado["headers"]["Authorization"] == "Bearer sk-de-mentira"
    assert capturado["json"] == {
        "input": ["primero", "segundo"],
        "model": "text-embedding-3-small",
        "dimensions": 512,
    }
    # La respuesta llega desordenada a propósito: se reordena por `index`, o
    # cada fragmento quedaría asociado al vector de otro.
    assert vectores[0][0] == 1.0
    assert vectores[1][0] == 0.0


def test_si_openai_devuelve_menos_vectores_que_textos_se_nota(monkeypatch) -> None:
    """Emparejar mal fragmentos y vectores es peor que fallar."""
    import httpx

    class _Respuesta:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"index": 0, "embedding": [0.0] * 512}]}

    def _post(_url, **_kwargs):
        return _Respuesta()

    monkeypatch.setattr(httpx, "post", _post)
    proveedor = embeddings.ProveedorOpenAI(api_key="sk-de-mentira")

    with pytest.raises(ExternalServiceError):
        proveedor.embeber(["uno", "dos", "tres"])
