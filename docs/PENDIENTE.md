# Pendiente — al cerrar el 16-09-2026

Este archivo existe para que mañana se retome sin releer una conversación. Dice
qué quedó hecho, qué quedó a medias y **por qué**, que es lo que no se deduce
mirando el código.

Se actualiza o se borra cuando deje de ser cierto. Un documento de traspaso que
sobrevive a su sesión es otra cosa que promete y no cumple.

---

## 1. Dónde quedó todo, verificado

| | |
|---|---|
| Rama | `main`, todo subido a `origin` |
| Pruebas del cliente | **120 verdes** (eran 83 al empezar el día) |
| Pruebas del servidor | **636 verdes** |
| `flutter analyze` | limpio |
| APK de release | compila y está firmado; el icono de aviso verificado dentro del `resources.arsc` |
| Producción | desplegada; `/health` responde `worker: ok` |

Commits del día, en orden:

- `c4cc7a8` — Ajustes deja de prometer lo que nadie cumple, y el móvil aprende a avisar
- `bc337b9` — La hora que Ajustes promete es la hora a la que el Reino avisa
- `2f5d385` — El espejo del recordatorio se borra al cerrar sesión
- `0396608` — La creación del héroe deja de ofrecer ocho peinados que no se dibujan

---

## 1.bis — LO PRIMERO DE MAÑANA: el Reino se queda con recompensas ya ganadas

Esto no es deuda futura. **Está pasando en producción ahora mismo**, y lo
verifiqué línea a línea antes de escribirlo.

`missions.claim.auto_on_expiry` está sembrado en `True`
(`backend/app/seeds/config_juego.py:1032`), y su descripción dice «al expirar el
periodo se reclaman solas las misiones completadas». Pero
`expirar_vencidas` (`backend/app/modules/gamification/misiones.py:618-620`) pone
`claimed_at` y `status = CLAIMED` **a mano, sin emitir ningún evento**, y el pago
vive exclusivamente en la rama `MISSION_CLAIMED` del despachador
(`motor.py:1170`), que solo se emite desde el endpoint de reclamo
(`router.py:326`).

Consecuencia, para un aprendiz cualquiera: cumple una misión diaria, no la
reclama antes de medianoche, y al día siguiente la misión figura **reclamada**
sin haberle pagado ni un punto de experiencia ni una moneda. Si intenta
reclamarla, `router.py:319` le devuelve un 409: «Esta misión todavía no se puede
reclamar».

Dos detalles que confirman que es un olvido y no una decisión:

- El payload del evento de reclamo lleva un campo `"auto": False`
  (`router.py:328`). Alguien previó la vía automática y nunca la escribió.
- **No hay una sola prueba sobre `expirar_vencidas`** en todo `backend/tests`.

*Arreglo:* que `expirar_vencidas` emita `MISSION_CLAIMED` con `auto: True` y su
clave de idempotencia, como hace el endpoint. Antes de tocarlo hay que decidir si
se paga retroactivamente lo ya perdido, que es una decisión de producto y no de
código.

Es la misma enfermedad del apartado 2 —algo que se promete y nadie ejecuta—,
solo que aquí el precio lo paga el aprendiz.

---

## 2. El hilo del día: lo que se ofrece y nadie ejecuta

Todo el trabajo de hoy persigue una sola enfermedad, y conviene tenerla en la
cabeza porque **quedan casos sin buscar**. El patrón es siempre idéntico:

> Un valor viaja entero por las cuatro capas del cliente —DTO, repositorio,
> sesión, pantalla—, se guarda en el servidor, y **nadie lo lee jamás para
> decidir nada**. Ninguna prueba lo nota, porque todas comprueban la mitad que
> sí funciona: que se guarde.

Cerrados hoy: la vibración (vibraba siempre y el interruptor no la tocaba),
«Sonido» (cero audio en todo el repositorio), «Idioma del contenido» (nadie leía
`content_language`), el registro de push (código muerto que además daba 422), y
los ocho peinados de la creación del héroe.

**Cómo buscar el siguiente**: coger un campo de `Ajustes` o de `RasgosAvatar`,
hacer `grep` de su nombre en `app/lib`, y mirar si aparece en algún sitio que no
sea `dtos.dart`, `repositorios.dart`, `sesion.dart` y la pantalla que lo pinta.
Si no aparece, es otro caso.

---

## 3. El recordatorio local — escrito, conectado y con fallos conocidos

Funciona de punta a punta: el interruptor pide permiso de verdad, la cadena se
programa al cerrar la aplicación y se cancela al abrirla. **Pero no está
probado en un teléfono**, y una revisión adversarial de 109 agentes encontró 34
posibles fallos, de los que 11 sobrevivieron a tres escépticos cada uno.

La lista completa en bruto está en el diario del flujo:
`~/.claude/projects/…/subagents/workflows/wf_7e001aab-34c/journal.jsonl`

### 3.1 Los que verifiqué yo mismo leyendo el código

Estos tres no son sospechas. Son ciertos.

**A. La invariante se rompe en el arranque en frío.**
`app/lib/nucleo/recordatorio_local.dart:155`

`iniciar()` registra el observador del ciclo de vida, pero
`didChangeAppLifecycleState` solo dispara en **cambios**: un arranque en frío
nunca entrega un `resumed`. Así que la cadena programada anoche sigue armada
mientras el aprendiz está dentro de Atenea, y puede sonar un aviso diciendo «en
este teléfono todavía no hay práctica de hoy» con la aplicación abierta delante.

Es justo la invariante que sostiene que los textos sean ciertos.

*Arreglo:* cancelar la cadena al final de `iniciar()`, sin esperar a un
`resumed` que no va a llegar.

**B. El día del cambio de hora, el aviso de mañana cae en el día de hoy.**
`app/lib/nucleo/plan_recordatorio.dart:319`

`hoy.add(Duration(days: k))` suma 24 horas **absolutas**. El domingo de otoño en
que los relojes atrasan, el día dura 25 horas: medianoche + 24 h es las 23:00
del **mismo día**, así que `k = 1` construye otra vez la fecha de hoy y choca
con `k = 0`. Chile cambia la hora, así que esto pasa dos veces al año.

*Arreglo:* construir la fecha por partes —`DateTime(hoy.year, hoy.month,
hoy.day + k)`—, que normaliza el calendario sin tocar el reloj.

**C. Dos avisos en el mismo instante con silencio diurno.**
`app/lib/nucleo/plan_recordatorio.dart:341`

Con horas de silencio que **no** cruzan la medianoche —12:00 a 22:00, el turno
de noche— y la hora del recordatorio a las 13:00: el aviso del día cae dentro
del silencio y se corre a las 22:00; la última llamada de las 21:30 también cae
dentro y se corre a las 22:00. La regla 5 no los descarta porque ninguno cambia
de día.

Dos notificaciones simultáneas diciendo cosas distintas. Y el margen de la
regla 6 no protege, porque solo se aplica cuando la franja cruza la medianoche
—una limitación que dejé escrita en el comentario dando por hecho que bastaba.

*Arreglo:* una voz por instante. Al final de `planificarCadena`, descartar todo
aviso que caiga en el mismo instante que otro anterior.

### 3.2 Los graves que la revisión marcó y no llegué a verificar

Leerlos antes de creerlos. Cada uno lleva el sitio que la revisión citó.

- **El espejo se queda sin las horas del Reino al volver a entrar.**
  `app/lib/main.dart:95`. `config.cargar()` vuelve enseguida si ya tiene
  configuración, pero `olvidar()` borró el espejo al cerrar sesión. Resultado:
  sin `horaPorDefecto`, y la cadena devuelve lista vacía por la regla 2.
- **Cerrar sesión y volver a entrar sin reiniciar deja el espejo a medias.**
  `app/lib/nucleo/recordatorio_local.dart:294`.
- **Un reinicio del teléfono o una actualización de Play resucitan avisos ya
  vistos.** `AndroidManifest.xml:78`. El receptor de arranque reprograma lo que
  había, sin saber si el aprendiz ya abrió la aplicación.
- **`tomarDestino()` no tiene ni un consumidor.** `recordatorio_local.dart:432`.
  El toque en el aviso se guarda y nadie lo recoge, así que el enlace profundo
  no lleva a ningún sitio. *Esto es exactamente la enfermedad del apartado 2,
  recién introducida por mí.*
- **`resumed` y `paused` no se serializan.** `recordatorio_local.dart:397`. Un
  ir y volver rápido puede dejar la cadena armada con Atenea en primer plano, o
  borrar la que se acaba de programar.
- **Una excepción de plataforma en `iniciar()` revienta el `Future.wait`** de
  `main.dart` y con él el arranque entero. `recordatorio_local.dart:114`.

### 3.3 Pruebas que la revisión echó en falta

Todas se pueden escribir sin un teléfono:

1. Que al volver a primer plano se cancele la cadena —la invariante central, hoy
   sin cubrir.
2. Que si Android niega el permiso **no se escriba nada en el servidor**. Es el
   fallo que todo este trabajo vino a corregir y no lo comprueba nadie.
3. Que las cuatro horas del Reino salgan de verdad por `GET /config/public`
   (`backend/tests/gamification/`).

### 3.4 Lo que solo se puede comprobar en el móvil

Con el APK instalado, en este orden:

1. Ajustes → **Recordatorios en el móvil** → encender. **Android tiene que pedir
   permiso.** Si no lo pide, algo va mal antes de todo lo demás.
2. Negarlo a propósito: el interruptor debe quedarse apagado, aparecer la fila
   «Abrir los ajustes de Android», y **no debe guardarse nada en el servidor**.
3. Concederlo, poner la hora del recordatorio cerca, y **cerrar Atenea del
   todo**. Con la aplicación abierta no suena, y eso es a propósito.
4. Al tocar el aviso debería abrirse Atenea en Inicio. *Hoy probablemente no
   navegue: ver `tomarDestino()` en 3.2.*
5. Comprobar que el icono de la barra de estado es el escudo y no una mancha
   blanca.

---

## 4. Los dos huecos que quedan del proyecto

Estudiados hoy en paralelo. **Los planes completos están en `docs/planes/`** —
son largos, concretos y citan fichero y línea. Aquí solo el veredicto.

### 4.1 Misiones semanales → `docs/planes/misiones-semanales.md`

**Recortar, no conectar.** La sospecha se confirma entera: existe el catálogo
(W01–W06 sembradas con `is_active=False`), el motor de avance y pago ya es
agnóstico al horizonte, el endpoint ya consulta `scope == WEEKLY` y el cliente
ya pinta la pestaña. Lo único que no existe en todo el proyecto es la función
que crea la fila.

Pero conectarlas cuesta mucho más de lo que dan, y el plan lo argumenta con
números: mueve la economía por encima del tope blando diario sin que nadie lo
haya decidido, los objetivos semanales son absolutos mientras el diario es
configurable —quien eligió 50 XP/día no puede cumplir W01 ni con la semana
perfecta—, y W03 no tiene nivel `hard`, así que una instancia difícil paga 600
XP por completar **un** módulo en siete días.

Lo que sí sale de este frente es el apartado 1.bis, que no tiene nada de
semanal y está costando recompensas hoy.

### 4.2 El mapa del Reino → `docs/planes/mapa-del-reino.md`

**Conectar, y es barato.** Aquí no hay que construir nada: el servidor ya sirve
`GET /api/v1/territories` con siete territorios, su estado y su dominio
calculados por usuario, y el cliente tiene el repositorio, el DTO, el enum con
etiquetas en español y hasta el widget del emblema. **Falta la llamada**: nadie
invoca `repos.conocimiento` en toda la aplicación.

Lo que se ve en pantalla hoy es un `for (int i = 0; i < 4; i++)` de cuatro
siluetas constantes bajo la frase «Cada ruta que abres ilumina uno» —una frase
verificablemente falsa sobre datos que el servidor ya calcula. Conectarlo son
unas 60 líneas de cliente, cero backend, cero contrato.

> **Antes que nada, comprobar esto:** el plan afirma que `content_status` en los
> tres nodos del mapa de la Ruta (P07) **impide abrir cualquier lección desde
> ahí**, y que se arregla con tres líneas de backend. No lo verifiqué. Si es
> cierto, va antes que todo lo demás de este documento salvo el 1.bis.

---

## 5. Lo que depende de Rodrigo, no del código

- **`ALERT_EMAIL` sin poner en Railway.** La alerta de presupuesto de IA está
  bien escrita —sin destinatario marca el evento `SKIPPED` y avisa en el
  registro, no se pierde en silencio— pero no sale de la máquina. Railway →
  servicio `api` → Variables → `ALERT_EMAIL` = un correo. No hay código que
  tocar.
- **Instalar el APK** de `app/build/app/outputs/flutter-apk/app-release.apk`
  para probar el apartado 3.4.

---

## 6. Sobre los flujos de revisión

Dos avisos para quien los vuelva a lanzar:

- **Los agentes escriben ficheros en el repositorio si no se les prohíbe.** Dos
  pruebas temporales (`_tmp_refutacion_test.dart`, `zz_verificacion_temp_test.dart`)
  acabaron dentro de un commit por un `git add -A`. En los flujos nuevos va la
  prohibición explícita.
- **`agent()` recibe texto, no listas.** Pasarle un array manda `[object]` al
  agente, que responde que no recibió tarea. Se pierde la síntesis y no el
  trabajo: los resultados individuales siguen en `journal.jsonl`.
