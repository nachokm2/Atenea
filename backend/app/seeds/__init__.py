"""Semillas del Reino: catálogos iniciales y contenido curado del MVP.

Este paquete es la **única** fuente de las filas de catálogo que el producto necesita
para arrancar. Sin ellas, un usuario nuevo no puede completar su primera lección en
menos de cinco minutos, que es el criterio de éxito del onboarding.

Qué siembra cada módulo:

===================  =========================================================
Módulo               Tablas que llena
===================  =========================================================
`config_juego`       `game_configs` (los 178 parámetros del contrato §5)
`niveles`            `level_definitions` (curva global y por conocimiento, §6.1)
`areas`              `knowledge_areas` y `territories`
`items`              `items`, `item_requirements` y `shop_listings` (46 ítems)
`logros`             `achievements` (32 logros)
`misiones`           `mission_templates` (23 plantillas)
`ruta_semilla_sql`   `learning_paths`, `path_modules`, `topics`, `lessons`,
                     `lesson_blocks`, `questions`, `assessments` y
                     `assessment_questions` de la Ruta del Reino de SQL
`ejecutar`           el comando `python -m app.seeds.ejecutar`
===================  =========================================================

**Identificadores deterministas.** Todo lo que no tiene clave natural (el contenido
educativo: rutas, módulos, temas, lecciones, bloques, preguntas y evaluaciones) recibe
su `id` con `uuid5` sobre un código estable, de modo que sembrar dos veces escribe
exactamente las mismas filas y nunca duplica nada. Lo que sí tiene clave natural
(`game_configs.key`, `knowledge_areas.slug`, `items.code`, `achievements.code`,
`mission_templates.code`) se actualiza por esa clave.
"""

from __future__ import annotations

import uuid
from typing import Final

__all__ = ["NAMESPACE_SEMILLA", "id_semilla"]

#: Espacio de nombres UUID de las semillas: `uuid5(NAMESPACE_DNS, "seeds.atenea.app")`.
#: Está escrito literal a propósito: es una constante de identidad, no un valor de juego,
#: y debe sobrevivir a cualquier cambio del código que lo generó.
NAMESPACE_SEMILLA: Final[uuid.UUID] = uuid.UUID("73de04b6-5d34-5b05-aa6e-626435388b51")


def id_semilla(*partes: str) -> uuid.UUID:
    """Identificador estable y reproducible para una fila de semilla.

    Las partes se unen con ``:`` y se convierten en un `uuid5`, así que el mismo código
    produce siempre el mismo `id`. Es lo que hace idempotente la siembra del contenido.

    >>> id_semilla("path", "ruta_sql") == id_semilla("path", "ruta_sql")
    True
    """
    return uuid.uuid5(NAMESPACE_SEMILLA, ":".join(partes))
