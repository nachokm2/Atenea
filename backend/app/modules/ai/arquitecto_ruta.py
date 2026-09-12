"""Fase A — del corpus al esquema de ruta (módulos, temas, objetivos y respaldo).

Esta fase es la que convierte el material del usuario en una **estructura navegable**:
módulos, temas, objetivos de aprendizaje y, para cada tema, los identificadores de los
fragmentos que lo respaldan. No genera todavía ninguna lección: eso es la Fase B
(`app.modules.ai.autor_leccion`), perezosa y cacheada.

Aquí viven además dos piezas que el resto de la capa de IA reutiliza:

- **La recuperación híbrida** (CONTRACT.md §6.12): vectorial + léxica fusionadas con
  RRF (`k = 60`), refuerzo de los fragmentos asignados al tema en la Fase A, descarte
  por `min_score_ratio` y vecindad para fragmentos de código y de tabla.
- **La detección de material insuficiente** y la **política de cobertura**
  (`coverage_policy`: `source_only`, `model_knowledge`, `request_more`).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError, NotFound
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.content import Assessment, KnowledgeArea, LearningPath, PathModule, Topic
from app.models.enums import (
    ContentStatus,
    CoverageLevel,
    CoveragePolicy,
    DocumentStatus,
    EventType,
    JobStatus,
    JobType,
    PathSourceMode,
    PathStatus,
    ProvenanceContentType,
    ProvenanceOrigin,
)
from app.models.ingestion import ContentProvenance, Document, DocumentChunk, DocumentVersion
from app.modules.ai import costos
from app.modules.ai.esquemas_salida import SalidaRuta, esquema_estricto, generar_validado
from app.modules.ai.proveedor import (
    TAREA_PATH_DESIGN,
    FragmentoContexto,
    ProveedorIA,
    SolicitudIA,
    modelo_para_tarea,
    plantilla_para_tarea,
)
from app.modules.gamification import eventos as bus
from app.modules.gamification.servicio_config import ServicioConfig

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


class MaterialInsuficiente(AteneaError):
    """422 · El material no da para construir una ruta (`ingestion.min_words_for_path`)."""

    code = "DOCUMENT_UNREADABLE"
    status_code = 422


# ---------------------------------------------------------------------------
# Recuperación híbrida (§6.12)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParametrosRecuperacion:
    """Parámetros de `ai.retrieval` (§5.8)."""

    vector_top_k: int = 20
    lexical_top_k: int = 20
    rrf_k: int = 60
    design_bonus: float = 0.02
    final_top_k: int = 10
    reexplain_top_k: int = 6
    min_score_ratio: float = 0.4


def parametros_recuperacion(cfg: ServicioConfig | None) -> ParametrosRecuperacion:
    """Lee `ai.retrieval`; sin configuración devuelve los valores del contrato."""
    if cfg is None:
        return ParametrosRecuperacion()
    crudo = cfg.obtener_json("ai.retrieval", {}) or {}
    base = ParametrosRecuperacion()
    return ParametrosRecuperacion(
        vector_top_k=int(crudo.get("vector_top_k", base.vector_top_k)),
        lexical_top_k=int(crudo.get("lexical_top_k", base.lexical_top_k)),
        rrf_k=int(crudo.get("rrf_k", base.rrf_k)),
        design_bonus=float(crudo.get("design_bonus", base.design_bonus)),
        final_top_k=int(crudo.get("final_top_k", base.final_top_k)),
        reexplain_top_k=int(crudo.get("reexplain_top_k", base.reexplain_top_k)),
        min_score_ratio=float(crudo.get("min_score_ratio", base.min_score_ratio)),
    )


def _fragmento_de(fila: DocumentChunk, titulo: str, rank: int, score: float) -> FragmentoContexto:
    """Traduce una fila de `document_chunks` al contexto que viaja al prompt."""
    encabezados = fila.heading_path if isinstance(fila.heading_path, list) else []
    return FragmentoContexto(
        chunk_id=fila.id,
        text=fila.text,
        document_id=fila.document_id,
        document_version_id=fila.document_version_id,
        document_title=titulo,
        heading_path=tuple(str(parte) for parte in encabezados),
        page_start=fila.page_start,
        page_end=fila.page_end,
        chunk_type=str(getattr(fila.chunk_type, "value", fila.chunk_type or "prose")),
        rank=rank,
        score=score,
    )


def _titulos_de_documentos(db: Session, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Mapa `document_id -> título`, para citar la fuente en el prompt y en la app."""
    limpios = [i for i in ids if i is not None]
    if not limpios:
        return {}
    filas = db.execute(
        sa.select(Document.id, Document.title).where(Document.id.in_(limpios))
    ).all()
    return {fila[0]: fila[1] for fila in filas}


def _busqueda_lexica(
    db: Session,
    *,
    knowledge_base_id: uuid.UUID,
    user_id: uuid.UUID | None,
    consulta: str,
    limite: int,
) -> list[tuple[uuid.UUID, float]]:
    """Búsqueda léxica con `ts_rank_cd` en español y en `simple` (§6.12, paso 2)."""
    texto = " ".join((consulta or "").split())
    if not texto:
        return []
    rank = sa.func.greatest(
        sa.func.ts_rank_cd(
            DocumentChunk.search_vector, sa.func.plainto_tsquery("spanish", texto)
        ),
        sa.func.ts_rank_cd(
            DocumentChunk.search_vector, sa.func.plainto_tsquery("simple", texto)
        ),
    ).label("rank")
    condiciones = [DocumentChunk.knowledge_base_id == knowledge_base_id]
    if user_id is not None:
        condiciones.append(DocumentChunk.user_id == user_id)
    consulta_sql = (
        sa.select(DocumentChunk.id, rank)
        .where(*condiciones, rank > 0)
        .order_by(rank.desc(), DocumentChunk.id)
        .limit(limite)
    )
    return [(fila[0], float(fila[1])) for fila in db.execute(consulta_sql).all()]


def _busqueda_vectorial(
    db: Session,
    *,
    knowledge_base_id: uuid.UUID,
    user_id: uuid.UUID | None,
    embedding: Sequence[float],
    limite: int,
) -> list[tuple[uuid.UUID, float]]:
    """Búsqueda vectorial por distancia coseno (§6.12, paso 1)."""
    distancia = DocumentChunk.embedding.cosine_distance(list(embedding)).label("distancia")
    condiciones = [
        DocumentChunk.knowledge_base_id == knowledge_base_id,
        DocumentChunk.embedding.is_not(None),
    ]
    if user_id is not None:
        condiciones.append(DocumentChunk.user_id == user_id)
    consulta_sql = (
        sa.select(DocumentChunk.id, distancia)
        .where(*condiciones)
        .order_by(distancia.asc(), DocumentChunk.id)
        .limit(limite)
    )
    return [(fila[0], 1.0 - float(fila[1])) for fila in db.execute(consulta_sql).all()]


def _todos_los_fragmentos(
    db: Session, *, knowledge_base_id: uuid.UUID, user_id: uuid.UUID | None, limite: int
) -> list[uuid.UUID]:
    """Respaldo cuando no hay consulta útil: los primeros fragmentos del corpus."""
    condiciones = [DocumentChunk.knowledge_base_id == knowledge_base_id]
    if user_id is not None:
        condiciones.append(DocumentChunk.user_id == user_id)
    filas = db.execute(
        sa.select(DocumentChunk.id)
        .where(*condiciones)
        .order_by(DocumentChunk.document_version_id, DocumentChunk.chunk_index)
        .limit(limite)
    ).all()
    return [fila[0] for fila in filas]


def recuperar(
    db: Session,
    cfg: ServicioConfig | None,
    *,
    knowledge_base_id: uuid.UUID | None,
    user_id: uuid.UUID | None = None,
    consulta: str = "",
    embedding: Sequence[float] | None = None,
    ids_preferidos: Collection[uuid.UUID] = (),
    top_k: int | None = None,
    incluir_vecinos: bool = True,
) -> list[FragmentoContexto]:
    """Recuperación híbrida del material del usuario (CONTRACT.md §6.12).

    1. Vectorial (si hay embedding de la consulta) y léxica, cada una con su tope.
    2. Fusión RRF con `k = 60`.
    3. Refuerzo `design_bonus` a los fragmentos ya asignados al tema en la Fase A.
    4. Selección del `top_k`, descartando los que puntúen por debajo del
       `min_score_ratio` del mejor.
    5. Vecindad: a un fragmento de código o de tabla se le adjunta el anterior.
    """
    if knowledge_base_id is None:
        return []
    parametros = parametros_recuperacion(cfg)
    objetivo = top_k or parametros.final_top_k
    preferidos = {i for i in ids_preferidos if i is not None}

    listas: list[list[tuple[uuid.UUID, float]]] = []
    if embedding is not None:
        listas.append(
            _busqueda_vectorial(
                db,
                knowledge_base_id=knowledge_base_id,
                user_id=user_id,
                embedding=embedding,
                limite=parametros.vector_top_k,
            )
        )
    listas.append(
        _busqueda_lexica(
            db,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            consulta=consulta,
            limite=parametros.lexical_top_k,
        )
    )

    puntajes: dict[uuid.UUID, float] = {}
    for lista in listas:
        for posicion, (chunk_id, _) in enumerate(lista, start=1):
            puntajes[chunk_id] = puntajes.get(chunk_id, 0.0) + 1.0 / (parametros.rrf_k + posicion)

    # Los fragmentos que el diseño asignó al tema entran siempre, con su refuerzo.
    for chunk_id in preferidos:
        puntajes[chunk_id] = puntajes.get(chunk_id, 0.0) + parametros.design_bonus

    if not puntajes:
        respaldo = _todos_los_fragmentos(
            db, knowledge_base_id=knowledge_base_id, user_id=user_id, limite=objetivo
        )
        puntajes = {chunk_id: 1.0 / (parametros.rrf_k + i) for i, chunk_id in enumerate(respaldo, 1)}

    ordenados = sorted(puntajes.items(), key=lambda par: (-par[1], str(par[0])))
    if ordenados:
        mejor = ordenados[0][1]
        minimo = mejor * parametros.min_score_ratio
        ordenados = [par for par in ordenados if par[1] >= minimo or par[0] in preferidos]
    seleccion = ordenados[:objetivo]

    filas = _cargar_chunks(db, [chunk_id for chunk_id, _ in seleccion])
    if incluir_vecinos:
        seleccion, filas = _adjuntar_vecinos(db, seleccion, filas)

    titulos = _titulos_de_documentos(db, {fila.document_id for fila in filas.values()})
    fragmentos: list[FragmentoContexto] = []
    for posicion, (chunk_id, puntaje) in enumerate(seleccion, start=1):
        fila = filas.get(chunk_id)
        if fila is None:
            continue
        fragmentos.append(
            _fragmento_de(fila, titulos.get(fila.document_id, ""), posicion, puntaje)
        )
    return fragmentos


def _cargar_chunks(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, DocumentChunk]:
    """Carga las filas de `document_chunks` de los identificadores dados."""
    if not ids:
        return {}
    filas = db.execute(sa.select(DocumentChunk).where(DocumentChunk.id.in_(list(ids)))).scalars()
    return {fila.id: fila for fila in filas}


def _adjuntar_vecinos(
    db: Session,
    seleccion: list[tuple[uuid.UUID, float]],
    filas: dict[uuid.UUID, DocumentChunk],
) -> tuple[list[tuple[uuid.UUID, float]], dict[uuid.UUID, DocumentChunk]]:
    """Paso 6 de §6.12: a un fragmento `code` o `table` se le adjunta el anterior."""
    presentes = {chunk_id for chunk_id, _ in seleccion}
    agregados: list[tuple[uuid.UUID, float]] = []
    for chunk_id, puntaje in seleccion:
        fila = filas.get(chunk_id)
        if fila is None:
            continue
        tipo = str(getattr(fila.chunk_type, "value", fila.chunk_type or ""))
        if tipo not in ("code", "table") or fila.chunk_index <= 0:
            continue
        anterior = db.execute(
            sa.select(DocumentChunk).where(
                DocumentChunk.document_version_id == fila.document_version_id,
                DocumentChunk.chunk_index == fila.chunk_index - 1,
            )
        ).scalar_one_or_none()
        if anterior is not None and anterior.id not in presentes:
            presentes.add(anterior.id)
            filas[anterior.id] = anterior
            agregados.append((anterior.id, puntaje * 0.99))
    if agregados:
        seleccion = sorted([*seleccion, *agregados], key=lambda par: (-par[1], str(par[0])))
    return seleccion, filas


# ---------------------------------------------------------------------------
# Material disponible y suficiencia
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InformeMaterial:
    """Foto del corpus que respalda una ruta."""

    document_version_ids: tuple[uuid.UUID, ...]
    words: int
    tokens: int
    chunks: int
    min_words: int

    @property
    def suficiente(self) -> bool:
        """`True` si el corpus llega al mínimo de `ingestion.min_words_for_path`."""
        return self.words >= self.min_words


def versiones_vigentes(db: Session, knowledge_base_id: uuid.UUID) -> list[DocumentVersion]:
    """Versiones vigentes y listas de los documentos activos de una biblioteca."""
    filas = db.execute(
        sa.select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Document.knowledge_base_id == knowledge_base_id,
            Document.deleted_at.is_(None),
            DocumentVersion.is_current.is_(True),
            DocumentVersion.status == DocumentStatus.READY,
        )
        .order_by(DocumentVersion.created_at)
    ).scalars()
    return list(filas)


def evaluar_material(
    db: Session, cfg: ServicioConfig | None, knowledge_base_id: uuid.UUID | None
) -> InformeMaterial:
    """Mide el corpus y decide si alcanza para diseñar una ruta."""
    minimo = int(cfg.obtener("ingestion.min_words_for_path", 300)) if cfg else 300
    if knowledge_base_id is None:
        return InformeMaterial((), 0, 0, 0, minimo)
    versiones = versiones_vigentes(db, knowledge_base_id)
    return InformeMaterial(
        document_version_ids=tuple(version.id for version in versiones),
        words=sum(int(version.word_count or 0) for version in versiones),
        tokens=sum(int(version.token_count or 0) for version in versiones),
        chunks=sum(int(version.chunk_count or 0) for version in versiones),
        min_words=minimo,
    )


def exigir_material(informe: InformeMaterial) -> None:
    """Lanza `MaterialInsuficiente` (422 `DOCUMENT_UNREADABLE`) si el corpus no da."""
    if informe.suficiente:
        return
    raise MaterialInsuficiente(
        "No pudimos leer el documento. Prueba con un archivo de texto real.",
        details={"min_words": informe.min_words, "words": informe.words},
    )


# ---------------------------------------------------------------------------
# Fase A
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ResultadoDiseno:
    """Salida de la Fase A."""

    learning_path_id: uuid.UUID
    modules: int = 0
    topics: int = 0
    coverage_notes: list[str] = field(default_factory=list)
    job_id: uuid.UUID | None = None
    desde_cache: bool = False
    llamadas_ia: int = 0
    coste_usd: Decimal = Decimal("0")

    def como_dict(self) -> dict[str, Any]:
        """Resumen serializable para `generation_jobs.result`."""
        return {
            "path_id": str(self.learning_path_id),
            "modules": self.modules,
            "topics": self.topics,
            "coverage_notes": self.coverage_notes,
            "from_cache": self.desde_cache,
            "ai_calls": self.llamadas_ia,
            "cost_usd": str(self.coste_usd),
        }


def _limites_de_contenido(cfg: ServicioConfig | None) -> dict[str, Any]:
    """Límites de `content.*` que el prompt debe respetar (§5.8)."""
    if cfg is None:
        return {
            "modules": {"min": 4, "max": 10},
            "topics": {"min": 2, "max": 6},
            "lesson_minutes": 9,
            "question_types": [],
        }
    modulos = cfg.obtener_json("content.path.modules", {"min": 4, "max": 10})
    temas = cfg.obtener_json("content.module.topics", {"min": 2, "max": 6})
    minutos = cfg.obtener_json("content.lesson.target_minutes", {"default": 9})
    tipos = cfg.obtener_lista("content.mvp_question_types", [])
    return {
        "modules": modulos,
        "topics": temas,
        "lesson_minutes": int(minutos.get("default", 9)),
        "question_types": [str(t) for t in tipos],
    }


def _tiene_estructura(db: Session, path_id: uuid.UUID) -> bool:
    """`True` si la ruta ya tiene módulos (la Fase A no se repite sin motivo)."""
    return bool(
        db.execute(
            sa.select(sa.func.count(PathModule.id)).where(PathModule.learning_path_id == path_id)
        ).scalar_one()
    )


def _instruccion_diseno(
    path: LearningPath, area: KnowledgeArea | None, limites: dict[str, Any], informe: InformeMaterial
) -> str:
    """Encargo concreto que acompaña al material en el mensaje de usuario."""
    modulos = limites["modules"]
    temas = limites["topics"]
    tipos = ", ".join(limites["question_types"]) or "los tipos del MVP"
    objetivo = (path.goal_text or "").strip() or "aprender el contenido de este material"
    return (
        "## Encargo\n"
        f"- Objetivo del estudiante: {objetivo}\n"
        f"- Conocimiento principal: {area.name if area else 'por determinar'}\n"
        f"- Nivel declarado: {path.declared_level.value}\n"
        f"- Idioma del contenido: {path.language}\n"
        f"- Módulos: entre {modulos.get('min', 4)} y {modulos.get('max', 10)}\n"
        f"- Temas por módulo: entre {temas.get('min', 2)} y {temas.get('max', 6)}\n"
        f"- Minutos estimados por tema: {limites['lesson_minutes']}\n"
        f"- Tipos de pregunta admitidos: {tipos}\n"
        f"- Palabras de material disponibles: {informe.words}\n"
        "\nDevuelve el esquema completo de la ruta en JSON."
    )


def _datos_diseno(
    path: LearningPath, area: KnowledgeArea | None, limites: dict[str, Any]
) -> dict[str, Any]:
    """Datos estructurados que el proveedor simulado usa para construir la salida."""
    return {
        "goal_text": path.goal_text or "",
        "declared_level": path.declared_level.value,
        "area_name": area.name if area else "",
        "language": path.language,
        "modules_min": int(limites["modules"].get("min", 4)),
        "modules_max": int(limites["modules"].get("max", 10)),
        "topics_min": int(limites["topics"].get("min", 2)),
        "topics_max": int(limites["topics"].get("max", 6)),
        "lesson_minutes": int(limites["lesson_minutes"]),
        "question_types": limites["question_types"],
    }


def _aplicar_politica(
    salida: SalidaRuta, disponibles: set[str], politica: CoveragePolicy
) -> tuple[SalidaRuta, list[str]]:
    """Aplica la política de cobertura y limpia los identificadores inventados.

    - Cualquier `source_chunk_ids` que no exista entre los fragmentos recuperados se
      descarta: la IA no puede respaldar nada con una cita que no le dimos.
    - Un tema sin respaldo pasa a `insufficient` y, según la política, se elimina
      (`source_only`), se conserva marcado (`model_knowledge`) o se conserva pidiendo
      más material (`request_more`).
    """
    notas: list[str] = list(salida.coverage_notes)
    modulos_finales = []
    for modulo in salida.modules:
        temas_finales = []
        for tema in modulo.topics:
            validos = [i for i in tema.source_chunk_ids if i in disponibles]
            tema.source_chunk_ids = validos
            if not validos:
                tema.coverage = CoverageLevel.INSUFFICIENT
            elif tema.coverage is CoverageLevel.INSUFFICIENT:
                tema.coverage = CoverageLevel.PARTIAL
            if tema.coverage is CoverageLevel.INSUFFICIENT:
                if politica is CoveragePolicy.SOURCE_ONLY:
                    notas.append(
                        f"«{tema.title}» se quitó de la ruta: tu material no lo cubre."
                    )
                    continue
                if politica is CoveragePolicy.REQUEST_MORE:
                    notas.append(
                        f"«{tema.title}» necesita más material: súbelo y lo regeneramos."
                    )
                else:
                    notas.append(
                        f"«{tema.title}» se completará con conocimiento del modelo: "
                        "tu material no lo cubre."
                    )
            temas_finales.append(tema)
        if not temas_finales:
            notas.append(f"El módulo «{modulo.title}» se quitó: ningún tema tenía respaldo.")
            continue
        for posicion, tema in enumerate(temas_finales, start=1):
            tema.position = posicion
        modulo.topics = temas_finales
        modulos_finales.append(modulo)
    for posicion, modulo in enumerate(modulos_finales, start=1):
        modulo.position = posicion
    salida.modules = modulos_finales
    # Sin duplicados y conservando el orden de aparición.
    salida.coverage_notes = list(dict.fromkeys(notas))
    return salida, salida.coverage_notes


def disenar_ruta(
    db: Session,
    cfg: ServicioConfig,
    proveedor: ProveedorIA,
    *,
    learning_path_id: uuid.UUID,
    usuario_id: uuid.UUID | None = None,
    forzar: bool = False,
    embedding_consulta: Sequence[float] | None = None,
) -> ResultadoDiseno:
    """Ejecuta la Fase A sobre una ruta ya creada y persiste su esquema.

    Idempotente por naturaleza: si la ruta ya tiene módulos y no se fuerza, no se llama
    al modelo y se devuelve el resultado cacheado.
    """
    path = db.get(LearningPath, learning_path_id)
    if path is None:
        raise NotFound("No encontramos esa ruta.")
    if usuario_id is not None and path.user_id not in (None, usuario_id):
        raise NotFound("No encontramos esa ruta.")

    if not forzar and _tiene_estructura(db, path.id):
        modulos = int(
            db.execute(
                sa.select(sa.func.count(PathModule.id)).where(
                    PathModule.learning_path_id == path.id
                )
            ).scalar_one()
        )
        temas = int(
            db.execute(
                sa.select(sa.func.count(Topic.id))
                .join(PathModule, PathModule.id == Topic.module_id)
                .where(PathModule.learning_path_id == path.id)
            ).scalar_one()
        )
        return ResultadoDiseno(
            learning_path_id=path.id,
            modules=modulos,
            topics=temas,
            coverage_notes=list(path.coverage_notes or []),
            desde_cache=True,
        )

    informe = evaluar_material(db, cfg, path.knowledge_base_id)
    if path.source_mode is not PathSourceMode.WITHOUT_SOURCE:
        exigir_material(informe)

    costos.verificar_cuota(db, cfg, usuario_id, costos.CUOTA_DISENOS_RUTA)
    costos.verificar_presupuesto(db, cfg)

    plantilla = plantilla_para_tarea(db, TAREA_PATH_DESIGN)
    job = costos.crear_job(
        db,
        job_type=JobType.PATH_DESIGN,
        usuario_id=usuario_id or path.user_id,
        target_type="path",
        target_id=path.id,
        learning_path_id=path.id,
        prompt_template_id=plantilla.id,
        payload={"goal_text": path.goal_text or "", "source_mode": path.source_mode.value},
        progress_label="Diseñando módulos",
    )
    path.status = PathStatus.GENERATING
    db.flush()

    area = db.get(KnowledgeArea, path.knowledge_area_id)
    limites = _limites_de_contenido(cfg)
    parametros = parametros_recuperacion(cfg)
    consulta = " ".join(
        parte for parte in [(path.goal_text or ""), (area.name if area else ""), path.title] if parte
    )
    fragmentos = recuperar(
        db,
        cfg,
        knowledge_base_id=path.knowledge_base_id,
        user_id=path.user_id,
        consulta=consulta,
        embedding=embedding_consulta,
        top_k=parametros.vector_top_k,
    )

    solicitud = SolicitudIA(
        tarea=TAREA_PATH_DESIGN,
        sistema=plantilla.body,
        instruccion=_instruccion_diseno(path, area, limites, informe),
        fragmentos=fragmentos,
        datos=_datos_diseno(path, area, limites),
        esquema=esquema_estricto(SalidaRuta),
        modelo=modelo_para_tarea(cfg, TAREA_PATH_DESIGN),
        max_tokens=16_000,
        plantilla_id=plantilla.id,
        semilla=str(path.id),
    )

    try:
        salida, respuesta = generar_validado(proveedor, solicitud, SalidaRuta)
    except AteneaError as error:
        costos.cerrar_job(db, job, estado=JobStatus.FAILED, error=str(error))
        path.status = PathStatus.FAILED
        db.flush()
        bus.crear_evento_dominio(
            db,
            usuario_id=usuario_id or path.user_id,
            tipo=EventType.GENERATION_FAILED,
            payload={
                "job_id": str(job.id),
                "job_type": JobType.PATH_DESIGN.value,
                "target_id": str(path.id),
                "reason": getattr(error, "code", "GENERATION_FAILED"),
            },
            idempotency_key=f"generation-failed:{job.id}",
            source_module="ai",
        )
        raise

    costos.registrar_uso(db, job, respuesta.uso)

    disponibles = {fragmento.etiqueta: fragmento for fragmento in fragmentos}
    salida, notas = _aplicar_politica(salida, set(disponibles), path.coverage_policy)

    modulos, temas = _persistir_esquema(
        db,
        cfg,
        path=path,
        salida=salida,
        fragmentos=disponibles,
        job_id=job.id,
        plantilla_id=plantilla.id,
        model_id=respuesta.uso.model_id,
    )

    path.summary = salida.summary or path.summary
    if not (path.title or "").strip():
        path.title = salida.title[:120]
    path.module_count = modulos
    path.estimated_minutes = sum(m.estimated_minutes for m in salida.modules) or None
    path.coverage_notes = notas
    path.generated_by_job_id = job.id
    path.status = PathStatus.PENDING_REVIEW
    db.flush()

    resultado = ResultadoDiseno(
        learning_path_id=path.id,
        modules=modulos,
        topics=temas,
        coverage_notes=notas,
        job_id=job.id,
        llamadas_ia=1 + respuesta.reintentos,
        coste_usd=respuesta.uso.cost_usd,
    )
    costos.cerrar_job(db, job, estado=JobStatus.SUCCEEDED, resultado=resultado.como_dict())

    bus.crear_evento_dominio(
        db,
        usuario_id=usuario_id or path.user_id,
        tipo=EventType.PATH_GENERATED,
        payload={
            "path_id": str(path.id),
            "modules": modulos,
            "topics": temas,
            "coverage_notes": notas,
            "job_id": str(job.id),
        },
        idempotency_key=f"path-generated:{path.id}:{job.id}",
        source_module="ai",
    )
    logger.info(
        "ai.fase_a",
        path_id=str(path.id),
        modules=modulos,
        topics=temas,
        cost_usd=str(respuesta.uso.cost_usd),
    )
    return resultado


def _persistir_esquema(
    db: Session,
    cfg: ServicioConfig,
    *,
    path: LearningPath,
    salida: SalidaRuta,
    fragmentos: dict[str, FragmentoContexto],
    job_id: uuid.UUID,
    plantilla_id: uuid.UUID | None,
    model_id: str,
) -> tuple[int, int]:
    """Escribe módulos, temas, evaluaciones y procedencia; devuelve (módulos, temas)."""
    total_temas = 0
    pass_score = Decimal(str(cfg.obtener("mastery.assessment.pass_score", 70)))
    n_preguntas = int(cfg.obtener("mastery.assessment.question_count", 10))
    ratio_banco = Decimal(str(cfg.obtener("mastery.assessment.bank_ratio", "2.5")))
    max_intentos = int(cfg.obtener("mastery.assessment.max_attempts_per_day", 2))

    anterior: PathModule | None = None
    for salida_modulo in salida.modules:
        modulo = PathModule(
            learning_path_id=path.id,
            position=salida_modulo.position,
            title=salida_modulo.title[:120],
            flavor_name=(salida_modulo.flavor_name or None),
            summary=salida_modulo.summary or None,
            difficulty=salida_modulo.difficulty,
            estimated_minutes=salida_modulo.estimated_minutes,
            content_status=ContentStatus.PENDING,
            prerequisite_module_id=anterior.id if anterior is not None else None,
            topic_count=len(salida_modulo.topics),
            generated_by_job_id=job_id,
        )
        db.add(modulo)
        db.flush()
        anterior = modulo

        for salida_tema in salida_modulo.topics:
            tema = Topic(
                module_id=modulo.id,
                position=salida_tema.position,
                title=salida_tema.title[:140],
                learning_objectives=list(salida_tema.learning_objectives),
                coverage=salida_tema.coverage,
                difficulty=salida_tema.difficulty,
                estimated_minutes=salida_tema.estimated_minutes,
                suggested_question_types=[t.value for t in salida_tema.suggested_question_types],
                source_chunk_ids=list(salida_tema.source_chunk_ids),
                content_status=ContentStatus.PENDING,
            )
            db.add(tema)
            db.flush()
            total_temas += 1
            registrar_procedencia(
                db,
                content_type=ProvenanceContentType.TOPIC,
                content_id=tema.id,
                fragmentos=[
                    fragmentos[i] for i in salida_tema.source_chunk_ids if i in fragmentos
                ],
                job_id=job_id,
                plantilla_id=plantilla_id,
                model_id=model_id,
                origen=(
                    ProvenanceOrigin.SOURCE
                    if salida_tema.source_chunk_ids
                    else ProvenanceOrigin.MODEL_KNOWLEDGE
                ),
            )

        db.add(
            Assessment(
                module_id=modulo.id,
                question_count=n_preguntas,
                pass_score=pass_score,
                bank_size=int(Decimal(n_preguntas) * ratio_banco),
                max_attempts_per_day=max_intentos,
                content_status=ContentStatus.PENDING,
            )
        )
        db.flush()
    return len(salida.modules), total_temas


def registrar_procedencia(
    db: Session,
    *,
    content_type: ProvenanceContentType,
    content_id: uuid.UUID,
    fragmentos: Sequence[FragmentoContexto],
    job_id: uuid.UUID | None,
    plantilla_id: uuid.UUID | None,
    model_id: str,
    origen: ProvenanceOrigin = ProvenanceOrigin.SOURCE,
    block_key: str | None = None,
) -> int:
    """Escribe la trazabilidad fina de una pieza generada (`content_provenance`).

    Sin fragmentos escribe **una** fila con `origin = model_knowledge`: la app necesita
    poder decir "esto lo escribió el modelo, no está en tu material".
    """
    if not fragmentos:
        db.add(
            ContentProvenance(
                content_type=content_type,
                content_id=content_id,
                block_key=block_key,
                origin=ProvenanceOrigin.MODEL_KNOWLEDGE,
                generation_job_id=job_id,
                prompt_template_id=plantilla_id,
                model_id=model_id or None,
                processed_at=utcnow(),
            )
        )
        db.flush()
        return 1
    for fragmento in fragmentos:
        db.add(
            ContentProvenance(
                content_type=content_type,
                content_id=content_id,
                block_key=block_key,
                chunk_id=fragmento.chunk_id,
                document_version_id=fragmento.document_version_id,
                document_id=fragmento.document_id,
                retrieval_rank=fragmento.rank or None,
                origin=origen,
                generation_job_id=job_id,
                prompt_template_id=plantilla_id,
                model_id=model_id or None,
                processed_at=utcnow(),
            )
        )
    db.flush()
    return len(fragmentos)


__all__ = [
    "InformeMaterial",
    "MaterialInsuficiente",
    "ParametrosRecuperacion",
    "ResultadoDiseno",
    "disenar_ruta",
    "evaluar_material",
    "exigir_material",
    "parametros_recuperacion",
    "recuperar",
    "registrar_procedencia",
    "versiones_vigentes",
]
