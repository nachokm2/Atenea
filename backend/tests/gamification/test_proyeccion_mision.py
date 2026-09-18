"""Lo que `GET /missions` manda de cada misión (§7.9).

`MissionOut` proyectaba diez campos y P19 lee catorce. Los cuatro que faltaban
no eran adorno:

* Sin `deep_link`, la hoja de detalle **nunca** pintaba «Ir a cumplirla»
  —`if (destino != null && !mision.estaCumplida)`, `misiones.dart`—, ni para las
  diarias. El aprendiz veía siempre el texto de consolación, y la pantalla
  parecía completa: es la enfermedad de siempre, sin síntoma.
* Sin `completed_at`, la fila «Cumplida» de esa misma hoja tampoco aparecía.
* `claimed_at` y `learning_path_id` son columnas de `user_missions` desde el
  principio y el DTO del cliente las lee.

Las tres primeras son columnas; `deep_link` se deriva, y por eso tiene su propia
prueba: una misión de ruta lleva a su mapa, una diaria no lleva a ningún sitio
concreto —cualquier lección vale— y ahí el botón no debe ofrecerse.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.content import KnowledgeArea, LearningPath
from app.models.enums import EventType, KnowledgeCategory, MissionScope
from app.models.gamification import UserMission
from app.models.identity import User
from app.modules.gamification import eventos
from app.modules.gamification.router import _mision_out

pytestmark = pytest.mark.db


@pytest.fixture
def conocimiento(db: Session) -> KnowledgeArea:
    area = KnowledgeArea(
        slug=f"sql-{uuid.uuid4().hex[:8]}",
        name="SQL",
        short_name="SQL",
        category=KnowledgeCategory.DATA,
    )
    db.add(area)
    db.flush()
    return area


@pytest.fixture
def ruta(db: Session, conocimiento: KnowledgeArea) -> LearningPath:
    fila = LearningPath(knowledge_area_id=conocimiento.id, title="Dominar SQL")
    db.add(fila)
    db.flush()
    return fila


@pytest.fixture
def plantillas(crear_plantilla_mision):
    return [
        crear_plantilla_mision(
            f"S{numero:02d}",
            scope=MissionScope.SPECIAL,
            title_template="Termina el módulo {n}",
            params={"n": {"easy": 1, "medium": 2, "hard": 3}},
        )
        for numero in range(1, 4)
    ]


def _misiones_de_ruta(db: Session, usuario: User, ruta: LearningPath) -> list[UserMission]:
    """Las que reparte empezar una ruta, por el camino real: el evento."""
    eventos.registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.PATH_CREATED,
        payload={
            "path_id": str(ruta.id),
            "knowledge_area_id": str(ruta.knowledge_area_id),
            "origin": "user",
        },
        idempotency_key=f"ruta-{uuid.uuid4()}",
        source_module="content",
    )
    return list(
        db.execute(
            sa.select(UserMission).where(
                UserMission.user_id == usuario.id,
                UserMission.scope == MissionScope.SPECIAL,
            )
        ).scalars()
    )


def test_una_mision_de_ruta_lleva_a_su_mapa(db, usuario, ruta, plantillas):
    """El destino de «Ir a cumplirla», y con el vocabulario del contrato.

    Sin esquema —`route/{id}`, no `atenea://route/{id}`—: quien sabe de
    `atenea://` es el cliente. El servidor no tiene por qué, y el traductor del
    cliente acepta las dos formas.
    """
    misiones = _misiones_de_ruta(db, usuario, ruta)
    assert misiones, "empezar la ruta no repartió ninguna misión"

    salida = _mision_out(misiones[0])

    assert salida.learning_path_id == ruta.id
    assert salida.deep_link == f"route/{ruta.id}"
    assert "://" not in salida.deep_link


def test_una_mision_sin_ruta_no_ofrece_destino(db, usuario, crear_plantilla_mision):
    """Una diaria no lleva a ningún sitio único: el botón no debe ofrecerse.

    Es la mitad que impide «arreglarlo» mandando siempre un enlace. Con un
    destino inventado, «Ir a cumplirla» llevaría a cualquier parte, que es peor
    que no ofrecerlo: la hoja ya tiene un texto para este caso.
    """
    plantilla = crear_plantilla_mision("D01", scope=MissionScope.DAILY)
    mision = UserMission(
        user_id=usuario.id,
        template_id=plantilla.id,
        template_code=plantilla.code,
        template_version=plantilla.version,
        scope=MissionScope.DAILY,
        params={},
        title="Completa 2 lecciones",
        target=2,
        progress=0,
    )
    db.add(mision)
    db.flush()

    salida = _mision_out(mision)

    assert salida.learning_path_id is None
    assert salida.deep_link is None


def test_las_marcas_de_tiempo_viajan(db, usuario, ruta, plantillas):
    """`completed_at` y `claimed_at`, que la hoja de detalle pinta.

    Se comprueban con valores propios y no con los de fábrica: dos `None` a cada
    lado también «coinciden», y eso es lo que dejaba pasar el fallo.
    """
    from app.core.time import utcnow  # noqa: PLC0415 - solo para fechar aquí

    mision = _misiones_de_ruta(db, usuario, ruta)[0]
    momento = utcnow()
    mision.completed_at = momento
    mision.claimed_at = momento
    db.flush()

    salida = _mision_out(mision)

    assert salida.completed_at == momento
    assert salida.claimed_at == momento


def test_lo_que_ya_viajaba_sigue_viajando(db, usuario, ruta, plantillas):
    """El resto del sobre no se toca: esto es añadir, no rehacer."""
    mision = _misiones_de_ruta(db, usuario, ruta)[0]

    salida = _mision_out(mision)

    assert salida.user_mission_id == mision.id
    assert salida.template_code == mision.template_code
    assert salida.scope == mision.scope.value
    assert salida.title == mision.title
    assert salida.target == int(mision.target)
    assert salida.status == mision.status.value
    assert salida.reward == {
        "xp": int(mision.reward_xp),
        "gold": int(mision.reward_gold),
    }
