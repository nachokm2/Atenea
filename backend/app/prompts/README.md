# Plantillas de prompt de Atenea

Los prompts **no viven en el código**: son archivos de texto versionados en esta carpeta
y se siembran en la tabla `prompt_templates` durante el despliegue. Cada generación
guarda qué plantilla usó (`generation_jobs.prompt_template_id` y
`content_provenance.prompt_template_id`), de modo que una lección o una pregunta se
puede auditar y reproducir exactamente.

## Convención de nombre

```
<task_type>.<version>.md
```

- `task_type` es **literalmente** un valor de `JobType` (CONTRACT.md §2): `path_design`,
  `lesson_generation`, `question_generation`, `answer_judgement`, `re_explanation`.
- `version` es la versión semántica libre de `prompt_templates.version` (`v1`, `2026-09-10.1`).

El cargador (`app.modules.ai.proveedor.cargar_plantilla`) elige la versión **mayor** por
orden lexicográfico cuando no se pide una concreta, y calcula el `content_hash`
(SHA-256 del cuerpo) que detecta ediciones no versionadas.

## Reglas vinculantes (CONTRACT.md §8.7)

1. El **material del usuario es entrada no confiable**: nunca va en el `system`.
   Viaja siempre en bloques delimitados `<material>…</material>` del mensaje de usuario.
2. Las llamadas de generación **no llevan herramientas**.
3. Toda salida se valida contra su esquema JSON antes de persistir.
4. Ningún prompt puede otorgar XP, oro ni dominio: esos los calcula el motor de
   gamificación a partir de eventos del servidor, jamás a partir de texto generado.
5. El cuerpo del prompt (`prompt_templates.body`) **nunca** se serializa al cliente.

El cuerpo de cada archivo es el `system` de la llamada: contenido **estable**, apto para
la caché de prefijo (`cache_control`). Lo variable (tema, objetivos, fragmentos) va en el
mensaje de usuario que construye cada módulo de `app/modules/ai/`.
