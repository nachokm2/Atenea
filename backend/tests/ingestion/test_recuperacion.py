"""Recuperación híbrida con fusión RRF (§6.12) sobre un corpus pequeño y real.

La prueba exigida por el contrato interno del módulo es
`test_encuentra_el_fragmento_relevante_en_un_corpus_pequeno`: el corpus se ingiere con el
pipeline completo (trocear + embeber con el proveedor `mock`), se consulta como lo hará
el módulo `ai`, y el fragmento correcto tiene que salir el primero.

El resto cubre las seis reglas de §6.12 una a una, más el aislamiento por usuario de §8.7.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import ChunkType
from app.models.identity import User
from app.models.ingestion import Document, DocumentChunk, DocumentVersion, KnowledgeBase
from app.modules.ingestion import embeddings, recuperacion, servicio
from tests.ingestion.conftest import ConfigDePruebas

# ---------------------------------------------------------------------------
# Corpus de pruebas
# ---------------------------------------------------------------------------

SQL = (
    "# Manual de SQL\n\n## LEFT JOIN\n\n"
    "Un LEFT JOIN devuelve todas las filas de la tabla izquierda y las coincidencias "
    "de la tabla derecha. Cuando no existe coincidencia en la tabla derecha, las "
    "columnas de esa tabla se rellenan con NULL en el resultado de la consulta.\n\n"
    + " ".join(
        f"La consulta {indice} combina la tabla clientes con la tabla pedidos mediante "
        "un LEFT JOIN para conservar los clientes sin pedidos."
        for indice in range(14)
    )
)

BOTANICA = (
    "# Botánica\n\n## Fotosíntesis\n\n"
    "La fotosíntesis convierte la luz solar en energía química dentro de los "
    "cloroplastos. La clorofila absorbe la luz y la planta produce glucosa y oxígeno.\n\n"
    + " ".join(
        f"El proceso {indice} ocurre en la hoja, donde la clorofila capta fotones y "
        "libera oxígeno hacia la atmósfera terrestre."
        for indice in range(26)
    )
)

HISTORIA = (
    "# Historia\n\n## Roma\n\n"
    "El imperio romano organizó sus legiones en cohortes y centurias durante siglos.\n\n"
    + " ".join(
        f"La campaña {indice} del ejército romano amplió las fronteras del imperio "
        "hacia las provincias del norte."
        for indice in range(26)
    )
)


def _ingerir(db: Session, usuario: User, cfg: Any, titulo: str, texto: str) -> DocumentVersion:
    """Sube un material pegado y lo procesa entero (trocear + embeber)."""
    subida = servicio.pegar_texto(
        db,
        usuario_id=usuario.id,
        titulo=titulo,
        texto=texto,
        idempotency_key=str(uuid.uuid4()),
        cfg=cfg,
    )
    servicio.procesar_version(db, subida.version, cfg=cfg)
    return subida.version


# ---------------------------------------------------------------------------
# Fusión RRF (§6.12, pasos 3 y 4) — sin base de datos
# ---------------------------------------------------------------------------


def test_rrf_aplica_la_formula_del_contrato() -> None:
    """`score(f) = Σ_listas 1 / (60 + rango)`, con rangos 1-indexados."""
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fusion = dict(recuperacion.fusionar_rrf([[a, b], [b, c]], rrf_k=60))

    assert fusion[a] == 1 / 61
    assert fusion[b] == 1 / 62 + 1 / 61
    assert fusion[c] == 1 / 62
    # El que aparece en las dos listas gana.
    assert max(fusion, key=lambda clave: fusion[clave]) == b


def test_el_refuerzo_de_diseno_se_suma_una_sola_vez() -> None:
    """Paso 4: `design_bonus` premia al fragmento asignado al tema en la Fase A."""
    a, b = uuid.uuid4(), uuid.uuid4()
    fusion = dict(
        recuperacion.fusionar_rrf(
            [[a, b], [a, b]], rrf_k=60, bonificados={a}, design_bonus=0.02
        )
    )
    assert fusion[a] == 2 * (1 / 61) + 0.02
    assert fusion[b] == 2 * (1 / 62)


def test_los_parametros_por_defecto_son_los_del_contrato() -> None:
    """Sin `game_configs` sembrado se usan los valores de `ai.retrieval` de §5.8."""
    parametros = recuperacion.parametros_de(None)
    assert parametros.vector_top_k == 20
    assert parametros.lexical_top_k == 20
    assert parametros.rrf_k == 60
    assert parametros.final_top_k == 10
    assert parametros.reexplain_top_k == 6
    assert parametros.min_score_ratio == 0.4


# ---------------------------------------------------------------------------
# LA prueba del contrato: recuperación híbrida sobre un corpus pequeño
# ---------------------------------------------------------------------------


def test_encuentra_el_fragmento_relevante_en_un_corpus_pequeno(
    db: Session, usuario: User, cfg: Any
) -> None:
    """Tres materiales distintos; la consulta de SQL recupera el fragmento de SQL."""
    version_sql = _ingerir(db, usuario, cfg, "Manual de SQL", SQL)
    _ingerir(db, usuario, cfg, "Botánica", BOTANICA)
    _ingerir(db, usuario, cfg, "Historia", HISTORIA)

    resultado = recuperacion.recuperar(
        db,
        "¿Qué devuelve un LEFT JOIN con las filas de la tabla izquierda?",
        usuario_id=usuario.id,
        cfg=cfg,
    )

    assert len(resultado) > 0
    mejor = resultado.fragmentos[0]
    assert mejor.chunk.document_version_id == version_sql.id
    assert "LEFT JOIN" in mejor.chunk.text
    assert mejor.rank == 1
    assert mejor.score > 0
    # Entró por las dos ramas: es una recuperación híbrida de verdad.
    assert mejor.rango_vectorial is not None
    assert mejor.rango_lexico is not None
    assert resultado.total_vectorial > 0
    assert resultado.total_lexico > 0


def test_la_procedencia_permite_citar_la_fuente(db: Session, usuario: User, cfg: Any) -> None:
    """Cada fragmento recuperado sabe de qué documento y qué sección viene (§3.3)."""
    _ingerir(db, usuario, cfg, "Manual de SQL", SQL)
    resultado = recuperacion.recuperar(
        db, "LEFT JOIN tabla izquierda NULL", usuario_id=usuario.id, cfg=cfg
    )
    procedencia = resultado.fragmentos[0].procedencia
    assert procedencia["document_title"] == "Manual de SQL"
    assert procedencia["retrieval_rank"] == 1
    assert procedencia["chunk_id"] == resultado.fragmentos[0].chunk.id
    assert "Manual de SQL" in procedencia["heading_path"]


def test_una_consulta_de_otro_tema_no_devuelve_el_fragmento_de_sql(
    db: Session, usuario: User, cfg: Any
) -> None:
    """La recuperación discrimina: preguntar por fotosíntesis no trae la sección de JOINs."""
    _ingerir(db, usuario, cfg, "Manual de SQL", SQL)
    _ingerir(db, usuario, cfg, "Botánica", BOTANICA)

    resultado = recuperacion.recuperar(
        db, "¿Cómo convierte la clorofila la luz solar en energía química?",
        usuario_id=usuario.id,
        cfg=cfg,
    )
    assert len(resultado) > 0
    assert "clorofila" in resultado.fragmentos[0].chunk.text.lower()


def test_una_consulta_vacia_no_toca_la_base(db: Session, usuario: User, cfg: Any) -> None:
    """Sin consulta no hay recuperación: se devuelve el resultado vacío, no un error."""
    resultado = recuperacion.recuperar(db, "   ", usuario_id=usuario.id, cfg=cfg)
    assert len(resultado) == 0
    assert resultado.fragmentos == []


# ---------------------------------------------------------------------------
# Aislamiento y filtros (§8.7)
# ---------------------------------------------------------------------------


def test_nunca_se_recupera_material_de_otro_usuario(
    db: Session, usuario: User, cfg: Any
) -> None:
    """El aislamiento por `user_id` es obligatorio en **toda** consulta (§8.7)."""
    otro = User(email=f"otro-{uuid.uuid4().hex[:8]}@atenea.test", timezone="America/Santiago")
    db.add(otro)
    db.flush()
    _ingerir(db, otro, cfg, "Manual de SQL ajeno", SQL)

    mio = recuperacion.recuperar(
        db, "LEFT JOIN tabla izquierda", usuario_id=usuario.id, cfg=cfg
    )
    suyo = recuperacion.recuperar(db, "LEFT JOIN tabla izquierda", usuario_id=otro.id, cfg=cfg)

    assert len(mio) == 0
    assert len(suyo) > 0


def test_el_filtro_por_biblioteca_acota_el_corpus(
    db: Session, usuario: User, cfg: Any
) -> None:
    """La recuperación de una ruta solo mira la biblioteca de esa ruta."""
    _ingerir(db, usuario, cfg, "Manual de SQL", SQL)
    otra = KnowledgeBase(user_id=usuario.id, name="Otra biblioteca", is_default=False)
    db.add(otra)
    db.flush()

    vacio = recuperacion.recuperar(
        db,
        "LEFT JOIN tabla izquierda",
        usuario_id=usuario.id,
        knowledge_base_id=otra.id,
        cfg=cfg,
    )
    assert len(vacio) == 0


# ---------------------------------------------------------------------------
# Paso 6: vecindad de código y tablas
# ---------------------------------------------------------------------------


def test_un_fragmento_de_codigo_arrastra_al_anterior(
    db: Session,
    usuario: User,
    cfg: Any,
    configuracion: dict[str, Any],
    biblioteca: KnowledgeBase,
) -> None:
    """§6.12 paso 6: el código sin su párrafo introductorio se entiende a medias."""
    documento = Document(
        knowledge_base_id=biblioteca.id,
        user_id=usuario.id,
        title="Recetario SQL",
        document_type=servicio.DocumentType.MARKDOWN,
        version_count=1,
    )
    db.add(documento)
    db.flush()
    version = DocumentVersion(
        document_id=documento.id,
        version_number=1,
        content_hash="a" * 64,
        storage_key="documents/aa/aaaa.md",
        byte_size=1,
        chunk_count=2,
    )
    db.add(version)
    db.flush()

    proveedor = embeddings.ProveedorMock(dimensiones=512)
    textos = [
        "Antes de agrupar conviene entender la cláusula de ventana y su marco.",
        "SELECT id, SUM(total) OVER (PARTITION BY cliente) FROM ventas_ventana;",
    ]
    vectores = proveedor.embeber(textos)
    for indice, (texto, vector) in enumerate(zip(textos, vectores, strict=True)):
        db.add(
            DocumentChunk(
                document_version_id=version.id,
                document_id=documento.id,
                knowledge_base_id=biblioteca.id,
                user_id=usuario.id,
                chunk_index=indice,
                chunk_type=ChunkType.PROSE if indice == 0 else ChunkType.CODE,
                heading_path=["Recetario SQL"],
                text=texto,
                token_count=20,
                content_hash=f"{indice:064d}",
                embedding=vector,
                embedding_model=proveedor.modelo,
                embedding_dim=512,
                language="es",
            )
        )
    db.flush()

    # Con `final_top_k = 1` solo cabe el fragmento de código: si el anterior aparece,
    # es porque lo ha arrastrado la regla de vecindad y no la fusión.
    estrecho = ConfigDePruebas(
        {**configuracion, "ai.retrieval": {**configuracion["ai.retrieval"], "final_top_k": 1}}
    )
    resultado = recuperacion.recuperar(
        db, "ventas_ventana PARTITION BY cliente", usuario_id=usuario.id, cfg=estrecho
    )
    indices = [fragmento.chunk.chunk_index for fragmento in resultado.fragmentos]
    assert 1 in indices, "el fragmento de código se recupera"
    assert 0 in indices, "y arrastra al anterior para dar contexto"
    vecino = next(f for f in resultado.fragmentos if f.chunk.chunk_index == 0)
    assert vecino.por_vecindad is True
    # El vecino se coloca justo antes del fragmento que lo arrastró.
    assert indices.index(0) < indices.index(1)
