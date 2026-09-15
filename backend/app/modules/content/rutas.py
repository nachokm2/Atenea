"""Ciclo de vida de una ruta de aprendizaje (§7.5).

Contrato §3.2 (`learning_paths`, `path_modules`, `topics`), §4.2 (`PATH_CREATED`,
`PATH_CONFIRMED`), §5.8 (`content.*`, `ai.quotas_per_day`) y §8.7 (aislamiento).

Reglas duras:

* **Ruta del Reino** = `learning_paths.user_id IS NULL` con `origin = SEED` (§5.9 D17).
  Adoptarla **no duplica contenido**: solo crea las filas `user_*_progress` del
  usuario. Es la razón de ser de la separación contenido/progreso.
* **Aislamiento** (§8.7): una ruta ajena responde `404`, nunca `403`.
* **Idempotencia** (§8.3): `POST /paths` no tiene columna propia para la clave, así
  que la idempotencia se ancla en `domain_events.idempotency_key`, que es única
  global. Reintentar con la misma clave devuelve la misma ruta y no crea otra.
* El **estado de generación y los documentos** los sirve `ingestion`: aquí solo se
  deja la ruta en `DRAFT`/`GENERATING` y se emite el evento que despierta esa fase.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError, NotFound
from app.core.time import utcnow
from app.models.content import KnowledgeArea, LearningPath, PathModule, Topic
from app.models.enums import (
    CoveragePolicy,
    DeclaredLevel,
    EventType,
    MissionStatus,
    PathOrigin,
    PathSourceMode,
    PathStatus,
    ProgressState,
)
from app.models.gamification import UserMission
from app.models.progress import UserPathProgress
from app.modules.gamification.eventos import buscar_por_clave, registrar_evento
from app.modules.progress.progreso import MapaRuta, ServicioProgreso

#: Ámbitos admitidos por `GET /paths?scope=` (§7.5).
AMBITOS: tuple[str, ...] = ("mine", "seed", "all")

#: Estados en los que la ruta todavía no tiene contenido navegable (§7.5 · P06).
ESTADOS_SIN_CONTENIDO: frozenset[PathStatus] = frozenset(
    {PathStatus.DRAFT, PathStatus.GENERATING, PathStatus.PENDING_REVIEW}
)


@dataclass(slots=True)
class FilaRuta:
    """Una ruta con el avance del usuario, para el listado de §7.5."""

    path: LearningPath
    knowledge_area: KnowledgeArea | None = None
    progress: UserPathProgress | None = None


@dataclass(slots=True)
class ResultadoCreacion:
    """Resultado de `POST /paths`: la ruta y si se creó ahora o ya existía."""

    path: LearningPath
    creada: bool


@dataclass(slots=True)
class CambioEsquema:
    """Una edición del esquema revisado en `POST /paths/{id}/confirm`."""

    topic_id: uuid.UUID
    title: str | None = None
    position: int | None = None
    remove: bool = False


@dataclass(slots=True)
class DetalleRuta:
    """Ruta + mapa de progreso, que es lo que devuelve `PathDetailOut`."""

    path: LearningPath
    knowledge_area: KnowledgeArea | None
    mapa: MapaRuta
    weak_topic_ids: list[uuid.UUID] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


def _es_del_reino(ruta: LearningPath) -> bool:
    """Una Ruta del Reino es la que no tiene dueño (§5.9 D17)."""
    return ruta.user_id is None


def obtener_ruta(db: Session, usuario_id: uuid.UUID, path_id: uuid.UUID) -> LearningPath:
    """Carga una ruta visible para el usuario; si no lo es, `404` (§8.7)."""
    ruta = db.get(LearningPath, path_id)
    if ruta is None:
        raise NotFound()
    if ruta.user_id == usuario_id:
        return ruta
    if _es_del_reino(ruta) and (ruta.is_public or ruta.origin == PathOrigin.SEED):
        return ruta
    raise NotFound()


def obtener_ruta_propia(db: Session, usuario_id: uuid.UUID, path_id: uuid.UUID) -> LearningPath:
    """Carga una ruta **del usuario**: las del Reino no se editan ni se borran."""
    ruta = obtener_ruta(db, usuario_id, path_id)
    if ruta.user_id != usuario_id:
        raise NotFound()
    return ruta


def listar_rutas(db: Session, usuario_id: uuid.UUID, *, scope: str = "all") -> list[FilaRuta]:
    """Mis rutas y/o las Rutas del Reino, con el avance del usuario (§7.5 · P22)."""
    if scope not in AMBITOS:
        raise AteneaError(
            "El ámbito debe ser mine, seed o all.",
            code="VALIDATION_ERROR",
            field_errors=[{"field": "scope", "message": "Valores admitidos: mine, seed, all."}],
        )

    condiciones = []
    if scope in ("mine", "all"):
        condiciones.append(LearningPath.user_id == usuario_id)
    if scope in ("seed", "all"):
        condiciones.append(
            sa.and_(LearningPath.user_id.is_(None), LearningPath.origin == PathOrigin.SEED)
        )

    filas = db.execute(
        sa.select(LearningPath, KnowledgeArea, UserPathProgress)
        .join(KnowledgeArea, KnowledgeArea.id == LearningPath.knowledge_area_id)
        .outerjoin(
            UserPathProgress,
            sa.and_(
                UserPathProgress.learning_path_id == LearningPath.id,
                UserPathProgress.user_id == usuario_id,
            ),
        )
        .where(sa.or_(*condiciones), LearningPath.archived_at.is_(None))
        .order_by(LearningPath.created_at.desc(), LearningPath.id)
    ).all()
    return [FilaRuta(path=ruta, knowledge_area=area, progress=avance) for ruta, area, avance in filas]


def detalle_ruta(db: Session, usuario_id: uuid.UUID, path_id: uuid.UUID) -> DetalleRuta:
    """Mapa de la ruta con el bloqueo de cada módulo (§7.5 · P07)."""
    ruta = obtener_ruta(db, usuario_id, path_id)
    servicio = ServicioProgreso(db)
    servicio.asegurar_progreso_ruta(usuario_id, ruta.id)
    mapa = servicio.estado_mapa_ruta(usuario_id, ruta.id)
    area = db.get(KnowledgeArea, ruta.knowledge_area_id)
    debiles = [
        tema.topic_id
        for modulo in mapa.modulos
        for tema in modulo.temas
        if tema.is_weak
    ]
    return DetalleRuta(path=ruta, knowledge_area=area, mapa=mapa, weak_topic_ids=debiles)


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------


def _area_para_ruta(
    db: Session, usuario_id: uuid.UUID, *, knowledge_area_id: uuid.UUID | None, pista: str | None
) -> KnowledgeArea:
    """Resuelve el conocimiento de la ruta: por id, por `slug` de la pista o creándolo.

    Cuando el usuario propone un conocimiento que no existe en la taxonomía canónica
    se crea uno suyo (`is_canonical = false`) y se emite `KNOWLEDGE_AREA_CREATED`,
    que es lo que materializa sus ítems derivados (§4.2).
    """
    if knowledge_area_id is not None:
        area = db.get(KnowledgeArea, knowledge_area_id)
        if area is None or not area.is_active:
            raise NotFound()
        return area

    etiqueta = (pista or "").strip()
    if not etiqueta:
        raise AteneaError(
            "Indica sobre qué conocimiento quieres aprender.",
            code="VALIDATION_ERROR",
            field_errors=[
                {"field": "knowledge_area_hint", "message": "El conocimiento no puede estar vacío."}
            ],
        )
    slug = "-".join(etiqueta.casefold().split())[:64]
    area = db.execute(
        sa.select(KnowledgeArea).where(KnowledgeArea.slug == slug)
    ).scalar_one_or_none()
    if area is not None:
        return area

    area = KnowledgeArea(
        slug=slug,
        name=etiqueta[:80],
        short_name=etiqueta[:18],
        is_canonical=False,
        created_by_user_id=usuario_id,
    )
    db.add(area)
    db.flush()
    registrar_evento(
        db,
        usuario_id=usuario_id,
        tipo=EventType.KNOWLEDGE_AREA_CREATED,
        payload={
            "knowledge_area_id": str(area.id),
            "slug": area.slug,
            "short_name": area.short_name,
            "category": area.category.value,
            "is_canonical": False,
        },
        idempotency_key=f"knowledge-area-created:{usuario_id}:{area.id}:1",
        source_module="content",
    )
    return area


def crear_ruta(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    idempotency_key: str,
    goal_text: str,
    declared_level: DeclaredLevel = DeclaredLevel.BEGINNER,
    source_mode: PathSourceMode = PathSourceMode.WITHOUT_SOURCE,
    knowledge_area_id: uuid.UUID | None = None,
    knowledge_area_hint: str | None = None,
    knowledge_base_id: uuid.UUID | None = None,
    coverage_policy: CoveragePolicy = CoveragePolicy.MODEL_KNOWLEDGE,
    title: str | None = None,
    momento: datetime | None = None,
) -> ResultadoCreacion:
    """Crea la ruta en `DRAFT` y emite `PATH_CREATED` (§7.5 · P05).

    No genera contenido: la Fase A la ejecuta el módulo `ai` a partir del evento.
    Es idempotente por `Idempotency-Key`: el reintento devuelve la misma ruta.
    """
    clave = f"path-create:{usuario_id}:{idempotency_key}"
    previo = buscar_por_clave(db, clave)
    if previo is not None:
        path_id = previo.payload.get("path_id")
        ruta_previa = db.get(LearningPath, uuid.UUID(str(path_id))) if path_id else None
        if ruta_previa is not None:
            return ResultadoCreacion(path=ruta_previa, creada=False)

    area = _area_para_ruta(
        db, usuario_id, knowledge_area_id=knowledge_area_id, pista=knowledge_area_hint
    )
    ruta = LearningPath(
        user_id=usuario_id,
        knowledge_area_id=area.id,
        title=(title or goal_text or area.name)[:120],
        goal_text=goal_text,
        declared_level=declared_level,
        source_mode=source_mode,
        origin=PathOrigin.USER,
        status=PathStatus.DRAFT,
        knowledge_base_id=knowledge_base_id,
        coverage_policy=coverage_policy,
    )
    db.add(ruta)
    db.flush()

    registrar_evento(
        db,
        usuario_id=usuario_id,
        tipo=EventType.PATH_CREATED,
        payload={
            "path_id": str(ruta.id),
            "knowledge_area_id": str(area.id),
            "source_mode": source_mode.value,
            "origin": PathOrigin.USER.value,
            "declared_level": declared_level.value,
        },
        idempotency_key=clave,
        occurred_at=momento,
        source_module="content",
    )
    ServicioProgreso(db).asegurar_progreso_ruta(usuario_id, ruta.id, ahora=momento)
    return ResultadoCreacion(path=ruta, creada=True)


def confirmar_ruta(
    db: Session,
    usuario_id: uuid.UUID,
    path_id: uuid.UUID,
    *,
    cambios: list[CambioEsquema] | None = None,
    coverage_policy: CoveragePolicy | None = None,
    momento: datetime | None = None,
) -> LearningPath:
    """Confirma el esquema revisado y deja la ruta lista para generar el módulo 1 (§7.5).

    Admite renombrar, reordenar y eliminar temas. Al confirmar, la ruta pasa a
    `GENERATING` y se emite `PATH_CONFIRMED`, que es lo que encola la Fase B en `ai`.
    """
    ruta = obtener_ruta_propia(db, usuario_id, path_id)
    instante = momento or utcnow()

    for cambio in cambios or []:
        tema = db.get(Topic, cambio.topic_id)
        if tema is None:
            raise NotFound()
        modulo = db.get(PathModule, tema.module_id)
        if modulo is None or modulo.learning_path_id != ruta.id:
            raise NotFound()
        if cambio.remove:
            db.delete(tema)
            continue
        if cambio.title is not None:
            tema.title = cambio.title[:140]
        if cambio.position is not None:
            tema.position = int(cambio.position)
    db.flush()

    if coverage_policy is not None:
        ruta.coverage_policy = coverage_policy
    ruta.confirmed_at = instante
    ruta.status = PathStatus.GENERATING
    ruta.module_count = int(
        db.execute(
            sa.select(sa.func.count(PathModule.id)).where(PathModule.learning_path_id == ruta.id)
        ).scalar_one()
    )
    db.flush()

    registrar_evento(
        db,
        usuario_id=usuario_id,
        tipo=EventType.PATH_CONFIRMED,
        payload={
            "path_id": str(ruta.id),
            "modules_kept": int(ruta.module_count),
            "coverage_policy": ruta.coverage_policy.value,
        },
        idempotency_key=f"path-confirm:{usuario_id}:{ruta.id}:1",
        occurred_at=instante,
        source_module="content",
    )
    ServicioProgreso(db).asegurar_progreso_ruta(usuario_id, ruta.id, ahora=instante)
    return ruta


def actualizar_ruta(
    db: Session,
    usuario_id: uuid.UUID,
    path_id: uuid.UUID,
    *,
    title: str | None = None,
    archived: bool | None = None,
    momento: datetime | None = None,
) -> LearningPath:
    """Renombra o archiva una ruta del usuario (§7.5 `PATCH /paths/{id}`)."""
    ruta = obtener_ruta_propia(db, usuario_id, path_id)
    instante = momento or utcnow()
    if title is not None:
        limpio = title.strip()
        if not limpio:
            raise AteneaError(
                "El título no puede estar vacío.",
                code="VALIDATION_ERROR",
                field_errors=[{"field": "title", "message": "El título no puede estar vacío."}],
            )
        ruta.title = limpio[:120]
    if archived is True:
        ruta.archived_at = instante
        ruta.status = PathStatus.ARCHIVED
        _cancelar_misiones_de_ruta(db, usuario_id, ruta.id, momento=instante)
    elif archived is False:
        ruta.archived_at = None
        if ruta.status == PathStatus.ARCHIVED:
            ruta.status = PathStatus.ACTIVE
    db.flush()
    return ruta


def _cancelar_misiones_de_ruta(
    db: Session, usuario_id: uuid.UUID, path_id: uuid.UUID, *, momento: datetime
) -> int:
    """Cancela las misiones de ruta activas al archivarla o borrarla (§7.5)."""
    filas = list(
        db.execute(
            sa.select(UserMission).where(
                UserMission.user_id == usuario_id,
                UserMission.learning_path_id == path_id,
                UserMission.status == MissionStatus.ACTIVE,
            )
        ).scalars()
    )
    for fila in filas:
        fila.status = MissionStatus.CANCELLED
        fila.expires_at = momento
    db.flush()
    return len(filas)


def eliminar_ruta(
    db: Session, usuario_id: uuid.UUID, path_id: uuid.UUID, *, momento: datetime | None = None
) -> None:
    """Elimina una ruta del usuario y cancela sus misiones de ruta (§7.5)."""
    ruta = obtener_ruta_propia(db, usuario_id, path_id)
    instante = momento or utcnow()
    _cancelar_misiones_de_ruta(db, usuario_id, ruta.id, momento=instante)
    db.delete(ruta)
    db.flush()


def adoptar_ruta(
    db: Session, usuario_id: uuid.UUID, path_id: uuid.UUID, *, momento: datetime | None = None
) -> DetalleRuta:
    """Adopta una Ruta del Reino: crea el progreso del usuario **sin duplicar contenido**.

    Es idempotente: adoptar dos veces la misma ruta deja el progreso como estaba.
    """
    ruta = obtener_ruta(db, usuario_id, path_id)
    if not _es_del_reino(ruta):
        raise AteneaError(
            "Esta ruta ya es tuya: no hace falta adoptarla.",
            code="UNAVAILABLE",
            details={"path_id": str(ruta.id)},
        )
    servicio = ServicioProgreso(db)
    servicio.asegurar_progreso_ruta(usuario_id, ruta.id, ahora=momento)

    # Adoptar también es empezar una Ruta, y el motor solo se entera por eventos.
    # Sin esto, el camino del día uno (que es adoptar la Ruta del Reino, no crear
    # una propia) no desbloqueaba el primer logro ni avanzaba ninguna misión: el
    # aprendiz hacía lo que la app le proponía y el juego no reaccionaba.
    #
    # La clave lleva la ruta y el usuario, así que adoptarla dos veces no paga dos
    # veces, que es justo lo que promete la idempotencia del §4.1.
    registrar_evento(
        db,
        usuario_id=usuario_id,
        tipo=EventType.PATH_CREATED,
        payload={
            "path_id": str(ruta.id),
            "knowledge_area_id": str(ruta.knowledge_area_id),
            "source_mode": ruta.source_mode.value if ruta.source_mode else None,
            "origin": PathOrigin.SEED.value,
            "declared_level": ruta.declared_level.value if ruta.declared_level else None,
            "adopted": True,
        },
        idempotency_key=f"path-adopt:{usuario_id}:{ruta.id}",
        occurred_at=momento,
        source_module="content",
    )
    return detalle_ruta(db, usuario_id, ruta.id)


def rutas_activas_del_usuario(db: Session, usuario_id: uuid.UUID) -> list[LearningPath]:
    """Rutas con progreso abierto: las que cuentan para la cuota `ai.quotas_per_day`."""
    return list(
        db.execute(
            sa.select(LearningPath)
            .join(UserPathProgress, UserPathProgress.learning_path_id == LearningPath.id)
            .where(
                UserPathProgress.user_id == usuario_id,
                UserPathProgress.status.in_(
                    [ProgressState.NOT_STARTED, ProgressState.IN_PROGRESS]
                ),
                LearningPath.archived_at.is_(None),
            )
            .order_by(UserPathProgress.last_activity_at.desc().nullslast())
        ).scalars()
    )


__all__ = [
    "AMBITOS",
    "ESTADOS_SIN_CONTENIDO",
    "CambioEsquema",
    "DetalleRuta",
    "FilaRuta",
    "ResultadoCreacion",
    "actualizar_ruta",
    "adoptar_ruta",
    "confirmar_ruta",
    "crear_ruta",
    "detalle_ruta",
    "eliminar_ruta",
    "listar_rutas",
    "obtener_ruta",
    "obtener_ruta_propia",
    "rutas_activas_del_usuario",
]
