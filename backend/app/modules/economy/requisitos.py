"""Evaluador declarativo de requisitos de desbloqueo (contrato §6.13).

Una sola implementación cubre los **tres usos** que exige el contrato:

1. **Otorgar**: `auto_grant = true` entrega el ítem con `INSERT … ON CONFLICT DO NOTHING`
   (por eso reevaluar es idempotente y un job nocturno puede corregir eventos perdidos).
2. **Gatear la compra**: la tienda pregunta si el usuario cumple antes de cobrar.
3. **Explicar**: cada condición devuelve `{met, current, target, label, cta}` para que la
   mochila muestre "Dominio de BigQuery: 62 / 80 %".

Semántica del DSL (`item_requirements`): el ítem está desbloqueado si **algún**
`group_index` tiene **todas** sus filas cumplidas (OR de ANDs, profundidad máxima 2).

Los datos que se leen pertenecen a otros módulos (`progress`, `gamification`,
`identity`, `content`), pero se consultan **como tablas de lectura**, nunca importando
sus servicios: la comunicación en tiempo de ejecución sigue siendo por eventos (§1.3).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.time import user_local_date, utcnow
from app.models.content import KnowledgeArea, LearningPath, PathModule, Topic
from app.models.economy import Item, ItemRequirement, UserItem
from app.models.enums import (
    EventType,
    ItemOrigin,
    KnowledgeAreaStatus,
    ProgressState,
    RequirementType,
    StreakKind,
)
from app.models.gamification import Achievement, Streak, UserAchievement
from app.models.identity import Character, User
from app.models.progress import (
    AssessmentAttempt,
    UserAreaProgress,
    UserLessonProgress,
    UserPathProgress,
)
from app.modules.economy.monedero import SOURCE_MODULE, recortar_clave, registrar_evento

logger = get_logger("atenea.economy")

# ---------------------------------------------------------------------------
# Familias de hechos (`items.requirement_facts`)
# ---------------------------------------------------------------------------

#: Familia de hechos que referencia cada tipo de condición del DSL.
FAMILIA_POR_REQUISITO: dict[RequirementType, str] = {
    RequirementType.PATH_COMPLETED: "path",
    RequirementType.MASTERY_GTE: "mastery",
    RequirementType.AREAS_MASTERED_GTE: "mastery",
    RequirementType.ASSESSMENT_SCORE_GTE: "assessment",
    RequirementType.STREAK_GTE: "streak",
    RequirementType.LEVEL_GTE: "level",
    RequirementType.ACHIEVEMENT_UNLOCKED: "achievement",
    RequirementType.LESSONS_COMPLETED_GTE: "lessons",
    RequirementType.WITHIN_WINDOW: "time",
}

#: Familias que despierta cada evento de dominio (§6.13, filtro de candidatos).
FAMILIAS_POR_EVENTO: dict[EventType, tuple[str, ...]] = {
    EventType.PATH_COMPLETED: ("path",),
    EventType.MASTERY_UPDATED: ("mastery",),
    EventType.AREA_MASTERED: ("mastery",),
    EventType.ASSESSMENT_COMPLETED: ("assessment",),
    EventType.STREAK_UPDATED: ("streak",),
    EventType.STREAK_MILESTONE_REACHED: ("streak",),
    EventType.LEVEL_UP: ("level",),
    EventType.ACHIEVEMENT_UNLOCKED: ("achievement",),
    EventType.LESSON_COMPLETED: ("lessons",),
}

#: Condiciones que acreditan **desempeño** (regla de integridad educativa de §6.13).
REQUISITOS_DE_DESEMPENO: frozenset[RequirementType] = frozenset(
    {
        RequirementType.PATH_COMPLETED,
        RequirementType.MASTERY_GTE,
        RequirementType.AREAS_MASTERED_GTE,
        RequirementType.ASSESSMENT_SCORE_GTE,
    }
)


# ---------------------------------------------------------------------------
# Resultados de la evaluación
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CondicionEvaluada:
    """Una condición del DSL ya evaluada, lista para mostrarse al usuario."""

    requirement_type: RequirementType
    met: bool
    current: float
    target: float
    label: str
    cta: str | None = None
    group_index: int = 0
    position: int = 0
    knowledge_area_id: uuid.UUID | None = None
    area_slug: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Forma serializable de la condición (modo `explain` del contrato)."""
        return {
            "type": self.requirement_type.value,
            "met": self.met,
            "current": self.current,
            "target": self.target,
            "label": self.label,
            "cta": self.cta,
            "group_index": self.group_index,
            "position": self.position,
            "knowledge_area_id": str(self.knowledge_area_id) if self.knowledge_area_id else None,
            "area_slug": self.area_slug,
        }


@dataclass(frozen=True)
class EvaluacionItem:
    """Resultado completo de evaluar un ítem para un usuario."""

    item_id: uuid.UUID
    item_code: str
    desbloqueado: bool
    sin_requisitos: bool
    condiciones: tuple[CondicionEvaluada, ...] = ()
    grupo_mas_cercano: int = 0

    @property
    def condiciones_visibles(self) -> tuple[CondicionEvaluada, ...]:
        """Condiciones del grupo más cercano a cumplirse (el que se explica en la UI)."""
        return tuple(c for c in self.condiciones if c.group_index == self.grupo_mas_cercano)

    @property
    def motivo(self) -> str | None:
        """Texto de desbloqueo (`unlock_reason`) construido con las etiquetas del grupo."""
        etiquetas = [c.label for c in self.condiciones_visibles if c.label]
        return " y ".join(etiquetas) if etiquetas else None

    def snapshot(self) -> dict[str, Any]:
        """Foto de los requisitos en el momento del otorgamiento (auditoría)."""
        return {"conditions": [c.as_dict() for c in self.condiciones_visibles]}


@dataclass
class Otorgamiento:
    """Ítem entregado (o ya poseído) tras evaluar los requisitos."""

    item: Item
    user_item: UserItem
    creado: bool
    motivo: str | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Hechos del usuario (se cargan una sola vez por evaluación)
# ---------------------------------------------------------------------------


class HechosUsuario:
    """Cache de los hechos del usuario que consultan las condiciones del DSL.

    Evita repetir la misma consulta por cada ítem candidato: una evaluación completa
    del catálogo hace un puñado de consultas, no una por condición.
    """

    def __init__(self, db: Session, usuario_id: uuid.UUID, *, ahora: dt.datetime | None = None):
        self.db = db
        self.usuario_id = usuario_id
        self.ahora = ahora or utcnow()

    # -- identidad y gamificación ------------------------------------------------

    @cached_property
    def personaje(self) -> Character | None:
        """Personaje del usuario (nivel y rango)."""
        return self.db.execute(
            sa.select(Character).where(Character.user_id == self.usuario_id)
        ).scalar_one_or_none()

    @cached_property
    def nivel(self) -> int:
        """Nivel global del personaje; 0 si aún no existe."""
        return int(self.personaje.level) if self.personaje is not None else 0

    @cached_property
    def racha(self) -> Streak | None:
        """Fila de racha del usuario."""
        return self.db.execute(
            sa.select(Streak).where(Streak.user_id == self.usuario_id)
        ).scalar_one_or_none()

    @cached_property
    def logros(self) -> set[str]:
        """Códigos de logro ya desbloqueados por el usuario."""
        filas = self.db.execute(
            sa.select(Achievement.code)
            .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
            .where(
                UserAchievement.user_id == self.usuario_id,
                UserAchievement.first_unlocked_at.is_not(None),
            )
        ).scalars()
        return {str(codigo) for codigo in filas}

    # -- dominio -----------------------------------------------------------------

    @cached_property
    def dominio_por_area(self) -> dict[uuid.UUID, Decimal]:
        """Dominio actual (0.00–100.00) por conocimiento."""
        filas = self.db.execute(
            sa.select(UserAreaProgress.knowledge_area_id, UserAreaProgress.mastery).where(
                UserAreaProgress.user_id == self.usuario_id
            )
        ).all()
        return {fila[0]: Decimal(fila[1] or 0) for fila in filas}

    @cached_property
    def areas_dominadas(self) -> int:
        """Cantidad de conocimientos en estado `mastered`."""
        return int(
            self.db.execute(
                sa.select(sa.func.count())
                .select_from(UserAreaProgress)
                .where(
                    UserAreaProgress.user_id == self.usuario_id,
                    UserAreaProgress.status == KnowledgeAreaStatus.MASTERED,
                )
            ).scalar_one()
        )

    # -- rutas, evaluaciones y lecciones ----------------------------------------

    def rutas_completadas(self, area_id: uuid.UUID | None) -> int:
        """Rutas con `user_path_progress.status = completed` (del área, si se indica)."""
        consulta = (
            sa.select(sa.func.count())
            .select_from(UserPathProgress)
            .join(LearningPath, LearningPath.id == UserPathProgress.learning_path_id)
            .where(
                UserPathProgress.user_id == self.usuario_id,
                UserPathProgress.status == ProgressState.COMPLETED,
            )
        )
        if area_id is not None:
            consulta = consulta.where(LearningPath.knowledge_area_id == area_id)
        return int(self.db.execute(consulta).scalar_one())

    def evaluaciones_sobre(self, umbral: Decimal, area_id: uuid.UUID | None) -> int:
        """Evaluaciones con `score >= umbral` (del área, si se indica)."""
        consulta = (
            sa.select(sa.func.count())
            .select_from(AssessmentAttempt)
            .where(
                AssessmentAttempt.user_id == self.usuario_id,
                AssessmentAttempt.score.is_not(None),
                AssessmentAttempt.score >= umbral,
            )
        )
        if area_id is not None:
            consulta = consulta.where(AssessmentAttempt.knowledge_area_id == area_id)
        return int(self.db.execute(consulta).scalar_one())

    def mejor_evaluacion(self, area_id: uuid.UUID | None) -> Decimal:
        """Mejor puntaje de evaluación obtenido (para explicar el progreso)."""
        consulta = sa.select(sa.func.max(AssessmentAttempt.score)).where(
            AssessmentAttempt.user_id == self.usuario_id
        )
        if area_id is not None:
            consulta = consulta.where(AssessmentAttempt.knowledge_area_id == area_id)
        return Decimal(self.db.execute(consulta).scalar() or 0)

    def lecciones_completadas(self, area_id: uuid.UUID | None) -> int:
        """Lecciones completadas por el usuario (del área, si se indica)."""
        consulta = (
            sa.select(sa.func.count())
            .select_from(UserLessonProgress)
            .where(
                UserLessonProgress.user_id == self.usuario_id,
                UserLessonProgress.status == ProgressState.COMPLETED,
            )
        )
        if area_id is not None:
            consulta = (
                consulta.join(Topic, Topic.id == UserLessonProgress.topic_id)
                .join(PathModule, PathModule.id == Topic.module_id)
                .join(LearningPath, LearningPath.id == PathModule.learning_path_id)
                .where(LearningPath.knowledge_area_id == area_id)
            )
        return int(self.db.execute(consulta).scalar_one())

    # -- áreas -------------------------------------------------------------------

    @cached_property
    def _areas_por_slug(self) -> dict[str, tuple[uuid.UUID, str]]:
        """Índice `slug -> (id, nombre)` de los conocimientos activos."""
        filas = self.db.execute(
            sa.select(KnowledgeArea.slug, KnowledgeArea.id, KnowledgeArea.name)
        ).all()
        return {str(fila[0]): (fila[1], str(fila[2])) for fila in filas}

    @cached_property
    def _areas_por_id(self) -> dict[uuid.UUID, str]:
        """Índice `id -> nombre` de los conocimientos."""
        filas = self.db.execute(sa.select(KnowledgeArea.id, KnowledgeArea.name)).all()
        return {fila[0]: str(fila[1]) for fila in filas}

    def resolver_area(
        self, requisito: ItemRequirement, item: Item
    ) -> tuple[uuid.UUID | None, str]:
        """Devuelve `(area_id, nombre)` de la condición.

        `area_slug = "self"` en una plantilla se resuelve con el área del ítem derivado.
        """
        if requisito.knowledge_area_id is not None:
            area_id = requisito.knowledge_area_id
            return area_id, self._areas_por_id.get(area_id, "tu conocimiento")
        slug = requisito.area_slug
        if slug == "self":
            area_id = item.knowledge_area_id
            if area_id is None:
                return None, "tu conocimiento"
            return area_id, self._areas_por_id.get(area_id, "tu conocimiento")
        if slug:
            encontrada = self._areas_por_slug.get(slug)
            if encontrada is not None:
                return encontrada[0], encontrada[1]
            return None, slug
        return None, "cualquier conocimiento"


# ---------------------------------------------------------------------------
# Evaluación de una condición
# ---------------------------------------------------------------------------


def _etiqueta(
    requisito: ItemRequirement,
    *,
    area: str,
    current: float,
    target: float,
    por_defecto: str,
) -> str:
    """Aplica `label_template` con los datos observados; si falla, usa el texto base."""
    plantilla = requisito.label_template
    if not plantilla:
        return por_defecto
    try:
        return plantilla.format(
            area=area,
            current=_bonito(current),
            target=_bonito(target),
            value=_bonito(target),
        )
    except (KeyError, IndexError, ValueError):
        return por_defecto


def _bonito(valor: float) -> str:
    """Formatea un número para el texto de la UI (sin decimales cuando es entero)."""
    if float(valor).is_integer():
        return str(int(valor))
    return f"{float(valor):.2f}"


def evaluar_condicion(
    hechos: HechosUsuario, item: Item, requisito: ItemRequirement
) -> CondicionEvaluada:
    """Evalúa una fila de `item_requirements` según la tabla de §6.13."""
    tipo = requisito.requirement_type
    area_id, area_nombre = hechos.resolver_area(requisito, item)
    objetivo_valor = float(requisito.target_value or 0)
    objetivo_cantidad = int(requisito.target_count or 0)

    if tipo is RequirementType.PATH_COMPLETED:
        objetivo = max(objetivo_cantidad, 1)
        actual = hechos.rutas_completadas(area_id)
        texto = f"Rutas completadas de {area_nombre}: {actual} / {objetivo}"

    elif tipo is RequirementType.MASTERY_GTE:
        objetivo = objetivo_valor
        if area_id is not None:
            actual = float(hechos.dominio_por_area.get(area_id, Decimal(0)))
        else:
            valores = hechos.dominio_por_area.values()
            actual = float(max(valores)) if valores else 0.0
        texto = f"Dominio de {area_nombre}: {_bonito(actual)} / {_bonito(objetivo)} %"

    elif tipo is RequirementType.AREAS_MASTERED_GTE:
        objetivo = max(objetivo_cantidad, 1)
        actual = hechos.areas_dominadas
        texto = f"Conocimientos dominados: {actual} / {objetivo}"

    elif tipo is RequirementType.ASSESSMENT_SCORE_GTE:
        objetivo = max(objetivo_cantidad, 1)
        actual = hechos.evaluaciones_sobre(Decimal(str(objetivo_valor)), area_id)
        mejor = float(hechos.mejor_evaluacion(area_id))
        texto = (
            f"Pruebas de {area_nombre} con {_bonito(objetivo_valor)} % o más: "
            f"{actual} / {objetivo} (tu mejor puntaje: {_bonito(mejor)} %)"
        )

    elif tipo is RequirementType.STREAK_GTE:
        objetivo = max(objetivo_cantidad, 1)
        racha = hechos.racha
        if racha is None:
            actual = 0
        elif requisito.streak_kind is StreakKind.BEST:
            actual = int(racha.best_length)
        else:
            actual = int(racha.current_length)
        texto = f"Racha: {actual} / {objetivo} días"

    elif tipo is RequirementType.LEVEL_GTE:
        objetivo = max(objetivo_cantidad, 1)
        actual = hechos.nivel
        texto = f"Nivel: {actual} / {objetivo}"

    elif tipo is RequirementType.ACHIEVEMENT_UNLOCKED:
        objetivo = 1
        codigo = requisito.achievement_code or ""
        actual = 1 if codigo in hechos.logros else 0
        texto = f"Logro necesario: {codigo}"

    elif tipo is RequirementType.LESSONS_COMPLETED_GTE:
        objetivo = max(objetivo_cantidad, 1)
        actual = hechos.lecciones_completadas(area_id)
        texto = f"Lecciones completadas de {area_nombre}: {actual} / {objetivo}"

    elif tipo is RequirementType.WITHIN_WINDOW:
        objetivo = 1
        desde = requisito.window_from
        hasta = requisito.window_to
        dentro = (desde is None or hechos.ahora >= desde) and (
            hasta is None or hechos.ahora <= hasta
        )
        actual = 1 if dentro else 0
        texto = "Disponible solo durante el evento"

    else:  # pragma: no cover - el enum está cerrado; defensa ante ampliaciones
        objetivo = 1
        actual = 0
        texto = "Requisito no reconocido"

    cumplido = float(actual) >= float(objetivo)
    return CondicionEvaluada(
        requirement_type=tipo,
        met=cumplido,
        current=float(actual),
        target=float(objetivo),
        label=_etiqueta(
            requisito,
            area=area_nombre,
            current=float(actual),
            target=float(objetivo),
            por_defecto=texto,
        ),
        cta=None if cumplido else "Sigue estudiando para desbloquearlo.",
        group_index=int(requisito.group_index),
        position=int(requisito.position),
        knowledge_area_id=area_id,
        area_slug=requisito.area_slug,
    )


# ---------------------------------------------------------------------------
# Evaluación de un ítem
# ---------------------------------------------------------------------------


def requisitos_de(db: Session, item_id: uuid.UUID) -> list[ItemRequirement]:
    """Filas del DSL normalizado de un ítem, ordenadas por grupo y posición."""
    return list(
        db.execute(
            sa.select(ItemRequirement)
            .where(ItemRequirement.item_id == item_id)
            .order_by(ItemRequirement.group_index, ItemRequirement.position)
        )
        .scalars()
        .all()
    )


def evaluar_item(
    db: Session,
    usuario_id: uuid.UUID,
    item: Item,
    *,
    hechos: HechosUsuario | None = None,
    requisitos: list[ItemRequirement] | None = None,
) -> EvaluacionItem:
    """Evalúa un ítem completo: OR de ANDs sobre `item_requirements`.

    Un ítem sin filas de requisito está **desbloqueado** por definición: su acceso lo
    gobierna la tienda (precio y nivel mínimo del listado).
    """
    contexto = hechos or HechosUsuario(db, usuario_id)
    filas = requisitos if requisitos is not None else requisitos_de(db, item.id)

    if not filas:
        return EvaluacionItem(
            item_id=item.id,
            item_code=item.code,
            desbloqueado=True,
            sin_requisitos=True,
        )

    evaluadas = tuple(evaluar_condicion(contexto, item, fila) for fila in filas)

    grupos: dict[int, list[CondicionEvaluada]] = {}
    for condicion in evaluadas:
        grupos.setdefault(condicion.group_index, []).append(condicion)

    desbloqueado = any(all(c.met for c in grupo) for grupo in grupos.values())

    # El grupo que se explica es el que menos condiciones le faltan (o el cumplido).
    def _faltantes(par: tuple[int, list[CondicionEvaluada]]) -> tuple[int, int]:
        return (sum(0 if c.met else 1 for c in par[1]), par[0])

    grupo_cercano = min(grupos.items(), key=_faltantes)[0]

    return EvaluacionItem(
        item_id=item.id,
        item_code=item.code,
        desbloqueado=desbloqueado,
        sin_requisitos=False,
        condiciones=evaluadas,
        grupo_mas_cercano=grupo_cercano,
    )


def explicar_requisitos(
    db: Session,
    usuario_id: uuid.UUID,
    item: Item,
    *,
    hechos: HechosUsuario | None = None,
) -> list[dict[str, Any]]:
    """Modo `explain`: lista `{met, current, target, label, cta}` para la ficha del ítem."""
    evaluacion = evaluar_item(db, usuario_id, item, hechos=hechos)
    return [condicion.as_dict() for condicion in evaluacion.condiciones_visibles]


def validar_integridad_educativa(
    item: Item, requisitos: list[ItemRequirement]
) -> bool:
    """Regla de §6.13: un ítem `origin = knowledge` exige una condición de desempeño.

    Tiempo de estudio y número de lecciones **no bastan**. La usa el validador de
    catálogo de las semillas y la tienda antes de entregar un ítem de conocimiento.
    """
    if item.origin is not ItemOrigin.KNOWLEDGE:
        return True
    return any(fila.requirement_type in REQUISITOS_DE_DESEMPENO for fila in requisitos)


# ---------------------------------------------------------------------------
# Otorgamiento
# ---------------------------------------------------------------------------


def otorgar_item(
    db: Session,
    usuario_id: uuid.UUID,
    item: Item,
    *,
    origin: ItemOrigin,
    source_ref: dict[str, Any] | None = None,
    unlock_reason: str | None = None,
    evento_disparador: uuid.UUID | None = None,
    momento: dt.datetime | None = None,
) -> Otorgamiento:
    """Entrega una instancia del ítem al usuario de forma **idempotente**.

    Usa `INSERT … ON CONFLICT DO NOTHING` sobre la única `(user_id, item_id)`: si el
    usuario ya lo tenía no pasa nada, no se emite `ITEM_ACQUIRED` y `creado` es `False`.
    """
    instante = momento or utcnow()
    referencia = dict(source_ref or {})

    sentencia = (
        pg_insert(UserItem.__table__)
        .values(
            id=uuid.uuid4(),
            user_id=usuario_id,
            item_id=item.id,
            acquired_at=instante,
            origin=origin,
            source_ref=referencia,
            is_new=True,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "item_id"])
        .returning(UserItem.__table__.c.id)
    )
    nuevo_id = db.execute(sentencia).scalar_one_or_none()

    if nuevo_id is None:
        existente = db.execute(
            sa.select(UserItem).where(
                UserItem.user_id == usuario_id, UserItem.item_id == item.id
            )
        ).scalar_one()
        return Otorgamiento(item=item, user_item=existente, creado=False)

    user_item = db.execute(
        sa.select(UserItem).where(UserItem.id == nuevo_id)
    ).scalar_one()

    usuario = db.get(User, usuario_id)
    if usuario is not None:
        total = int(
            db.execute(
                sa.select(sa.func.count())
                .select_from(UserItem)
                .where(UserItem.user_id == usuario_id, UserItem.revoked_at.is_(None))
            ).scalar_one()
        )
        registrar_evento(
            db,
            event_type=EventType.ITEM_ACQUIRED,
            usuario=usuario,
            payload={
                "user_item_id": str(user_item.id),
                "item_code": item.code,
                "slot": item.slot.value,
                "rarity": item.rarity.value,
                "origin": origin.value,
                "items_count": total,
                "knowledge_linked": item.origin is ItemOrigin.KNOWLEDGE,
                "unlock_reason": unlock_reason,
                "requirements_snapshot": referencia.get("requirements_snapshot"),
            },
            clave=recortar_clave(f"item-acquired:{usuario_id}:{item.id}:1"),
            local_date=user_local_date(instante, usuario.timezone),
            momento=instante,
        )

    return Otorgamiento(
        item=item,
        user_item=user_item,
        creado=True,
        motivo=unlock_reason,
        snapshot=dict(referencia.get("requirements_snapshot") or {}),
    )


# ---------------------------------------------------------------------------
# Punto de entrada público: reacción a un evento
# ---------------------------------------------------------------------------


def _familias_del_contexto(contexto: dict[str, Any] | None) -> tuple[str, ...]:
    """Familias de hechos que hay que revisar según el contexto recibido."""
    if not contexto:
        return ()
    if contexto.get("todos"):
        return ()
    familias = contexto.get("familias")
    if familias:
        return tuple(str(f) for f in familias)
    tipo = contexto.get("event_type")
    if tipo is None:
        return ()
    if not isinstance(tipo, EventType):
        try:
            tipo = EventType(str(tipo))
        except ValueError:
            return ()
    return FAMILIAS_POR_EVENTO.get(tipo, ())


def candidatos(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    familias: tuple[str, ...] = (),
    solo_auto: bool = True,
) -> list[Item]:
    """Ítems activos que este usuario aún no posee y que el evento podría desbloquear."""
    poseidos = sa.select(UserItem.item_id).where(UserItem.user_id == usuario_id)

    consulta = sa.select(Item).where(
        Item.is_active.is_(True),
        Item.is_template.is_(False),
        Item.id.not_in(poseidos),
        sa.or_(Item.owner_user_id.is_(None), Item.owner_user_id == usuario_id),
    )
    if solo_auto:
        consulta = consulta.where(Item.auto_grant.is_(True))
    if familias:
        consulta = consulta.where(
            sa.or_(
                *[
                    Item.requirement_facts.op("@>")(sa.literal([familia], JSONB))
                    for familia in familias
                ]
            )
        )
    return list(db.execute(consulta.order_by(Item.code)).scalars().all())


def evaluar_desbloqueos(
    db: Session,
    usuario_id: uuid.UUID,
    contexto: dict[str, Any] | None = None,
) -> list[Item]:
    """Evalúa los desbloqueos del usuario tras un evento y otorga lo que corresponda.

    `contexto` admite:

    - `event_type`: `EventType` (o su nombre) que disparó la reevaluación; filtra los
      candidatos por `items.requirement_facts` según §6.13.
    - `familias`: familias de hechos explícitas (`("mastery", "streak")`).
    - `todos`: `True` para revisar el catálogo completo (job nocturno de corrección).
    - `event_id`: evento disparador, que se guarda en `user_items.source_ref`.
    - `ahora`: instante de evaluación (pruebas y reproceso).

    Devuelve **solo los ítems recién otorgados**: llamarla dos veces con el mismo
    contexto devuelve `[]` la segunda vez (idempotencia por `(user_id, item_id)`).
    """
    ctx = contexto or {}
    ahora = ctx.get("ahora") or utcnow()
    familias = _familias_del_contexto(ctx)
    evento_id = ctx.get("event_id")
    if isinstance(evento_id, str):
        evento_id = uuid.UUID(evento_id)

    hechos = HechosUsuario(db, usuario_id, ahora=ahora)
    otorgados: list[Item] = []

    if _es_creacion_de_personaje(ctx.get("event_type")):
        otorgados.extend(_entregar_kit_inicial(db, usuario_id, evento_id, ahora))

    for item in candidatos(db, usuario_id, familias=familias, solo_auto=True):
        filas = requisitos_de(db, item.id)
        if not validar_integridad_educativa(item, filas):
            # Catálogo mal formado: un ítem de conocimiento sin prueba de desempeño
            # nunca se otorga automáticamente (regla de integridad educativa).
            continue
        evaluacion = evaluar_item(db, usuario_id, item, hechos=hechos, requisitos=filas)
        if not evaluacion.desbloqueado:
            continue
        resultado = otorgar_item(
            db,
            usuario_id,
            item,
            origin=item.origin,
            source_ref={
                "trigger_event_id": str(evento_id) if evento_id else None,
                "requirements_snapshot": evaluacion.snapshot(),
            },
            unlock_reason=evaluacion.motivo,
            evento_disparador=evento_id,
            momento=ahora,
        )
        if resultado.creado:
            otorgados.append(item)

    db.flush()
    return otorgados


def _es_creacion_de_personaje(tipo: Any) -> bool:
    """¿El evento que dispara la evaluación es `CHARACTER_CREATED`?"""
    if tipo is None:
        return False
    valor = getattr(tipo, "value", tipo)
    return str(valor) == EventType.CHARACTER_CREATED.value


def _entregar_kit_inicial(
    db: Session,
    usuario_id: uuid.UUID,
    evento_id: uuid.UUID | None,
    ahora: dt.datetime,
) -> list[Item]:
    """Entrega el equipo con el que empieza cada Orden (06c §3.2).

    El kit no se puede expresar con el DSL de desbloqueo, porque no existe un
    requisito de arquetipo: depende de la Orden que el aprendiz acaba de elegir,
    no de algo que haya logrado. Por eso se entrega aquí, desde el evento, en
    lugar de con `auto_grant`.

    Que pase por esta función y no por `identity` tiene una razón concreta: así
    los ítems entran en el `RewardsReceipt` de la creación y la app los celebra.
    Antes no los entregaba nadie y el personaje nacía sin nada que ponerse, con
    la tienda cerrada hasta el nivel 3 y cien monedas que no podía gastar.

    Es idempotente por `(user_id, item_id)`: repetir el evento no duplica nada.
    """
    from app.seeds.items import KITS_INICIALES  # noqa: PLC0415 - catálogo, no dominio

    personaje = db.execute(
        sa.select(Character).where(Character.user_id == usuario_id)
    ).scalar_one_or_none()
    if personaje is None:
        return []

    arquetipo = getattr(personaje.archetype, "value", personaje.archetype)
    codigos = KITS_INICIALES.get(str(arquetipo), ())
    if not codigos:
        return []

    items = list(
        db.execute(sa.select(Item).where(Item.code.in_(codigos))).scalars().all()
    )
    # Se respeta el orden del kit, no el que devuelva la base.
    por_codigo = {item.code: item for item in items}

    entregados: list[Item] = []
    for codigo in codigos:
        item = por_codigo.get(codigo)
        if item is None:
            logger.warning("economy.kit_inicial_sin_item", code=codigo)
            continue
        resultado = otorgar_item(
            db,
            usuario_id,
            item,
            origin=ItemOrigin.STARTER,
            source_ref={"trigger_event_id": str(evento_id) if evento_id else None},
            unlock_reason="Kit inicial de tu Orden",
            evento_disparador=evento_id,
            momento=ahora,
        )
        if resultado.creado:
            entregados.append(item)
    return entregados


__all__ = [
    "FAMILIAS_POR_EVENTO",
    "FAMILIA_POR_REQUISITO",
    "REQUISITOS_DE_DESEMPENO",
    "SOURCE_MODULE",
    "CondicionEvaluada",
    "EvaluacionItem",
    "HechosUsuario",
    "Otorgamiento",
    "candidatos",
    "evaluar_condicion",
    "evaluar_desbloqueos",
    "evaluar_item",
    "explicar_requisitos",
    "otorgar_item",
    "requisitos_de",
    "validar_integridad_educativa",
]
