"""Rutas HTTP del módulo `progress`: panel, perfil, estadísticas y conocimiento.

Contrato §7.4 y §7.8. Este archivo expone `router = APIRouter()` **sin prefijo**: el
prefijo `/api/v1` y el montaje los pone el router raíz (`app/api/v1/__init__.py`, A8).

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/dashboard` | `DashboardOut` (P04) |
| GET | `/profile` | `ProfileOut` (P17) |
| GET | `/profile/stats` | `StatsOut` con rango `from`/`to` |
| GET | `/me/knowledge` | `Page<UserKnowledgeOut>` |

Aislamiento por usuario (§8.7): todas las consultas filtran por `user_id` del token;
ninguna ruta recibe un identificador de usuario.
"""

from __future__ import annotations

from datetime import date as date_type, timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.core.time import user_local_date, utcnow
from app.models.identity import Character
from app.modules.progress.estadisticas import ServicioEstadisticas
from app.modules.progress.panel import ServicioPanel
from app.modules.progress.schemas import (
    DashboardOut,
    DayActivityOut,
    Page,
    PageMeta,
    ProfileCharacterOut,
    ProfileOut,
    ProfileStatsOut,
    StatsOut,
    StatsTotalsOut,
    UserKnowledgeOut,
)

router = APIRouter()

#: Ventana por defecto de `GET /profile/stats` cuando el cliente no manda fechas.
DIAS_RANGO_POR_DEFECTO = 30
#: Paginación por defecto y máxima (§8.2).
LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 100


@router.get("/dashboard", response_model=DashboardOut, summary="Panel principal (P04)")
def obtener_panel(db: DbSession, user: CurrentUser) -> DashboardOut:
    """Devuelve en una sola llamada todo lo que dibuja la pantalla de inicio."""
    panel = ServicioPanel(db).construir(user.id, user.timezone)
    return DashboardOut.model_validate(panel)


@router.get("/profile", response_model=ProfileOut, summary="Perfil de videojuego (P17)")
def obtener_perfil(db: DbSession, user: CurrentUser) -> ProfileOut:
    """Personaje, estadísticas acumuladas, conocimientos y actividad de la semana."""
    servicio = ServicioEstadisticas(db)
    panel = ServicioPanel(db)

    personaje = panel.personaje(user.id)
    fila = db.execute(
        sa.select(Character).where(Character.user_id == user.id)
    ).scalar_one_or_none()
    racha = panel.racha_visible(user.id, user.timezone)
    estadisticas = servicio.estadisticas_perfil(user.id, streak_current=racha.current)

    return ProfileOut(
        character=ProfileCharacterOut(
            name=fila.name if fila else "",
            archetype=fila.archetype.value if fila else "",
            level=personaje.level,
            rank_title=personaje.rank_title,
            xp_total=personaje.xp_total,
            xp_to_next=personaje.xp_to_next,
            progress_pct=personaje.progress_pct,
            total_study_seconds=int(fila.total_study_seconds) if fila else 0,
        ),
        avatar_layers=[],
        stats=ProfileStatsOut.model_validate(estadisticas),
        knowledge=[UserKnowledgeOut.model_validate(k) for k in servicio.conocimientos(user.id)],
        last_7_days=[
            DayActivityOut.model_validate(d) for d in servicio.ultimos_dias(user.id, user.timezone)
        ],
    )


@router.get("/profile/stats", response_model=StatsOut, summary="Estadísticas con rango")
def obtener_estadisticas(
    db: DbSession,
    user: CurrentUser,
    desde: date_type | None = Query(default=None, alias="from"),
    hasta: date_type | None = Query(default=None, alias="to"),
) -> StatsOut:
    """Serie diaria, totales, precisión, lecciones y evaluaciones del rango pedido."""
    hoy = user_local_date(utcnow(), user.timezone)
    fin = hasta or hoy
    inicio = desde or (fin - timedelta(days=DIAS_RANGO_POR_DEFECTO - 1))
    if inicio > fin:
        inicio, fin = fin, inicio

    datos = ServicioEstadisticas(db).estadisticas(user.id, inicio, fin)
    return StatsOut(
        daily=[DayActivityOut.model_validate(d) for d in datos.daily],
        totals=StatsTotalsOut.model_validate(datos.totals),
        accuracy_pct=datos.accuracy_pct,
        lessons=datos.lessons,
        assessments=datos.assessments,
    )


@router.get(
    "/me/knowledge",
    response_model=Page[UserKnowledgeOut],
    summary="Perfil de conocimiento del usuario",
)
def obtener_conocimientos(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=LIMITE_POR_DEFECTO, ge=1, le=LIMITE_MAXIMO),
) -> Page[UserKnowledgeOut]:
    """Lista de conocimientos con nivel, XP, dominio, tiempo y estado (§7.4)."""
    filas = ServicioEstadisticas(db).conocimientos(user.id)
    recortadas = filas[:limit]
    return Page[UserKnowledgeOut](
        items=[UserKnowledgeOut.model_validate(f) for f in recortadas],
        page=PageMeta(
            limit=limit,
            next_cursor=None,
            has_more=len(filas) > limit,
            total=len(filas),
        ),
    )


__all__ = ["router"]
