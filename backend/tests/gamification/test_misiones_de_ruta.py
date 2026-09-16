"""Empezar una ruta tiene que repartir sus misiones especiales.

`asignar_misiones_de_ruta` existía desde el principio, estaba exportada en
`__all__` y **no la llamaba nadie**. La consecuencia se veía en pantalla y a la
vez era invisible: la sección de misiones especiales del tablón iba a salir vacía
para siempre, y ninguna prueba lo notaba porque ninguna la ejercía.

Se engancha en el motor, sobre `PATH_CREATED`, y no en los dos sitios que crean
rutas —crear una propia y adoptar una del Reino—, porque los dos pasan por ese
evento. Un sitio en vez de dos.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.content import KnowledgeArea, LearningPath
from app.models.enums import EventType, KnowledgeCategory, MissionScope, MissionStatus
from app.models.gamification import UserMission
from app.models.identity import User
from app.modules.gamification import eventos


@pytest.fixture
def conocimiento(db: Session) -> KnowledgeArea:
    """Un conocimiento de verdad: `user_missions` lo referencia con clave foránea."""
    sufijo = uuid.uuid4().hex[:8]
    area = KnowledgeArea(
        slug=f"sql-{sufijo}",
        name="SQL",
        short_name="SQL",
        category=KnowledgeCategory.DATA,
    )
    db.add(area)
    db.flush()
    return area


@pytest.fixture
def crear_ruta(db: Session, conocimiento: KnowledgeArea):
    """Fábrica de rutas. También con clave foránea, así que no valen uuid sueltos."""

    def _crear(titulo: str = "Dominar SQL") -> LearningPath:
        ruta = LearningPath(knowledge_area_id=conocimiento.id, title=titulo)
        db.add(ruta)
        db.flush()
        return ruta

    return _crear


@pytest.fixture
def plantillas_de_ruta(crear_plantilla_mision):
    """Tres plantillas especiales, que es lo que `missions.path.per_path` pide."""
    return [
        crear_plantilla_mision(
            f"S{numero:02d}",
            scope=MissionScope.SPECIAL,
            title_template="Termina el módulo {n}",
            params={"n": {"easy": 1, "medium": 2, "hard": 3}},
        )
        for numero in range(1, 4)
    ]


def _empezar_ruta(
    db: Session, usuario: User, path_id: uuid.UUID, *, clave: str, area: uuid.UUID | None = None
):
    """Registra el evento que emiten tanto crear una ruta como adoptarla."""
    return eventos.registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.PATH_CREATED,
        payload={
            "path_id": str(path_id),
            "knowledge_area_id": str(area) if area else None,
            "origin": "user",
        },
        idempotency_key=clave,
        source_module="content",
    )


def _especiales(db: Session, usuario: User) -> list[UserMission]:
    return list(
        db.execute(
            sa.select(UserMission).where(
                UserMission.user_id == usuario.id,
                UserMission.scope == MissionScope.SPECIAL,
            )
        )
        .scalars()
        .all()
    )


def test_empezar_una_ruta_reparte_sus_misiones(
    db: Session, usuario: User, plantillas_de_ruta, crear_ruta
) -> None:
    ruta = crear_ruta().id

    _empezar_ruta(db, usuario, ruta, clave=f"path:{ruta}")

    creadas = _especiales(db, usuario)
    assert len(creadas) == 3, "«missions.path.per_path» son tres"
    assert {m.learning_path_id for m in creadas} == {ruta}
    assert all(m.status == MissionStatus.ACTIVE for m in creadas)


def test_las_misiones_de_ruta_no_caducan(
    db: Session, usuario: User, plantillas_de_ruta, crear_ruta
) -> None:
    """A diferencia de las diarias, acompañan a la ruta hasta que se termina."""
    ruta = crear_ruta().id

    _empezar_ruta(db, usuario, ruta, clave=f"path:{ruta}")

    for mision in _especiales(db, usuario):
        assert mision.expires_at is None
        assert mision.assigned_for is None


def test_adoptar_la_misma_ruta_dos_veces_no_duplica(
    db: Session, usuario: User, plantillas_de_ruta, crear_ruta
) -> None:
    """La idempotencia la sostienen dos cosas: la clave del evento y la función."""
    ruta = crear_ruta().id

    _empezar_ruta(db, usuario, ruta, clave=f"path:{ruta}")
    # Clave distinta a propósito: así se prueba la guarda de la función, no la
    # del bus de eventos.
    _empezar_ruta(db, usuario, ruta, clave=f"path:{ruta}:otra-vez")

    assert len(_especiales(db, usuario)) == 3


def test_cada_ruta_trae_las_suyas(
    db: Session, usuario: User, plantillas_de_ruta, crear_ruta
) -> None:
    primera = crear_ruta("Dominar SQL").id
    segunda = crear_ruta("Dominar Python").id

    _empezar_ruta(db, usuario, primera, clave=f"path:{primera}")
    _empezar_ruta(db, usuario, segunda, clave=f"path:{segunda}")

    creadas = _especiales(db, usuario)
    assert len(creadas) == 6
    assert {m.learning_path_id for m in creadas} == {primera, segunda}


def test_la_ruta_lleva_su_conocimiento(
    db: Session, usuario: User, plantillas_de_ruta, crear_ruta, conocimiento
) -> None:
    """El conocimiento viaja en el evento y hay misiones que lo necesitan."""
    ruta = crear_ruta().id

    _empezar_ruta(db, usuario, ruta, clave=f"path:{ruta}", area=conocimiento.id)

    assert {m.knowledge_area_id for m in _especiales(db, usuario)} == {conocimiento.id}


def test_un_evento_sin_ruta_no_rompe_nada(
    db: Session, usuario: User, plantillas_de_ruta
) -> None:
    """El motor no puede caerse por un payload incompleto."""
    eventos.registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.PATH_CREATED,
        payload={"origin": "user"},
        idempotency_key=f"path-sin-id:{uuid.uuid4()}",
        source_module="content",
    )

    assert _especiales(db, usuario) == []
