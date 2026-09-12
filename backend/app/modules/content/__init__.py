"""Módulo `content`: taxonomía, rutas, lecciones, preguntas y evaluaciones.

Contrato §1.3, §3.2, §7.4, §7.5, §7.6 y §7.7.

Archivos del paquete:

* `areas.py` — conocimientos, territorios y el mapa del mundo (§7.4).
* `rutas.py` — ciclo de vida de una ruta de aprendizaje (§7.5).
* `modulos.py` — desbloqueo progresivo y estado del mapa de la ruta.
* `lecciones.py` — lección, actividad de estudio, latidos y cierre (§7.6).
* `preguntas.py` — serialización pública de preguntas y muestreo de bancos.
* `correccion.py` — corrección determinista y delegación al juez y al sandbox.
* `evaluaciones.py` — evaluación de módulo: intento, respuestas y envío (§7.7).
* `schemas.py` / `router.py` — contrato HTTP del módulo.

**Tres invariantes que este paquete nunca rompe:**

1. `questions.answer_key` **jamás** sale por la API (§8.7). La única puerta de
   salida de una pregunta es `preguntas.vista_publica()`, que la elimina.
2. Ninguna cantidad de XP, oro o dominio se calcula aquí: toda recompensa pasa por
   `app.modules.gamification.eventos.registrar_evento`, que devuelve el
   `RewardsReceipt` canónico de §7.10 tal cual lo produce el motor.
3. Ningún número de balance es un literal: todo sale de `game_configs` a través de
   `ServicioConfig` (§5, §8.10 regla 5).

**Sobre la dirección de dependencias (§1.3).** El contrato asigna las rutas §7.4,
§7.6 y §7.7 a `content` **+** `progress`: son endpoints compuestos. La composición
vive en la capa de casos de uso de este paquete, que **llama** a los servicios ya
construidos de `progress` (sesiones, dominio, progreso) en lugar de reimplementarlos.
El modelo de datos sigue limpio: `app/models/content.py` no conoce el progreso de
ningún usuario.
"""

from __future__ import annotations

#: Motivos admitidos al reportar contenido (`lesson_blocks.flag_reason`, §3.2).
MOTIVOS_REPORTE: tuple[str, ...] = (
    "incorrect",
    "ambiguous",
    "not_in_material",
    "poorly_written",
    "too_easy",
    "too_hard",
    "other",
)

#: Tipos de contenido que admite `POST /content/report` (§7.6).
TIPOS_REPORTABLES: tuple[str, ...] = ("block", "question")

__all__ = ["MOTIVOS_REPORTE", "TIPOS_REPORTABLES"]
