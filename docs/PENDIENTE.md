# Pendiente — al 17-09-2026

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
| Pruebas del cliente | **142 verdes**, cero saltadas (eran 83 al empezar el 16) |
| Pruebas del servidor | **verde entera**, `ruff` limpio |
| `flutter analyze` | limpio |
| APK de release | compila y está firmado |
| Producción | desplegada y al día con `main` |

Las dos pruebas de contrato vivo se saltan solas si la API local no responde, y
son justo las que comprueban que cliente y servidor hablan el mismo idioma. Para
que corran: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` desde
`backend/`, con el contenedor `atenea-db` levantado.

---

## 2. El hilo que recorre todo esto: lo que se ofrece y nadie ejecuta

Conviene tenerlo en la cabeza porque **quedan casos sin buscar**. El patrón es
siempre idéntico:

> Algo se ofrece, se guarda y viaja entero por las capas, y **nadie lo lee jamás
> para decidir nada**. Ninguna prueba lo nota, porque todas comprueban la mitad
> que sí funciona.

Cerrados hasta ahora: la vibración, «Sonido», «Idioma del contenido», el registro
de push, los ocho peinados de la creación del héroe, el cobro de las misiones
autorreclamadas y el `content_status` que impedía abrir lecciones.

**Cómo buscar el siguiente**: coger un campo que la interfaz ofrezca, hacer
`grep` de su nombre, y mirar si aparece en algún sitio que no sea el DTO, el
repositorio, el estado y la pantalla que lo pinta. Si no aparece, es otro caso.

---

## 3. El recordatorio local — escrito, conectado y revisado

Una revisión adversarial de 109 agentes levantó 34 posibles fallos; once
sobrevivieron a tres escépticos. De esos, **tres los verifiqué leyendo el código
y cuatro más pasaron por una segunda verificación con contraste**. Todos los
reales están arreglados (commits `f82377e` y `cb8ddc2`).

Lo que se cerró, para que nadie lo vuelva a reportar:

| Fallo | Estado |
|---|---|
| La invariante se rompía en arranque en frío | arreglado |
| `add(Duration(days: n))` fallaba el día del cambio de hora (en dos sitios) | arreglado |
| Dos avisos en el mismo instante con silencio diurno | arreglado |
| Un fallo del plugin dejaba Atenea sin arrancar | arreglado |
| Lo mismo con un almacén de claves corrupto | arreglado |
| `resumed` y `paused` se entrelazaban | arreglado |
| El espejo perdía las horas del Reino al reentrar | arreglado |
| Un reinicio resucita avisos ya vistos | **falso**, verificado en el Java del plugin |
| `tomarDestino()` deja el toque sin destino | **falso**, el enrutador lleva a Inicio igual |

### 3.1 Lo que sigue sin cubrir, y por qué

**La carrera entre `resumed` y `paused` está arreglada pero sin prueba.**
Montarla exige falsear `AndroidFlutterLocalNotificationsPlugin`, que el plugin
resuelve por tipo concreto; sin él el permiso sale `false`, la cadena sale vacía
y la carrera no se puede provocar. La vía sería un *mock* del canal
`dexterous.com/flutter/local_notifications` con
`setMockMethodCallHandler`, devolviendo `areNotificationsEnabled` con retardo
para abrir la ventana a mano. Está anotado aquí en vez de fingir cobertura con
una prueba que pasaría siempre.

### 3.2 Lo que solo se puede comprobar en el móvil

Con el APK instalado, en este orden:

1. Ajustes → **Recordatorios en el móvil** → encender. **Android tiene que pedir
   permiso.** Si no lo pide, algo va mal antes de todo lo demás.
2. Negarlo a propósito: el interruptor debe quedarse apagado, aparecer la fila
   «Abrir los ajustes de Android», y **no debe guardarse nada en el servidor**.
3. Concederlo, poner la hora del recordatorio cerca, y **cerrar Atenea del
   todo**. Con la aplicación abierta no suena, y eso es a propósito.
4. Al tocar el aviso, Atenea abre en Inicio.
5. Que el icono de la barra de estado sea el escudo y no una mancha blanca.

---

## 4. Los huecos que quedan del proyecto

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

Lo que sí salió de este frente —que el autorreclamo no pagaba— **ya está
arreglado** (`c75da6e`). No tenía nada de semanal.

**Decisión pendiente, y es tuya:** si se paga retroactivamente lo que el
autorreclamo ya se comió. El arreglo cubre de ahí en adelante; las misiones que
figuran `CLAIMED` sin evento no las toca, porque `expirar_vencidas` solo mira
`ACTIVE` y `COMPLETED`. Haría falta un rastreo aparte.

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

> Lo del `content_status` que este plan señalaba —que ninguna lección se podía
> abrir desde el mapa de la Ruta— era cierto y **ya está arreglado** (`255065e`).
>
> **Queda un hueco hermano, sin verificar:** el nodo de módulo no manda
> `assessment`, así que el desafío no se pinta en el mapa. Es más grande que el
> anterior: el dato no existe en el agregado, hay que construirlo.

### 4.3 Las dos manos al equipar un arma — medido, a medias

Rodrigo lo encontró en el móvil: al equipar una espada se ven **dos manos**, la
del arma y la suya. Cada pieza empuñada trae su propio puño dibujado porque al
generarla se le prohibía al modelo tocar las manos existentes y a la vez se le
pedía un arma empuñada; obedecer a las dos cosas solo se puede dibujando un puño
nuevo.

**Hecho y subido:** el cuerpo se dibuja en tres piezas —tronco sin manos y cada
mano por su lado— y la capa de piel igual, que es la que hace falta para poder
apagar una mano. `scripts/separar_manos.py` las deriva sin gastar API y se niega
a escribir si recomponer las tres no devuelve el original píxel a píxel. Hoy se
dibujan siempre las dos, así que **en pantalla no ha cambiado nada**: es la
infraestructura, no el arreglo.

**Por qué no se apaga todavía**, que es lo que no se deduce del código. Se
compuso la pila fuera de la aplicación y se miró (`arte/diagnostico/`):

1. El puño del arma **no cae donde está la mano**. Hace falta mover la pieza
   entre 133 px hacia arriba y 184 px hacia abajo según cuál sea, y no hay
   constante posible: cada una lo puso donde quiso. Apagar la mano sin mover el
   arma deja el antebrazo **cortado en seco** con el puño flotando aparte.
2. Aunque encajara, ese puño va pintado dentro del arma y **no se tiñe**. Mide
   entre 0,29 y 5,47 veces la mano del cuerpo. Sobre la piel «Ébano» es un puño
   naranja en un brazo marrón oscuro: los seis tonos de piel volverían a ser
   seis tonos que no se aplican a todo.

**Lo que sí funciona, probado en cuatro piezas:** borrar el puño del arma,
mover la pieza para que la empuñadura caiga en la mano, y dibujar la mano del
cuerpo **por encima**. Entonces agarra ella, y se tiñe. Se ve en
`arte/diagnostico/tres_caminos.png`.

**Dónde se atasca:** borrar el puño se hace por color, y la madera es del mismo
color que la piel. En `baston_aprendiz` el 78 % de la pieza da «piel» por color y
en `arco_fresno` el 66 %; en las espadas y cetros, del 15 al 23 %. Borrar por
color arregla el metal y **destruiría el arco y el bastón**.

Dos salidas, y la elección es de Rodrigo porque una cuesta dinero:

- **Regenerar las 30 piezas sin puño**, con la empuñadura en el sitio de la mano.
  Limpio y definitivo, y el arte por capas queda bien para siempre. Cuesta ~30
  generaciones más las que se repitan.
- **Afinar el borrado sin gastar**: distinguir el puño de la madera por forma y
  no por color —un puño es compacto, una vara es alargada—. Gratis, pero no hay
  garantía de que salga en las seis piezas de madera.

Medidas, guiones de diagnóstico y las imágenes están en `arte/diagnostico/`.

---

## 5. Lo que depende de Rodrigo, no del código

- **`ALERT_EMAIL` sin poner en Railway.** La alerta de presupuesto de IA está
  bien escrita —sin destinatario marca el evento `SKIPPED` y avisa en el
  registro, no se pierde en silencio— pero no sale de la máquina. Railway →
  servicio `api` → Variables → `ALERT_EMAIL` = un correo. No hay código que
  tocar.
- **Instalar el APK** para probar el apartado 3.2. Hay que recompilarlo: el que
  hay en `app/build/` es del 16 y no lleva nada de hoy.
  `flutter build apk --release --dart-define=ATENEA_API=…` — la orden completa
  está en el `README.md`.

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
