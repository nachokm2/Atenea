<!-- Estudio del 16-09-2026. Un plan, no una decision tomada: leelo con
     ojo critico y comprueba lo que afirme antes de ejecutarlo. Los numeros
     de linea envejecen. Ver docs/PENDIENTE.md para el contexto. -->

# PLAN — Misiones semanales

## 1. EL VEREDICTO

Existe el catálogo entero (W01–W06 sembradas, `is_active=False`), el motor de avance, expiración, reclamo y pago ya es agnóstico al horizonte, el endpoint ya consulta `scope == WEEKLY` y el cliente ya deserializa y pinta la pestaña; lo único que no existe en todo el proyecto es la función que crea la fila —no hay `asignar_misiones_semanales` ni nada que escriba un `UserMission` con `scope=WEEKLY`— y `missions.weekly.enabled` no lo lee ni un solo `cfg.obtener_bool` de `backend/app/` (verificado: los únicos usos son la propia semilla y dos tests). La sospecha se confirma entera: la consulta de `backend/app/modules/gamification/router.py:272-286` devuelve cero filas en todas las peticiones de todos los usuarios desde que existe el proyecto, y el interruptor de configuración es un cable suelto.

**Dos lectores se equivocaron en el mismo punto, y es el punto que más importa.** La lente Cliente (TRAMPA 3) afirma que `expirar_vencidas` «es el único sitio donde `missions.claim.auto_on_expiry` **paga** las misiones cumplidas», y la lente Diseño de juego que «una semanal completada se autorreclamaría al cerrar la semana, sin tocar nada». Las dos son falsas. `expirar_vencidas` (`backend/app/modules/gamification/misiones.py:599-627`) pone `claimed_at` y `status = CLAIMED` y **no emite ningún evento**; el pago vive exclusivamente en la rama `EventType.MISSION_CLAIMED` del despachador (`backend/app/modules/gamification/motor.py:1170-1171` → `_recompensa_de_mision_reclamada`, `:899`). La lente Servidor lo vio bien. Y no es teórico: `missions.claim.auto_on_expiry` está sembrado en **`True`** (`backend/app/seeds/config_juego.py:1032-1036`), así que hoy, en el móvil de Rodrigo, toda diaria cumplida y no reclamada antes de medianoche se marca reclamada sin pagar nada, y el endpoint de reclamo ya devuelve 409 (`router.py:318-319`). No hay ni una prueba sobre `expirar_vencidas` en `backend/tests` (verificado con grep: cero ficheros).

## 2. LA DECISIÓN: recortarlo, y en dos tiempos separados

**Conectar las seis semanales cuesta bastante más de lo que da. Dilo sin rodeos: hoy no se hace.** El argumento no es el coste de escribir la función —son cuarenta líneas—, es todo lo que arrastra detrás:

- **La economía se mueve sin que nadie lo haya decidido.** El tope blando diario (`xp.daily_softcap`) excluye misiones por comentario explícito en `backend/app/modules/gamification/xp.py:53`. Tres semanales `weekly_default` añaden 900–1.800 XP y 300–600 de oro por semana **por encima del tope**, casi duplicando el ingreso por misiones. Eso no es activar una pestaña, es cambiar el ritmo de progresión y los precios reales de la tienda.
- **Los objetivos semanales son absolutos y el objetivo diario es configurable.** `goal.xp.options = [50, 100, 200, 350]`: quien eligió 50 XP/día no puede cumplir W01 medium (500 XP) ni haciendo la semana perfecta —350—; quien eligió 350 la cumple el martes sin enterarse. No hay forma de arreglarlo sin tocar `resolver_parametros` (`misiones.py:93`), que solo sabe resolver por `tier`, nunca por estado del usuario.
- **Hay un agujero que ninguna lente vio: W03 no tiene nivel `hard`.** `params={"n": {"medium": 1}}` (`backend/app/seeds/misiones.py:325`). Una instancia HARD cae por `valor.get(clave_tier, next(iter(valor.values()), 0))` a target **1**, y cobra `xp.mission_weekly_hard` = 600 XP + 200 de oro por completar **un módulo** en siete días. Sumado a la trampa del tier fantasma (`weekly_default` no tiene `easy`, así que `tier=None` da objetivo medio y recompensa **0/0** en silencio), el catálogo semanal tiene dos formas distintas de producir instancias absurdas sin lanzar una sola excepción.
- **El efecto dominó administrativo.** Claves nuevas en `game_configs` obligan a tocar CONTRACT.md §5.7, la cabecera de `config_juego.py`, `seeds/__init__.py`, `seeds/ejecutar.py` y el recuento exacto de 177 en `backend/tests/seeds/test_semillas.py:28`; el segundo contador obliga a cambiar `MissionsOut` en el contrato (§7.9, CONTRACT.md:3133), el router, el DTO y la pantalla; y `assigned_for = lunes` rompe el panel de Inicio en silencio, porque `ServicioPanel._misiones` (`backend/app/modules/progress/panel.py:643-655`) filtra `assigned_for == hoy` **sin filtrar scope** (verificado): los lunes el aprendiz vería seis misiones en el panel y los martes tres.

Contra todo eso, el valor real: **una** mecánica que el bucle diario no sabe expresar —«cumple tu objetivo 4 de 7 días», la red bajo la racha, que perdona tres fallos cuando la racha no perdona ninguno—. Una mecánica no justifica un segundo horizonte entero.

Así que: **recortar**. Y separar los dos tiempos, porque no son el mismo trabajo:

- **Tiempo 1 (hoy, y no es «semanales»):** cerrar las dos cosas que ya mienten o ya pierden dinero en producción con las semanales apagadas. Esto es exactamente la enfermedad de la sesión y no depende de que exista ninguna semanal.
- **Tiempo 2 (si se quiere, otro día):** una sola semanal fija, W04, detrás del flag. Sin selector ponderado, sin mezcla de tiers, sin antirrepetición. Se mide una pregunta —¿vuelve más gente tras romper la racha?— y si la respuesta es no, lo que se apaga es un booleano.

## 3. EL PASO MÁS PEQUEÑO QUE YA SE NOTA

**Que el autorreclamo pague.** Es la única cosa del frente que hoy le quita algo real al aprendiz, y se arregla sin tocar nada semanal.

Estado verificado:
- `backend/app/modules/gamification/misiones.py:610-621` — con `auto = True`, una misión COMPLETED vencida recibe `claimed_at = instante` y `status = CLAIMED`, y la función devuelve la lista sin emitir nada.
- `backend/app/modules/gamification/motor.py:1170-1171` — el pago solo ocurre al despachar `MISSION_CLAIMED`.
- `backend/app/modules/gamification/router.py:246` — único llamante en toda la aplicación (verificado con grep sobre `backend/app/`).
- `backend/app/modules/gamification/router.py:318-319` — tras el autorreclamo, `claimed_at is not None` hace que el reclamo manual devuelva 409 para siempre.
- `backend/app/modules/gamification/eventos.py:187-189` — `PayloadMissionClaimed` ya declara el campo `auto` con default `False`, y CONTRACT.md §4.2 lo documenta. Alguien previó este caso y nadie lo escribió.

El cambio: que `expirar_vencidas` distinga las autorreclamadas (devolverlas marcadas, o que el llamante filtre `status == CLAIMED and claimed_at == instante`) y que **`listar_misiones`, justo después de la línea 246**, emita por cada una un `registrar_evento(tipo=MISSION_CLAIMED, payload={..., "auto": True}, idempotency_key=clave_derivada("mission-claimed-auto", usuario.id, mision.id))`. La emisión va en el llamante, no dentro de `misiones.py`, por la misma razón por la que hoy emite el motor y no el módulo: mantener `misiones.py` sin saber de eventos. `clave_derivada` ya existe en `motor.py:239` y `registrar_evento` es idempotente por clave (`eventos.py:455-473`), así que reabrir el tablón dos veces no paga dos veces.

Se comprueba sin móvil, con una prueba de integración: crear una diaria, completarla, adelantar el reloj, llamar `GET /missions`, verificar que el monedero subió `reward_xp` y que existe un `DomainEvent` de tipo `MISSION_CLAIMED` con `auto=True`. Hoy esa prueba falla; con el cambio pasa. Y de paso, al escribirla, deja de ser cierto que `expirar_vencidas` no tiene ninguna prueba.

Aviso honesto: la recompensa llegará **sin celebración** —el `ReciboRecompensas` que devuelve `registrar_evento` se descarta, porque `MissionsOut` no lo transporta—. Es mejor que perderla. Encolar la celebración es trabajo aparte y no debe colarse aquí.

## 4. EL RESTO, POR VALOR

**P2 — El pie del tablón deja de mentir. Coste: media hora, solo cliente.**
`app/lib/pantallas/inicio/misiones.dart:132-135` monta `_Reinicio` siempre que `misiones != null`, alimentado con `gami.segundosParaReinicio`, que es `resets_in_seconds` = medianoche local (`misiones.py:642-646`). El `switch` de `:298-300` rotula «La semana cierra» en la pestaña Semanales y «Se revisan» en la de ruta, cuyas misiones tienen `expires_at = None` y no se revisan nunca. Dos frases falsas hoy, en producción, con la pestaña vacía. Mientras no exista un contador semanal de verdad, la salida honesta es **no pintar el pie salvo en la pestaña diaria**. Es un `if` sobre el ámbito.

**P3 — La pestaña «Semanales» deja de ofrecerse. Coste: una hora, solo cliente.**
`_Pestanas` (`misiones.dart:144-165`) itera `AmbitoMision.values` a pelo. `missions.weekly.enabled` ya es `is_public=True`, ya sale en `/config/public`, `ControladorConfigJuego` ya está en el árbol (`app/lib/main.dart:155`) y `ConfigPublica.booleano(clave, porDefecto)` ya existe. Pasar la lista de ámbitos visibles y filtrar la semanal cuando el flag es falso. Con esto el vacío honesto de `:226-229` deja de ser alcanzable, el problema del pie se evapora de paso —y el mismo `if` sirve el día que se encienda, sin volver a tocar nada—.

**P4 — `MissionOut` proyecta lo que el cliente ya sabe pintar. Coste: medio día, contrato + router.**
`_mision_out` (`router.py:219-232`) manda siete campos. El cliente lee y renderiza `description`, `deep_link`, `completed_at`, `claimed_at`, `reward_item`, `learning_path_id`. Consecuencia concreta y presente: sin `deep_link`, el botón «Ir a cumplirla» de la hoja de detalle (`misiones.dart:413-418`) **no se pinta nunca, ni para las diarias**. Es la enfermedad de hoy en el mismo módulo, y beneficia a las diarias tanto como a las hipotéticas semanales. Toca CONTRACT.md §7.9 antes que el router.

**P5 — Los comentarios que mienten. Coste: diez minutos.**
`app/lib/estado/gamificacion.dart:4-6` («las recompensas se otorgan solas en el servidor; `reclamarMision` existe solo para las plantillas que exigen reclamo explícito») y la cabecera de `tarjeta_mision.dart:3-4`. Ninguna de las dos cosas es cierta: `_avanzar_misiones` marca COMPLETED y no paga, y `sePuedeReclamar` es `estado == completada` (`modelos.dart:809`), sin mirar plantilla alguna. Quien planifique las semanales leyendo esos comentarios diseñará un autopago que no existe. Cuesta diez minutos y ahorra una tarde ajena.

**P6 — Una sola semanal, W04, detrás del flag. Coste: dos o tres días bien hechos, y una decisión de producto antes de escribir nada.**
Requiere, en este orden: (a) decidir qué pasa con quien entra a mitad de semana —repartir solo si quedan N días es la única salida que no rompe el título interpolado ni deja seis días en blanco al que se registra un martes—; (b) un ayudante de lunes local en `backend/app/core/time.py`, junto a `day_start_utc` (`:84`), no dentro de `misiones.py`, porque `week_stats`, ACH_PERFECT_WEEK y el evento WEEK_PERFECT lo van a querer; (c) `missions.weekly.count = 1` y `missions.weekly.tier_mix` en `game_configs` —el tier **explícito**, nunca `None`, nunca la mezcla de las diarias, que incluye `easy`—; (d) `asignar_misiones_semanales` con `assigned_for = lunes local` (no `None`: es lo que hace que el único `(user_id, template_id, assigned_for)` garantice la idempotencia, y en Postgres dos NULL no colisionan) y `expires_at = day_start_utc(lunes + 7, zona)`; (e) la llamada desde `listar_misiones` guardada por `cfg.obtener_bool("missions.weekly.enabled")`, sustituyendo la consulta muerta; (f) **filtrar por `scope == DAILY` en `panel.py:646`** en el mismo commit, o el panel muestra seis misiones los lunes y tres los martes; (g) `weekly_resets_in_seconds` en `MissionsOut`, su línea en CONTRACT.md:3133, su lector en el DTO y el pie del tablón revertido; (h) `cuentaAtras` con unidad de días (`app/lib/pantallas/inicio/widgets/formatos.dart:55-66`, hoy devolvería «168 h»); (i) `is_active=True` **solo en W04**; (j) revertir el texto del vacío semanal y actualizar los dos tests que se pondrán rojos a propósito.

**P7 — Lo que queda fuera por ahora, escrito para que no se pierda:** `topic_delta` en el payload de `MASTERY_UPDATED` (`backend/app/modules/progress/dominio.py:1029-1033`), que desbloquearía W06 —y ojo, `topic_before`/`topic_after` son floats y la métrica SUM hace `int(valor or 0)`, así que un delta de 0.07 se convierte en 0—; `reward_item_id` (`backend/app/models/gamification.py:713`), columna que nadie escribe ni lee; y el refresco del tablón al cruzar un límite temporal (`gamificacion.dart:162-163`).

## 5. LAS PRUEBAS

**Sin móvil, ahora mismo (pytest, backend):**
1. **El autorreclamo paga** — diaria completada, reloj adelantado más allá de `expires_at`, `GET /missions`: el monedero sube `reward_xp`/`reward_gold`, existe un `DomainEvent` `MISSION_CLAIMED` con `auto=True`, y la misión queda CLAIMED. Es la prueba que hoy no existe y la que justifica el paso 1.
2. **No paga dos veces** — dos llamadas seguidas a `GET /missions` tras la expiración: un solo evento, un solo cargo. Cubre la clave derivada.
3. **La expirada sin completar no paga** — ACTIVE vencida termina EXPIRED, sin evento y sin XP.
4. **El tier fantasma, como prueba de regresión antes de escribir la función semanal** — `recompensa_de_plantilla(cfg, plantilla_weekly, None)` devuelve `(0, 0)` y `resolver_parametros` devuelve el valor de `medium`. Dejarla escrita fija por contrato el comportamiento que hoy es una trampa silenciosa, y hace imposible que la función nueva nazca con `tier=None` sin que algo se ponga rojo.
5. **W03 en `hard`** — `resolver_parametros` con HARD sobre `{"n": {"medium": 1}}` devuelve 1: la prueba documenta el agujero de balance aunque no se arregle hoy.
6. **Cuando llegue P6:** idempotencia de `asignar_misiones_semanales` (dos `GET /missions` el mismo lunes → una sola tanda, garantizada por el único de la tabla), anclaje al lunes correcto con zona `America/Santiago` cruzando cambio de horario, el flag en `False` produce cero filas, `plantillas_candidatas` recibe `goal_type` (si no, W02 se reparte a todo el mundo duplicando su objetivo diario), y que `panel.py` sigue devolviendo solo diarias un lunes.

**Sin móvil, cliente (flutter test, widget):**
7. El pie no se pinta en las pestañas semanal y de ruta.
8. Con `missions.weekly.enabled = false` en `ConfigPublica`, `_Pestanas` renderiza dos pestañas, no tres.
9. `cuentaAtras(604800)` devuelve días, no «168 h» (solo si se llega a P6).

**Solo con móvil:** que la recompensa del autorreclamo aparezca en el monedero al abrir el tablón por la mañana —el backend se puede probar, pero que el aprendiz lo *vea* sin celebración es una decisión de UX que hay que mirar en pantalla—.

## 6. LO QUE NO HAY QUE HACER

- **No activar `is_active=True` en las seis plantillas.** Ni como prueba, ni «a ver qué pasa». W06 no avanza jamás (`topic_delta` no existe en el payload), W03 en `hard` paga 600 XP por un módulo, W01 es inalcanzable para quien eligió 50 XP/día y W02 se cumple sola por debajo del objetivo por defecto de 20 minutos. Encender seis plantillas es un cambio de economía disfrazado de cambio de interfaz.
- **No tocar `missions.weekly.enabled` a mano en la base de Railway.** `sembrar_configuracion` reescribe cualquier `game_config` cuyo valor difiera de la semilla, así que el cambio se deshace solo en la siguiente corrida del seed y nadie entenderá por qué. El sitio es `backend/app/seeds/config_juego.py:1053`.
- **No instanciar semanales con `assigned_for = None` copiando a las de ruta.** En PostgreSQL dos NULL no colisionan: el único de la tabla no aplica y cada `GET /missions` crearía otra tanda. El tablón se llenaría a razón de una tanda por refresco.
- **No reutilizar `missions.daily.tier_mix` ni pasar `tier=None`.** `weekly_default` no tiene entrada `easy` y `TIERS_VARIEDAD` sí incluye EASY: el resultado es una misión de siete días con objetivo de dificultad media y recompensa de 0 XP y 0 oro, sin excepción, sin log, y con las píldoras de recompensa ocultas en la tarjeta porque valen cero. Es el fallo más probable de todo el frente y el más difícil de ver en una prueba verde.
- **No reabrir el texto del vacío semanal.** Ya se corrigió en esta misma sesión y el comentario de `misiones.dart:221-225` explica por qué se quitó la promesa anterior. Solo se revierte el día que W04 se reparta de verdad.
- **No escribir `asignar_misiones_semanales` sin decidir antes el reparto a mitad de semana.** Es la única regla genuinamente nueva que el horizonte semanal trae, no tiene respuesta obvia, y las tres salidas cambian el código de forma distinta. Elegir después de escribir significa reescribir.
- **No escribir la función y dejarla sin llamar.** Es literalmente la enfermedad que se está cerrando hoy: `_misiones_de_la_ruta` ya vivió esto una vez (`motor.py:1010-1046` documenta la cura). Si el paso 6 no se termina entero —función, llamada, flag, panel, contador, contrato y tests—, no se empieza.
- **No emitir el pago del autorreclamo desde dentro de `misiones.py` sin más.** Ese módulo hoy no sabe de eventos, y el patrón de la casa es que emita el llamante. Si acaba yendo dentro, que sea importación perezosa con `# noqa: PLC0415`, no un import arriba que cierre el ciclo `misiones ↔ eventos`.
- **No dar por buenos los dos comentarios del cliente sobre el autopago.** Están equivocados (P5) y son justo lo que haría a alguien diseñar un autopago redundante en vez de arreglar el que falta.