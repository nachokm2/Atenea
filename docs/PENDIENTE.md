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

### 4.3 Las dos manos al equipar un arma — arreglado, sin gastar arte

Rodrigo lo encontró en el móvil: al equipar una espada se ven **dos manos**, la
del arma y la suya. Cada pieza empuñada traía un puño dibujado dentro porque al
generarla se le prohibía al modelo tocar las manos existentes y a la vez se le
pedía un arma empuñada.

**La idea que lo resuelve**, y que tardó tres intentos en aparecer: ese puño ya
agarra el arma, con los dedos cerrados sobre la empuñadura, que es algo que la
mano en reposo del cuerpo no sabe hacer. Lo único que le faltaba era ser del
color del aprendiz. Así que no hay que quitarlo: hay que **sacarlo a su propia
capa y teñirlo**, y apagar la mano del cuerpo de ese lado.

Tres piezas, ninguna con coste de API:

1. `scripts/separar_manos.py` saca las manos del cuerpo —y de la capa de piel,
   que se dibuja encima y las repintaba enteras—. Se niega a escribir si
   recomponer no devuelve el original píxel a píxel.
2. `scripts/quitar_punos.py` saca el puño de cada arma a `<pieza>_puno.webp`,
   normalizado para teñir, y corre la pieza hasta la mano de la figura.
3. El cliente tiñe esa capa y apaga la mano del cuerpo. La lista de qué piezas
   la tienen va en `Arte.conPunoPropio`, **por familia**, y la emite el guion.

**Estado: 13 de 18 armas limpias**, 2 con un resto pálido pequeño y 3 que siguen
con dos manos. Las piezas de mano secundaria no se tocan.

#### Lo que se probó y no vale, con sus medidas

Está escrito porque los cuatro parecen razonables hasta que se miden, y porque
tres de ellos se dieron por buenos mirando una hoja de contactos pequeña y
resultaron falsos al ampliar.

| intento | qué pasa | medido |
|---|---|---|
| Borrar el puño y agarrar con la mano del cuerpo | hueco que la mano no tapa: es más pequeña que el puño | asoman 434–2.204 px |
| Taparlo con la mano del cuerpo encima | filo naranja alrededor de una mano oscura | 114–1.071 px |
| Tocar también los escudos | agujero de lado a lado: ahí la mano va pintada **sobre** la cara del escudo y debajo no hay nada | `escudo_blason_reino` inservible |
| Borrar el brazo sobrante también en piezas de madera | se come la vara: el color no distingue madera de piel | `baston_aprendiz` pierde el 11,9 % |

#### Dos trampas del proceso que costaron caro

- **Una hoja de contactos pequeña no sirve para dar algo por bueno.** Tres
  piezas se declararon arregladas y al ampliarlas tenían agujeros. Hay que mirar
  a tamaño real, y sobre el tono de piel por defecto: revisar solo sobre «Ébano»
  hace que todo parezca negro y esconde los restos claros.
- **Un guion que cambia de criterio tiene que restaurar antes de decidir.** Al
  endurecer una regla, `arco_bosque_antiguo` pasó a la lista de las que no se
  tocan y se quedó con el recorte de la versión anterior, porque saltarla
  significaba no volver a escribirla. Ahora restaura desde `_con_puno/` siempre.

#### Lo que falta

Tres piezas necesitan arte nuevo —el arma sin mano, con la empuñadura a la
altura de la mano de la figura—: `arco_bosque_antiguo` masculino y `arco_fresno`
femenino (no se les encuentra puño) y `espada_entrenamiento` masculina (dejaría
615 px de muñeca al aire). Son **tres** generaciones, no treinta.

Las hojas de revisión están en `arte/diagnostico/` (ignorado por git; se
regeneran con los guiones).


### 4.4 Píxel art — explorado y descartado

Rodrigo lo propuso como forma de que los defectos del arte se notaran menos, y
se probó en serio sin gastar una sola generación: conversor con paleta corta,
sombreado plano, contorno de 1 px y alfa dura, y un boceto del Vestidor entero
con la paleta real de la aplicación.

**Decisión: no se cambia. Se mantiene el arte actual.**

Lo que se aprendió, por si vuelve a plantearse:

- **Las dos cosas que se querían se piden a resoluciones opuestas.** A 96-128 px
  los defectos se disuelven pero la `espada_corta_acero` se queda en una hilacha
  de dos píxeles: deja de verse lo que el aprendiz compra. A 256 px las armas se
  leen y el estilo funciona, pero ya no esconde nada.
- **El cuerpo y los iconos de ítem convierten solos y bien.** Las armas finas y
  los escudos no: habría que **redibujarlos** a escala de píxel, y los escudos
  pierden su blasón a cualquier resolución.
- Como razón, además, ya no aplicaba: quedaba **una** pieza de dieciocho con dos
  manos, y se arregló por otra vía.

Si algún día se retoma, que sea como **dirección de arte** y no como parche: el
premio de verdad es que a escala de píxel se controla cada píxel y se acaban los
halos, los flecos de extracción y las manos descuadradas. Los bocetos están en
`arte/diagnostico/boceto_pixel2.png` y `pixel_resoluciones.png`.



### 4.5 La URL de producción no existía — arreglado

`Entorno.apiProduccion` apuntaba a `https://api.atenea.cl/api/v1`. Ese dominio
**no es nuestro**: `atenea.cl` está registrado por «Atenea Gestión Cultural» y
`api.atenea.cl` no resuelve. Cualquier compilación de release sin
`--dart-define=ATENEA_API` salía sin servidor: la aplicación abría, se veía
entera y no cargaba un solo dato.

Ninguna de las ciento cincuenta pruebas lo vio, y no por descuido: **ninguna sale
a la red**, y una constante con una URL dentro no se puede verificar leyéndola.
Ahora hay `test/produccion_existe_test.dart`, con la etiqueta `vivo`: llama al
`/health` de verdad, distingue un fallo de DNS —que es el fallo que busca, y
falla— de un corte de red —que se salta—. Verificada apuntándola al dominio
muerto.

Apunta al dominio que genera Railway, `api-production-66b3.up.railway.app`, y
eso tiene fecha de caducidad: **va atado al servicio**, así que si algún día se
recrea, cambia. Una URL metida en un APK ya instalado no se cambia a distancia.

> **Decidido (17-09-2026): se usa el de Railway y ya está.** Mientras la
> aplicación la instale solo Rodrigo, si el dominio cambiara basta con volver a
> compilar. Lo que convierte esto en un problema no es el tiempo, es **el primer
> aprendiz que no seas tú**: desde ese momento la URL queda congelada en su
> móvil y no se puede cambiar a distancia. Ese es el disparador para comprar un
> dominio propio y añadirlo en Railway, no una fecha.



### 4.6 `/auth/register` no tiene freno — sin arreglar

Salió buscando por qué no se podía registrar una cuenta, y no era eso, pero está
ahí. En `backend/app/modules/identity/router.py`:

- `/auth/login` lleva `Depends(freno(settings.rate_limit_login))`, 10/minuto, y
  el comentario explica muy bien por qué: sin freno, probar contraseñas en masa
  es gratis, y cada intento cuesta un bcrypt de coste 12 sobre un backend
  **síncrono**, así que además de un robo es una denegación de servicio barata.
- **`/auth/register` no lleva ninguna dependencia de freno.** Le aplica solo el
  `rate_limit_default` global, 60/minuto.

Y el argumento del bcrypt vale igual aquí: registrar también hashea. Sesenta
registros por minuto y por IP son sesenta bcrypt de coste 12 en un backend
síncrono, más sesenta filas de usuario. Crear cuentas en masa sale barato.

**Lo que haría falta**, y es de una línea más una prueba: darle su propio freno
—más estricto que el de 60, del orden del de login— y comprobarlo con una prueba
que llame once veces seguidas y espere un 429 en la última. Hoy no hay ninguna
prueba de frenos en el registro.

**Por qué no se arregló al encontrarlo:** con un solo aprendiz usando la
aplicación no hay urgencia, y tocar un freno a ciegas puede dejar fuera a un
usuario legítimo que se equivoca tres veces de contraseña. Decidido el 17-09-2026
anotarlo y hacerlo con calma.


---

### 4.7 La barra de navegación del móvil tapaba los botones — arreglado

Rodrigo lo vio en su teléfono: en la hoja de módulo bloqueado, el botón
«Entendido» quedaba detrás de los tres botones de Android. Se veía, pero al
tocarlo respondía el sistema.

No era un olvido en esa hoja, era una trampa del SDK. `showModalBottomSheet`
acepta `useSafeArea: true` y lo que hace por dentro es
`SafeArea(bottom: false)` —Flutter, `material/bottom_sheet.dart:1119`—: protege
el borde de arriba y los lados y **deja el de abajo descubierto a propósito**.
El nombre del parámetro dice lo contrario de lo que hace.

De las veinticinco hojas de la aplicación, diecisiete se salvaban por casualidad
—traían su propio `SafeArea` dentro—; las ocho de `hojas_aventura.dart` y
`acceso.dart` no. Arreglarlas una a una habría dejado el mismo agujero abierto
para la hoja veintiséis, así que el arreglo va en `mostrarHoja`
(`app/lib/navegacion/armazon.dart`), por donde pasan todas. Va **dentro** del
`Material` de la hoja, de modo que el fondo sigue llegando al borde de la
pantalla y solo se aparta el contenido; y como consume el hueco, las diecisiete
que ya se protegían no ganan aire de más.

El resto de la aplicación estaba cubierto y se comprobó una por una:
`PantallaAtenea` protege el `body` y el `piePersistente` —los ocho pies
persistentes de lección y evaluación pasan por ahí—, `NavigationBar` y
`showDialog` se protegen solos dentro del SDK, y los `Positioned` anclados abajo
que aparecían en la búsqueda resultaron ser ornamentos dentro de tarjetas.

**Por qué ninguna de las ciento sesenta y tres pruebas lo vio:** el dispositivo
de pruebas no tiene barras del sistema, así que `SafeArea` no aparta nada y
todo mide exactamente igual roto que arreglado. `test/area_segura_test.dart`
finge la barra con `tester.view.padding` y mide la posición real en pantalla.
Comprobado rompiendo el arreglo: el «Entendido» terminaba en 891 dp con la
línea de seguridad en 867, o sea veinticuatro dentro de la barra —la mitad del
botón, que es justo lo que se ve en la captura.

## 5. Lo que depende de Rodrigo, no del código

- **Una cuenta de prueba creada por error con el correo de Rodrigo.** Probando
  qué devuelve `/auth/register` con distintos casos, uno usó
  `rodrigo.palma@uautonoma.cl` y respondió 201: el correo no estaba registrado y
  ahora sí, con la contraseña `Prueba12345!`. Está en producción. O se entra y
  se le cambia la contraseña, o se borra para poder registrarse desde cero.
  Debió usarse un correo de prueba.

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
