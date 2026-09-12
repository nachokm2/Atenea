"""Recuperación híbrida con fusión RRF (CONTRACT.md §6.12).

El procedimiento del contrato, literal:

```
1. Vectorial:  ORDER BY embedding <=> query_embedding  (cosine), filtro por knowledge_base_id, top 20
2. Léxica:     ts_rank_cd(search_vector, query) con configuración 'spanish' y 'simple', top 20
3. Fusión RRF: score(f) = Σ_listas 1 / (60 + rango_en_la_lista)
4. Refuerzo:   + ai.retrieval.design_bonus (0.02) a los fragmentos asignados al tema en la Fase A
5. Selección:  top 10 para lección y pool de preguntas; top 6 para re-explicación
               descartando los que puntúen < 40 % del mejor
6. Vecindad:   si un fragmento es 'code' o 'table', se adjunta el anterior si no está ya incluido
```

Todos los números (`vector_top_k`, `lexical_top_k`, `rrf_k`, `design_bonus`,
`final_top_k`, `reexplain_top_k`, `min_score_ratio`) salen de `ai.retrieval` en
`game_configs`: aquí no hay literales de juego.

**Aislamiento obligatorio (§8.7)**: toda consulta filtra por `user_id`, y además por
`knowledge_base_id` cuando se indica. No existe forma de llamar a este módulo sin dueño.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import ChunkType
from app.models.ingestion import Document, DocumentChunk
from app.modules.ingestion.embeddings import (
    ProveedorEmbeddings,
    ajustes_de,
    obtener_proveedor,
)

logger = get_logger("atenea.ingestion.recuperacion")

#: Valores de respaldo de `ai.retrieval` (§5.8) si la configuración no está sembrada.
RECUPERACION_POR_DEFECTO: dict[str, Any] = {
    "vector_top_k": 20,
    "lexical_top_k": 20,
    "rrf_k": 60,
    "design_bonus": 0.02,
    "final_top_k": 10,
    "reexplain_top_k": 6,
    "min_score_ratio": 0.4,
}


@dataclass(slots=True)
class ParametrosRecuperacion:
    """Parámetros efectivos de `ai.retrieval`."""

    vector_top_k: int
    lexical_top_k: int
    rrf_k: int
    design_bonus: float
    final_top_k: int
    reexplain_top_k: int
    min_score_ratio: float


@dataclass(slots=True)
class FragmentoRecuperado:
    """Fragmento devuelto por la recuperación, con su procedencia para citarlo."""

    chunk: DocumentChunk
    score: float
    rank: int
    rango_vectorial: int | None = None
    rango_lexico: int | None = None
    #: `True` cuando entró solo por la regla de vecindad del paso 6.
    por_vecindad: bool = False
    document_title: str | None = None

    @property
    def procedencia(self) -> dict[str, Any]:
        """Datos de cita que la app muestra bajo el contenido generado."""
        return {
            "chunk_id": self.chunk.id,
            "document_id": self.chunk.document_id,
            "document_version_id": self.chunk.document_version_id,
            "document_title": self.document_title,
            "heading_path": list(self.chunk.heading_path or []),
            "page_start": self.chunk.page_start,
            "page_end": self.chunk.page_end,
            "retrieval_rank": self.rank,
        }


def parametros_de(cfg: Any | None = None) -> ParametrosRecuperacion:
    """Resuelve `ai.retrieval` de `game_configs`, con respaldo documentado."""
    datos = dict(RECUPERACION_POR_DEFECTO)
    if cfg is not None:
        try:
            datos.update(cfg.obtener_json("ai.retrieval", RECUPERACION_POR_DEFECTO) or {})
        except Exception:  # noqa: BLE001 - sin configuración sembrada se usa el respaldo
            logger.debug("recuperacion_config_ausente")
    return ParametrosRecuperacion(
        vector_top_k=max(1, int(datos["vector_top_k"])),
        lexical_top_k=max(1, int(datos["lexical_top_k"])),
        rrf_k=max(1, int(datos["rrf_k"])),
        design_bonus=float(datos["design_bonus"]),
        final_top_k=max(1, int(datos["final_top_k"])),
        reexplain_top_k=max(1, int(datos["reexplain_top_k"])),
        min_score_ratio=min(1.0, max(0.0, float(datos["min_score_ratio"]))),
    )


# ---------------------------------------------------------------------------
# Las dos listas
# ---------------------------------------------------------------------------


def _filtros_base(
    *,
    usuario_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None,
    document_ids: list[uuid.UUID] | None,
) -> list[Any]:
    """Cláusulas de aislamiento comunes a las dos ramas de la búsqueda."""
    filtros: list[Any] = [DocumentChunk.user_id == usuario_id]
    if knowledge_base_id is not None:
        filtros.append(DocumentChunk.knowledge_base_id == knowledge_base_id)
    if document_ids:
        filtros.append(DocumentChunk.document_id.in_(document_ids))
    return filtros


def buscar_vectorial(
    db: Session,
    vector: list[float],
    *,
    usuario_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None = None,
    document_ids: list[uuid.UUID] | None = None,
    limite: int = 20,
) -> list[uuid.UUID]:
    """Top-K por distancia coseno sobre el índice HNSW de `document_chunks.embedding`."""
    if not vector:
        return []
    consulta = (
        sa.select(DocumentChunk.id)
        .where(
            *_filtros_base(
                usuario_id=usuario_id,
                knowledge_base_id=knowledge_base_id,
                document_ids=document_ids,
            ),
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(vector))
        .limit(limite)
    )
    return list(db.execute(consulta).scalars().all())


def buscar_lexical(
    db: Session,
    texto: str,
    *,
    usuario_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None = None,
    document_ids: list[uuid.UUID] | None = None,
    limite: int = 20,
) -> list[uuid.UUID]:
    """Top-K por `ts_rank_cd` sobre el `tsvector` español, con respaldo en `simple`.

    `search_vector` es una columna generada con `to_tsvector('spanish', text)`. La
    consulta se construye con `websearch_to_tsquery('spanish', …)`, que entiende comillas
    y `-palabra`. Si la variante española no casa con nada (siglas, identificadores,
    palabras en inglés que el diccionario español no lematiza), se reintenta con la
    configuración `simple`, tal como pide §6.12.
    """
    texto = (texto or "").strip()
    if not texto:
        return []

    filtros = _filtros_base(
        usuario_id=usuario_id, knowledge_base_id=knowledge_base_id, document_ids=document_ids
    )

    for configuracion, constructor in (("spanish", "websearch_to_tsquery"), ("simple", "plainto_tsquery")):
        consulta_ts = getattr(sa.func, constructor)(configuracion, texto)
        rango = sa.func.ts_rank_cd(DocumentChunk.search_vector, consulta_ts)
        sentencia = (
            sa.select(DocumentChunk.id)
            .where(*filtros, DocumentChunk.search_vector.op("@@")(consulta_ts))
            .order_by(rango.desc(), DocumentChunk.chunk_index.asc())
            .limit(limite)
        )
        filas = list(db.execute(sentencia).scalars().all())
        if filas:
            return filas
    return []


# ---------------------------------------------------------------------------
# Fusión RRF
# ---------------------------------------------------------------------------


def fusionar_rrf(
    listas: list[list[uuid.UUID]],
    *,
    rrf_k: int,
    bonificados: set[uuid.UUID] | None = None,
    design_bonus: float = 0.0,
) -> list[tuple[uuid.UUID, float]]:
    """Fusión *Reciprocal Rank Fusion*: `score(f) = Σ 1 / (k + rango)` (§6.12, pasos 3 y 4).

    Las posiciones son 1-indexadas. El refuerzo de diseño se suma una sola vez por
    fragmento, no una vez por lista.
    """
    puntajes: dict[uuid.UUID, float] = {}
    for lista in listas:
        for posicion, identificador in enumerate(lista, start=1):
            puntajes[identificador] = puntajes.get(identificador, 0.0) + 1.0 / (rrf_k + posicion)
    if bonificados and design_bonus:
        for identificador in bonificados:
            if identificador in puntajes:
                puntajes[identificador] += design_bonus
    return sorted(puntajes.items(), key=lambda par: (-par[1], str(par[0])))


# ---------------------------------------------------------------------------
# Caso de uso completo
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ResultadoRecuperacion:
    """Salida de la recuperación híbrida, lista para el prompt y para la trazabilidad."""

    fragmentos: list[FragmentoRecuperado] = field(default_factory=list)
    consulta: str = ""
    total_vectorial: int = 0
    total_lexico: int = 0

    def __iter__(self):
        """Permite recorrer el resultado como si fuera la lista de fragmentos."""
        return iter(self.fragmentos)

    def __len__(self) -> int:
        """Número de fragmentos seleccionados."""
        return len(self.fragmentos)

    @property
    def ids(self) -> list[uuid.UUID]:
        """Identificadores de los fragmentos, en orden de relevancia."""
        return [fragmento.chunk.id for fragmento in self.fragmentos]


def recuperar(
    db: Session,
    consulta: str,
    *,
    usuario_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None = None,
    document_ids: list[uuid.UUID] | None = None,
    top_k: int | None = None,
    ids_de_diseno: set[uuid.UUID] | None = None,
    cfg: Any | None = None,
    proveedor: ProveedorEmbeddings | None = None,
    con_vecindad: bool = True,
) -> ResultadoRecuperacion:
    """Ejecuta los seis pasos de §6.12 y devuelve los fragmentos con su procedencia.

    `top_k` permite pedir `reexplain_top_k` en vez de `final_top_k`; si no se indica se
    usa el de la configuración. `ids_de_diseno` son los fragmentos que la Fase A del
    diseño de ruta asignó al tema: reciben `design_bonus`.
    """
    parametros = parametros_de(cfg)
    limite_final = top_k or parametros.final_top_k
    texto = (consulta or "").strip()
    if not texto:
        return ResultadoRecuperacion(consulta=texto)

    proveedor = proveedor or obtener_proveedor(cfg)
    ajustes = ajustes_de(cfg)
    try:
        vector = proveedor.embeber([texto], consulta=True)[0]
    except Exception as exc:  # noqa: BLE001 - la rama léxica debe seguir funcionando
        logger.warning("recuperacion_sin_vector", error=str(exc))
        vector = []

    if vector and len(vector) != ajustes.dimensions:
        logger.warning(
            "recuperacion_dimension_inesperada",
            esperada=ajustes.dimensions,
            recibida=len(vector),
        )
        vector = []

    lista_vectorial = buscar_vectorial(
        db,
        vector,
        usuario_id=usuario_id,
        knowledge_base_id=knowledge_base_id,
        document_ids=document_ids,
        limite=parametros.vector_top_k,
    )
    lista_lexica = buscar_lexical(
        db,
        texto,
        usuario_id=usuario_id,
        knowledge_base_id=knowledge_base_id,
        document_ids=document_ids,
        limite=parametros.lexical_top_k,
    )

    fusionados = fusionar_rrf(
        [lista for lista in (lista_vectorial, lista_lexica) if lista],
        rrf_k=parametros.rrf_k,
        bonificados=ids_de_diseno,
        design_bonus=parametros.design_bonus,
    )
    if not fusionados:
        return ResultadoRecuperacion(consulta=texto)

    # Paso 5: corte por proporción respecto al mejor y top-K final.
    mejor = fusionados[0][1]
    umbral = mejor * parametros.min_score_ratio
    seleccionados = [par for par in fusionados if par[1] >= umbral][:limite_final]

    filas = _cargar_fragmentos(db, [identificador for identificador, _ in seleccionados])
    puntaje_por_id = dict(seleccionados)

    resultado: list[FragmentoRecuperado] = []
    posicion_vectorial = {valor: indice + 1 for indice, valor in enumerate(lista_vectorial)}
    posicion_lexica = {valor: indice + 1 for indice, valor in enumerate(lista_lexica)}
    for rango, (identificador, _) in enumerate(seleccionados, start=1):
        fila = filas.get(identificador)
        if fila is None:  # pragma: no cover - el fragmento se borró entre consultas
            continue
        chunk, titulo = fila
        resultado.append(
            FragmentoRecuperado(
                chunk=chunk,
                score=puntaje_por_id[identificador],
                rank=rango,
                rango_vectorial=posicion_vectorial.get(identificador),
                rango_lexico=posicion_lexica.get(identificador),
                document_title=titulo,
            )
        )

    if con_vecindad:
        resultado = _adjuntar_vecinos(db, resultado)

    return ResultadoRecuperacion(
        fragmentos=resultado,
        consulta=texto,
        total_vectorial=len(lista_vectorial),
        total_lexico=len(lista_lexica),
    )


def _cargar_fragmentos(
    db: Session, ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[DocumentChunk, str | None]]:
    """Carga los fragmentos seleccionados junto al título de su documento."""
    if not ids:
        return {}
    filas = db.execute(
        sa.select(DocumentChunk, Document.title)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.id.in_(ids))
    ).all()
    return {chunk.id: (chunk, titulo) for chunk, titulo in filas}


def _adjuntar_vecinos(
    db: Session, fragmentos: list[FragmentoRecuperado]
) -> list[FragmentoRecuperado]:
    """Paso 6: un fragmento de código o tabla arrastra al anterior para dar contexto."""
    presentes = {fragmento.chunk.id for fragmento in fragmentos}
    añadidos: list[FragmentoRecuperado] = []
    for fragmento in fragmentos:
        if fragmento.chunk.chunk_type not in (ChunkType.CODE, ChunkType.TABLE):
            continue
        if fragmento.chunk.chunk_index == 0:
            continue
        anterior = db.execute(
            sa.select(DocumentChunk, Document.title)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.document_version_id == fragmento.chunk.document_version_id,
                DocumentChunk.chunk_index == fragmento.chunk.chunk_index - 1,
            )
        ).first()
        if anterior is None or anterior[0].id in presentes:
            continue
        presentes.add(anterior[0].id)
        añadidos.append(
            FragmentoRecuperado(
                chunk=anterior[0],
                score=fragmento.score,
                rank=fragmento.rank,
                por_vecindad=True,
                document_title=anterior[1],
            )
        )
    if not añadidos:
        return fragmentos
    completos = fragmentos + añadidos
    # El vecino se coloca justo antes del fragmento que lo arrastró y se renumera.
    ordenados = sorted(completos, key=lambda item: (item.rank, 0 if item.por_vecindad else 1))
    for posicion, fragmento in enumerate(ordenados, start=1):
        fragmento.rank = posicion
    return ordenados


__all__ = [
    "RECUPERACION_POR_DEFECTO",
    "FragmentoRecuperado",
    "ParametrosRecuperacion",
    "ResultadoRecuperacion",
    "buscar_lexical",
    "buscar_vectorial",
    "fusionar_rrf",
    "parametros_de",
    "recuperar",
]
