"""Comando de siembra: `python -m app.seeds.ejecutar`.

Es **idempotente por construcción**: ejecutarlo dos veces deja exactamente el mismo
número de filas y los mismos identificadores. Dos mecanismos lo garantizan:

1. Las tablas con clave natural (`game_configs.key`, `knowledge_areas.slug`,
   `items.code`, `achievements.code`, `mission_templates.code`, `level_definitions`
   por `(scope, level)`) se buscan por esa clave y se **actualizan** en su sitio.
2. Las tablas de contenido, que no tienen clave natural, reciben identificadores
   deterministas con `app.seeds.id_semilla` (`uuid5` sobre un código estable), de modo
   que la segunda pasada encuentra la fila y la actualiza en lugar de crear otra.

`game_configs` es el único caso especial: es una tabla **versionada**. Si el valor de
una clave no ha cambiado, no se toca nada; si ha cambiado, se cierra la fila vigente
con `valid_to = now()` y se abre una versión nueva con un `config_version` recién
tomado de la secuencia `game_config_version_seq`. Así el historial de balance se
conserva y las transacciones antiguas siguen apuntando a la versión con la que se
calcularon.

Orden de siembra (importa: los pasos posteriores leen `game_configs`)::

    1. game_configs          → 177 parámetros (§5)
    2. level_definitions     → curva global y por conocimiento (§6.1)
    3. knowledge_areas       → 7 conocimientos canónicos y sus territorios
    4. items                 → 46 ítems, sus requisitos y sus ofertas de tienda
    5. achievements          → 32 logros
    6. mission_templates     → 23 plantillas de misión
    7. contenido             → la Ruta del Reino de SQL completa

Uso::

    python -m app.seeds.ejecutar              # siembra todo
    python -m app.seeds.ejecutar --dry-run    # calcula y revierte, sin escribir
"""

from __future__ import annotations

import argparse
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.models.content import (
    Assessment,
    AssessmentQuestion,
    KnowledgeArea,
    LearningPath,
    Lesson,
    LessonBlock,
    PathModule,
    Question,
    Territory,
    Topic,
)
from app.models.economy import Item, ItemRequirement, ShopListing
from app.models.enums import Currency, LessonBlockType
from app.models.gamification import Achievement, GameConfig, LevelDefinition, MissionTemplate
from app.modules.gamification import servicio_config
from app.modules.gamification.servicio_config import ServicioConfig
from app.seeds import id_semilla
from app.seeds.areas import AREAS, AreaSemilla
from app.seeds.config_juego import PARAMETROS
from app.seeds.items import ITEMS, ItemSemilla, listados_tienda
from app.seeds.logros import catalogo as catalogo_logros
from app.seeds.misiones import PLANTILLAS
from app.seeds.niveles import filas_nivel
from app.seeds.reglas_recompensa import definiciones as reglas_recompensa
from app.seeds.ruta_semilla_sql import (
    RUTA,
    ModuloSemilla,
    PreguntaSemilla,
    banco_de_evaluacion,
)

__all__ = ["Resumen", "main", "sembrar"]


@dataclass
class Resumen:
    """Cuenta de filas creadas y actualizadas por tabla."""

    creadas: Counter[str] = field(default_factory=Counter)
    actualizadas: Counter[str] = field(default_factory=Counter)
    sin_cambios: Counter[str] = field(default_factory=Counter)

    def registrar(self, tabla: str, *, creada: bool, cambiada: bool = True) -> None:
        """Anota el resultado de escribir una fila."""
        if creada:
            self.creadas[tabla] += 1
        elif cambiada:
            self.actualizadas[tabla] += 1
        else:
            self.sin_cambios[tabla] += 1

    def tablas(self) -> list[str]:
        """Tablas tocadas, en orden alfabético."""
        return sorted(set(self.creadas) | set(self.actualizadas) | set(self.sin_cambios))

    def total(self, tabla: str) -> int:
        """Filas sembradas en una tabla (creadas más actualizadas más intactas)."""
        return self.creadas[tabla] + self.actualizadas[tabla] + self.sin_cambios[tabla]

    def informe(self) -> str:
        """Texto del resumen que imprime el comando."""
        lineas = [f"{'tabla':<24}{'total':>8}{'nuevas':>8}{'actualiz.':>11}{'iguales':>9}"]
        for tabla in self.tablas():
            lineas.append(
                f"{tabla:<24}{self.total(tabla):>8}{self.creadas[tabla]:>8}"
                f"{self.actualizadas[tabla]:>11}{self.sin_cambios[tabla]:>9}"
            )
        return "\n".join(lineas)


def _asignar(fila: Any, valores: dict[str, Any]) -> bool:
    """Copia los valores a la fila y devuelve si alguno cambió realmente."""
    cambio = False
    for campo, valor in valores.items():
        if getattr(fila, campo) != valor:
            setattr(fila, campo, valor)
            cambio = True
    return cambio


def _upsert(
    db: Session,
    modelo: type,
    fila_id: uuid.UUID,
    valores: dict[str, Any],
    resumen: Resumen,
    tabla: str,
) -> Any:
    """Inserta o actualiza una fila por su identificador determinista."""
    fila = db.get(modelo, fila_id)
    if fila is None:
        fila = modelo(id=fila_id, **valores)
        db.add(fila)
        db.flush()
        resumen.registrar(tabla, creada=True)
        return fila
    cambio = _asignar(fila, valores)
    db.flush()
    resumen.registrar(tabla, creada=False, cambiada=cambio)
    return fila


# ---------------------------------------------------------------------------
# 1. game_configs
# ---------------------------------------------------------------------------


def sembrar_configuracion(db: Session, resumen: Resumen) -> None:
    """Siembra los 177 parámetros de §5 respetando el versionado de la tabla."""
    ahora = utcnow()
    for parametro in PARAMETROS:
        vigente = db.execute(
            sa.select(GameConfig)
            .where(
                GameConfig.key == parametro.key,
                sa.or_(GameConfig.valid_to.is_(None), GameConfig.valid_to > ahora),
            )
            .order_by(GameConfig.version.desc())
            .limit(1)
        ).scalar_one_or_none()

        if (
            vigente is not None
            and vigente.value == parametro.value
            and vigente.value_type == parametro.value_type
        ):
            # Mismo valor: solo se refrescan los metadatos, sin abrir versión nueva.
            cambio = _asignar(
                vigente,
                {"is_public": parametro.is_public, "description": parametro.description},
            )
            resumen.registrar("game_configs", creada=False, cambiada=cambio)
            continue

        version = 1
        if vigente is not None:
            vigente.valid_to = ahora
            version = int(vigente.version) + 1

        config_version = db.execute(sa.text("SELECT nextval('game_config_version_seq')")).scalar_one()
        db.add(
            GameConfig(
                key=parametro.key,
                version=version,
                config_version=int(config_version),
                value=parametro.value,
                value_type=parametro.value_type,
                valid_from=ahora,
                is_public=parametro.is_public,
                description=parametro.description,
            )
        )
        resumen.registrar("game_configs", creada=vigente is None, cambiada=True)
    db.flush()
    servicio_config.invalidar_cache()


# ---------------------------------------------------------------------------
# 2. level_definitions
# ---------------------------------------------------------------------------


def sembrar_niveles(db: Session, cfg: ServicioConfig, resumen: Resumen) -> None:
    """Materializa las dos curvas de nivel calculadas con las fórmulas de §6.1."""
    for fila in filas_nivel(db, cfg):
        existente = db.execute(
            sa.select(LevelDefinition).where(
                LevelDefinition.scope == fila.scope, LevelDefinition.level == fila.level
            )
        ).scalar_one_or_none()
        valores = {
            "xp_required": fila.xp_required,
            "xp_delta": fila.xp_delta,
            "rank_title": fila.rank_title,
            "is_rank_start": fila.is_rank_start,
            "unlocks": fila.unlocks,
        }
        if existente is None:
            db.add(LevelDefinition(scope=fila.scope, level=fila.level, **valores))
            resumen.registrar("level_definitions", creada=True)
        else:
            cambio = _asignar(existente, valores)
            resumen.registrar("level_definitions", creada=False, cambiada=cambio)
    db.flush()


# ---------------------------------------------------------------------------
# 3. knowledge_areas y territories
# ---------------------------------------------------------------------------


def sembrar_areas(db: Session, resumen: Resumen) -> dict[str, KnowledgeArea]:
    """Siembra los conocimientos canónicos y su territorio en el mapa."""
    resueltas: dict[str, KnowledgeArea] = {}
    for semilla in AREAS:
        area = _sembrar_area(db, semilla, resumen)
        resueltas[semilla.slug] = area
    db.flush()
    return resueltas


def _sembrar_area(db: Session, semilla: AreaSemilla, resumen: Resumen) -> KnowledgeArea:
    """Un conocimiento y su territorio, buscados por `slug` (clave natural)."""
    area = db.execute(sa.select(KnowledgeArea).where(KnowledgeArea.slug == semilla.slug)).scalar_one_or_none()
    valores = {
        "name": semilla.name,
        "short_name": semilla.short_name,
        "category": semilla.category,
        "description": semilla.description,
        "is_canonical": True,
        "icon_key": semilla.icon_key,
        "accent_color": semilla.accent_color,
        "is_active": True,
    }
    if area is None:
        area = KnowledgeArea(id=id_semilla("area", semilla.slug), slug=semilla.slug, **valores)
        db.add(area)
        db.flush()
        resumen.registrar("knowledge_areas", creada=True)
    else:
        cambio = _asignar(area, valores)
        resumen.registrar("knowledge_areas", creada=False, cambiada=cambio)

    _upsert(
        db,
        Territory,
        id_semilla("territory", semilla.slug),
        {
            "knowledge_area_id": area.id,
            "name": semilla.territory_name,
            "icon_hint": semilla.territory_icon,
            "concept_keyword": semilla.concept_keyword,
            "description": semilla.territory_description,
        },
        resumen,
        "territories",
    )
    return area


# ---------------------------------------------------------------------------
# 4. items, item_requirements y shop_listings
# ---------------------------------------------------------------------------


def sembrar_items(
    db: Session, cfg: ServicioConfig, areas: dict[str, KnowledgeArea], resumen: Resumen
) -> dict[str, Item]:
    """Siembra el catálogo de 46 ítems, sus requisitos y sus ofertas de tienda."""
    resueltos: dict[str, Item] = {}
    for semilla in ITEMS:
        resueltos[semilla.code] = _sembrar_item(db, semilla, areas, resumen)
    db.flush()

    for listado in listados_tienda(cfg):
        item = resueltos[listado.item_code]
        _upsert(
            db,
            ShopListing,
            id_semilla("shop_listing", listado.item_code),
            {
                "item_id": item.id,
                "currency": Currency.GOLD,
                "price": listado.price,
                "min_level": listado.min_level,
                "is_featured": listado.is_featured,
                "featured_order": listado.featured_order,
                "is_active": True,
            },
            resumen,
            "shop_listings",
        )
    db.flush()
    return resueltos


def _sembrar_item(
    db: Session, semilla: ItemSemilla, areas: dict[str, KnowledgeArea], resumen: Resumen
) -> Item:
    """Un ítem del catálogo global, buscado por `code` (clave natural)."""
    item = db.execute(sa.select(Item).where(Item.code == semilla.code)).scalar_one_or_none()
    valores = {
        "name": semilla.name,
        "description": semilla.description,
        "slot": semilla.slot,
        "rarity": semilla.rarity,
        "origin": semilla.origin,
        "requirements": semilla.requirements,
        "requirement_facts": list(semilla.requirement_facts),
        "auto_grant": semilla.auto_grant,
        "render_manifest": semilla.render_manifest,
        "icon_key": semilla.icon_key,
        "is_template": semilla.is_template,
        "template_code": None,
        "owner_user_id": None,
        "knowledge_area_id": None,
        "visibility": semilla.visibility,
        "tier_required": None,
        "is_active": True,
    }
    if item is None:
        item = Item(id=id_semilla("item", semilla.code), code=semilla.code, **valores)
        db.add(item)
        db.flush()
        resumen.registrar("items", creada=True)
    else:
        cambio = _asignar(item, valores)
        db.flush()
        resumen.registrar("items", creada=False, cambiada=cambio)

    esperados: set[uuid.UUID] = set()
    for requisito in semilla.requisitos:
        area = areas.get(requisito.area_slug or "") if requisito.area_slug != "self" else None
        fila_id = id_semilla("item_req", semilla.code, str(requisito.group_index), str(requisito.position))
        esperados.add(fila_id)
        _upsert(
            db,
            ItemRequirement,
            fila_id,
            {
                "item_id": item.id,
                "group_index": requisito.group_index,
                "position": requisito.position,
                "requirement_type": requisito.requirement_type,
                "knowledge_area_id": area.id if area is not None else None,
                "area_slug": requisito.area_slug,
                "target_value": requisito.target_value,
                "target_count": requisito.target_count,
                "achievement_code": requisito.achievement_code,
                "streak_kind": requisito.streak_kind,
                "label_template": requisito.label_template,
            },
            resumen,
            "item_requirements",
        )

    # Retira condiciones que ya no estén en la semilla (el catálogo puede encogerse).
    sobrantes = db.execute(
        sa.select(ItemRequirement).where(
            ItemRequirement.item_id == item.id,
            ItemRequirement.id.not_in(esperados) if esperados else sa.true(),
        )
    ).scalars()
    for fila in sobrantes:
        db.delete(fila)
    db.flush()
    return item


# ---------------------------------------------------------------------------
# 5. achievements
# ---------------------------------------------------------------------------


def derivar_cosmeticos_de_conocimiento(
    db: Session, areas: dict[str, KnowledgeArea], resumen: Resumen
) -> None:
    """Materializa los tres moldes del catálogo para cada conocimiento canónico.

    Los moldes (`tpl_capa_estudiante`, `tpl_capa_maestro`,
    `tpl_insignia_perfeccion`) llevan el hueco `{short_name}` en el nombre y no
    son equipables: existen para derivar uno por conocimiento. Nadie los derivaba,
    así que terminar una ruta prometía una capa que no existía como fila y todo
    cosmético de conocimiento del juego era inalcanzable.

    Va después de `sembrar_items` porque necesita los moldes ya en la base, y es
    idempotente: repetir la siembra no crea duplicados.
    """
    from app.models.economy import ItemRequirement  # noqa: PLC0415
    from app.modules.economy import plantillas  # noqa: PLC0415 - evita el ciclo

    derivados: list[uuid.UUID] = []
    for area in areas.values():
        for item in plantillas.derivar_para_area(db, area):
            resumen.registrar("items", creada=True)
            derivados.append(item.id)

    if not derivados:
        return
    # Las condiciones viajan con el derivado y también son filas sembradas: sin
    # contarlas, el resumen diría que el catálogo tiene menos requisitos de los
    # que tiene, y el oráculo de la siembra dejaría de cuadrar.
    condiciones = int(
        db.execute(
            sa.select(sa.func.count(ItemRequirement.id)).where(
                ItemRequirement.item_id.in_(derivados)
            )
        ).scalar_one()
    )
    for _ in range(condiciones):
        resumen.registrar("item_requirements", creada=True)


def sembrar_logros(db: Session, cfg: ServicioConfig, resumen: Resumen) -> None:
    """Siembra los 32 logros con sus reglas declarativas y sus niveles."""
    for semilla in catalogo_logros(cfg):
        logro = db.execute(
            sa.select(Achievement).where(Achievement.code == semilla.code)
        ).scalar_one_or_none()
        valores = {
            "name": semilla.name,
            "description": semilla.description,
            "category": semilla.category,
            "visibility": semilla.visibility,
            "rule": semilla.rule,
            "tiers": semilla.tiers_json(),
            "icon_key": semilla.icon_key,
            "sort_order": semilla.sort_order,
            "is_active": True,
        }
        if logro is None:
            db.add(Achievement(id=id_semilla("achievement", semilla.code), code=semilla.code, **valores))
            resumen.registrar("achievements", creada=True)
        else:
            cambio = _asignar(logro, valores)
            resumen.registrar("achievements", creada=False, cambiada=cambio)
    db.flush()


# ---------------------------------------------------------------------------
# 6. mission_templates
# ---------------------------------------------------------------------------


def sembrar_misiones(db: Session, resumen: Resumen) -> None:
    """Siembra las 23 plantillas de misión (las semanales, desactivadas)."""
    for semilla in PLANTILLAS:
        plantilla = db.execute(
            sa.select(MissionTemplate).where(MissionTemplate.code == semilla.code)
        ).scalar_one_or_none()
        valores = {
            "scope": semilla.scope,
            "title_template": semilla.title_template,
            "narrative_key": semilla.narrative_key,
            "metric": semilla.metric,
            "params": semilla.params,
            "target_scope": semilla.target_scope,
            "eligibility": list(semilla.eligibility),
            "exclude_if_goal_type": list(semilla.exclude_if_goal_type),
            "reward_profile": semilla.reward_profile,
            "rewards": semilla.rewards,
            "weight": semilla.weight,
            "is_active": semilla.is_active,
        }
        if plantilla is None:
            db.add(
                MissionTemplate(id=id_semilla("mission_template", semilla.code), code=semilla.code, **valores)
            )
            resumen.registrar("mission_templates", creada=True)
        else:
            cambio = _asignar(plantilla, valores)
            resumen.registrar("mission_templates", creada=False, cambiada=cambio)
    db.flush()


# ---------------------------------------------------------------------------
# 7. Contenido: la Ruta del Reino de SQL
# ---------------------------------------------------------------------------


def sembrar_ruta_sql(
    db: Session, cfg: ServicioConfig, areas: dict[str, KnowledgeArea], resumen: Resumen
) -> LearningPath:
    """Siembra la ruta semilla completa: módulos, temas, lecciones, preguntas y pruebas."""
    area = areas[RUTA.area_slug]
    ruta = _upsert(
        db,
        LearningPath,
        id_semilla("path", RUTA.code),
        {
            "user_id": None,
            "knowledge_area_id": area.id,
            "title": RUTA.title,
            "goal_text": RUTA.goal_text,
            "summary": RUTA.summary,
            "declared_level": RUTA.declared_level,
            "source_mode": RUTA.source_mode,
            "origin": RUTA.origin,
            "status": RUTA.status,
            "language": RUTA.language,
            "coverage_policy": RUTA.coverage_policy,
            "coverage_notes": [],
            "module_count": len(RUTA.modulos),
            "estimated_minutes": RUTA.estimated_minutes,
            "is_public": RUTA.is_public,
        },
        resumen,
        "learning_paths",
    )

    for modulo in RUTA.modulos:
        _sembrar_modulo(db, cfg, ruta, modulo, resumen)
    db.flush()
    return ruta


def _sembrar_modulo(
    db: Session, cfg: ServicioConfig, ruta: LearningPath, modulo: ModuloSemilla, resumen: Resumen
) -> None:
    """Un módulo con sus temas, lecciones, preguntas y su evaluación de cierre."""
    fila_modulo = _upsert(
        db,
        PathModule,
        id_semilla("module", RUTA.code, modulo.code),
        {
            "learning_path_id": ruta.id,
            "position": modulo.position,
            "title": modulo.title,
            "flavor_name": modulo.flavor_name,
            "summary": modulo.summary,
            "difficulty": modulo.difficulty,
            "estimated_minutes": modulo.estimated_minutes,
            "content_status": RUTA.content_status,
            "prerequisite_module_id": None,
            "topic_count": len(modulo.temas),
            "lesson_count": sum(len(tema.lecciones) for tema in modulo.temas),
        },
        resumen,
        "path_modules",
    )

    preguntas_por_codigo: dict[str, Question] = {}
    for tema in modulo.temas:
        fila_tema = _upsert(
            db,
            Topic,
            id_semilla("topic", tema.code),
            {
                "module_id": fila_modulo.id,
                "position": tema.position,
                "title": tema.title,
                "learning_objectives": list(tema.learning_objectives),
                "coverage": RUTA.coverage,
                "difficulty": tema.difficulty,
                "estimated_minutes": tema.estimated_minutes,
                "suggested_question_types": tema.suggested_question_types,
                "source_chunk_ids": [],
                "lesson_count": len(tema.lecciones),
                "content_status": RUTA.content_status,
            },
            resumen,
            "topics",
        )

        leccion = tema.lecciones[0]
        fila_leccion = _upsert(
            db,
            Lesson,
            id_semilla("lesson", leccion.code),
            {
                "topic_id": fila_tema.id,
                "position": leccion.position,
                "title": leccion.title,
                "summary": leccion.summary,
                "estimated_seconds": leccion.estimated_seconds,
                "content_status": RUTA.content_status,
                "origin": RUTA.provenance,
                "is_low_content": False,
                "coverage_report": [dict(entrada) for entrada in leccion.coverage_report],
                "block_count": len(leccion.bloques),
                "question_count": len(tema.preguntas),
                "content_version": 1,
            },
            resumen,
            "lessons",
        )

        # Las preguntas del tema se siembran antes que los bloques: el bloque
        # `inline_question` necesita el `id` de la pregunta en su `payload`.
        for pregunta in tema.preguntas:
            preguntas_por_codigo[pregunta.code] = _sembrar_pregunta(
                db, fila_tema.id, fila_leccion.id, pregunta, resumen
            )

        for bloque in leccion.bloques:
            payload = dict(bloque.payload)
            if bloque.block_type is LessonBlockType.INLINE_QUESTION and bloque.question_code:
                payload["question_id"] = str(preguntas_por_codigo[bloque.question_code].id)
            _upsert(
                db,
                LessonBlock,
                id_semilla("block", leccion.code, str(bloque.position)),
                {
                    "lesson_id": fila_leccion.id,
                    "position": bloque.position,
                    "block_type": bloque.block_type,
                    "body": bloque.body,
                    "payload": payload,
                    "origin": RUTA.provenance,
                    "is_flagged": False,
                    "flag_reason": None,
                },
                resumen,
                "lesson_blocks",
            )

    _sembrar_evaluacion(db, cfg, fila_modulo.id, modulo, preguntas_por_codigo, resumen)


def _sembrar_pregunta(
    db: Session,
    topic_id: uuid.UUID,
    lesson_id: uuid.UUID,
    pregunta: PreguntaSemilla,
    resumen: Resumen,
) -> Question:
    """Una pregunta del pool del tema, con su clave de corrección y su explicación."""
    return _upsert(
        db,
        Question,
        id_semilla("question", pregunta.code),
        {
            "topic_id": topic_id,
            "lesson_id": lesson_id,
            "question_type": pregunta.question_type,
            "difficulty": pregunta.difficulty,
            "stem": pregunta.stem,
            "body": pregunta.body,
            "answer_key": pregunta.answer_key,
            "explanation": pregunta.explanation,
            "learning_objective": pregunta.learning_objective,
            "estimated_seconds": pregunta.estimated_seconds,
            "origin": RUTA.provenance,
            "is_remedial": False,
            "content_status": RUTA.content_status,
            "is_flagged": False,
            "flag_reason": None,
            "flag_count": 0,
            "content_version": 1,
        },
        resumen,
        "questions",
    )


def _sembrar_evaluacion(
    db: Session,
    cfg: ServicioConfig,
    module_id: uuid.UUID,
    modulo: ModuloSemilla,
    preguntas: dict[str, Question],
    resumen: Resumen,
) -> None:
    """La prueba del módulo y su banco, que excluye las preguntas abiertas."""
    banco = banco_de_evaluacion(modulo)
    evaluacion = _upsert(
        db,
        Assessment,
        id_semilla("assessment", modulo.code),
        {
            "module_id": module_id,
            "title": modulo.assessment_title,
            "question_count": modulo.assessment_question_count,
            "pass_score": cfg.obtener_decimal("mastery.assessment.pass_score"),
            "bank_size": len(banco),
            "max_attempts_per_day": cfg.obtener_int("mastery.assessment.max_attempts_per_day"),
            "content_status": RUTA.content_status,
        },
        resumen,
        "assessments",
    )
    for posicion, pregunta in enumerate(banco, start=1):
        _upsert(
            db,
            AssessmentQuestion,
            id_semilla("assessment_question", modulo.code, pregunta.code),
            {
                "assessment_id": evaluacion.id,
                "question_id": preguntas[pregunta.code].id,
                "position": posicion,
                "is_active": True,
            },
            resumen,
            "assessment_questions",
        )


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 8. reward_rules
# ---------------------------------------------------------------------------


def sembrar_reglas_recompensa(db: Session, resumen: Resumen) -> None:
    """Siembra las reglas que convierten cada evento en XP y oro.

    Sin estas filas el motor procesa el evento y no otorga nada: es la tabla que
    hace que terminar una lección se sienta. Cada regla apunta a su clave de
    `game_configs`, nunca a una cifra escrita a mano.
    """
    from app.models.gamification import RewardRule  # noqa: PLC0415 - cruce entre módulos (§1.3)

    for definicion in reglas_recompensa():
        valores = dict(definicion)
        code = valores["code"]
        _upsert(
            db,
            RewardRule,
            id_semilla("reward_rule", code),
            valores,
            resumen,
            "reward_rules",
        )


def sembrar(db: Session) -> Resumen:
    """Siembra todos los catálogos en el orden correcto y devuelve el resumen.

    No hace `commit`: quien llama decide (el comando confirma, las pruebas revierten).
    """
    resumen = Resumen()
    sembrar_configuracion(db, resumen)
    cfg = ServicioConfig(db, ttl_segundos=0)
    sembrar_niveles(db, cfg, resumen)
    areas = sembrar_areas(db, resumen)
    sembrar_items(db, cfg, areas, resumen)
    derivar_cosmeticos_de_conocimiento(db, areas, resumen)
    sembrar_logros(db, cfg, resumen)
    sembrar_misiones(db, resumen)
    sembrar_reglas_recompensa(db, resumen)
    sembrar_ruta_sql(db, cfg, areas, resumen)
    return resumen


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de `python -m app.seeds.ejecutar`."""
    parser = argparse.ArgumentParser(
        prog="python -m app.seeds.ejecutar",
        description="Siembra los catálogos iniciales de Atenea. Es idempotente.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="calcula la siembra y la revierte al terminar, sin escribir nada",
    )
    args = parser.parse_args(argv)

    servicio_config.invalidar_cache()
    sesion = SessionLocal()
    try:
        resumen = sembrar(sesion)
        if args.dry_run:
            sesion.rollback()
            print("Simulación (--dry-run): nada se ha escrito.\n")
        else:
            sesion.commit()
            print("Siembra completada.\n")
        print(resumen.informe())
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()
        servicio_config.invalidar_cache()
    return 0


if __name__ == "__main__":  # pragma: no cover - punto de entrada del comando
    raise SystemExit(main())
