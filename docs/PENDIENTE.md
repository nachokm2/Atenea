# Pendiente — al 18-09-2026

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
| Pruebas del cliente | **217 verdes** sin contar las dos de contrato vivo, cero saltadas (eran 83 al empezar el 16) |
| Pruebas del servidor | **667 verdes** en la última corrida completa (21-09, antes de la deriva de entorno de más abajo), `ruff check` limpio |
| `flutter analyze` | limpio |
| APK de release | compilado y enviado a Rodrigo a las 02:38 del 18, **con todo lo de la sesión** |
| Producción | desplegada, `/health` en 200 con base y worker `ok`, migración aplicada, arranque sin trazas |

El APK del móvil está al día: incluye el arreglo de la barra de navegación, el
`content_status` del módulo, el rótulo de la prueba y los tres mensajes de
bloqueo. Lo que falta no es compilar, es **mirarlo**: que un módulo escrito ya
no diga «En construcción», que el nodo de la prueba aparezca al final de cada
módulo y que ninguna hoja deje su botón bajo los de Android.

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
autorreclamadas, el `content_status` que impedía abrir lecciones y el del
módulo, el objeto `assessment`, la pista de conocimiento que hacía imposible
crear una ruta, el `deep_link` de las misiones —por el que el botón «Ir a
cumplirla» no se pintó nunca, para ninguna misión—, el `coverage` del tema y
las `coverage_notes` de la ruta —por los que «Saber del Reino» no se pintó
jamás y se acusaba de no traer material a quien no había subido nada—, y el
`chunk_id` de las citas —por el que «Ver fuente» abría una ficha vacía en toda
lección de toda Ruta: el endpoint `GET /chunks/{id}` estaba entero, montado y
sin que nadie lo llamara—.

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

### 3.1 La carrera `resumed`/`paused` — ya con prueba

Estaba anotada como arreglada y sin cubrir, porque montarla exige falsear
`AndroidFlutterLocalNotificationsPlugin` —que el plugin resuelve por tipo
concreto— y abrir a mano la ventana entre las dos ramas.
`test/recordatorio_carrera_test.dart` lo hace: el permiso se controla con un
`Completer`, así que la ventana es exacta en vez de depender de un `pump`
afortunado, y el canal de `flutter_timezone` va falseado porque si no
`iniciar()` no vuelve nunca y la prueba se cuelga sin decir por qué.

**Lo que salió al romper el código, y que no se deduce leyéndolo:** las dos
protecciones son redundantes. Quitar solo `if (_enPrimerPlano)` deja la prueba
verde —la cola serializa y el cancelado corre antes de que `sincronizar`
programe—; quitar solo la cola también —el guard ve `_enPrimerPlano` ya en
falso—. Solo quitando **las dos** se pone roja, con el registro
`[zonedSchedule ×4, cancelAll]`: la cadena cancelada justo después de ponerla.
Cualquiera de las dos sostiene la invariante hoy; quien quite una tiene que
dejar la otra, y esta prueba es lo único que lo impide.

Un detalle del método que costó encontrar: hay que **esperar después de
`paused`** para que la cadena esté ya puesta cuando el permiso contesta. Sin
esa espera, programar y cancelar se resuelven en el mismo puñado de microtareas
y la prueba pasaba incluso con las dos protecciones quitadas. Una prueba de
concurrencia que no controla el entrelazado no prueba nada.

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

### 4.1 Misiones semanales → `docs/planes/misiones-semanales.md` — recortadas

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

**El recorte está hecho (18-09).** La pestaña «Semanales» deja de ofrecerse, y
se lee de `missions.weekly.enabled` —que ya viaja en `/config/public`— en vez de
una constante, para que vuelva sola el día que se reparta una de verdad. El pie
del tablón deja de decir «La semana cierra» y «Se revisan» sobre horizontes que
no cierran ni se revisan: ahora solo se pinta en la pestaña diaria, que es la
única para la que `resets_in_seconds` significa algo. Y se corrigieron los dos
comentarios que afirmaban que cumplir una misión paga sola —no paga: el cobro
vive entero en el reclamo—, que es lo que haría a cualquiera diseñar mal lo
siguiente.

**Lo que no se toca**: las seis plantillas siguen sembradas con
`is_active=False`. Encenderlas es un cambio de economía disfrazado de cambio de
interfaz, y el plan lo argumenta con números.

**Decisión pendiente, y es tuya:** si se paga retroactivamente lo que el
autorreclamo ya se comió. El arreglo cubre de ahí en adelante; las misiones que
figuran `CLAIMED` sin evento no las toca, porque `expirar_vencidas` solo mira
`ACTIVE` y `COMPLETED`. Haría falta un rastreo aparte.

### 4.2 El mapa del Reino → `docs/planes/mapa-del-reino.md` — arreglado

Eran dos huecos hermanos, los dos de la misma familia: **algo que el servidor
ya calculaba y que nadie pedía o nadie mandaba**. Los dos están cerrados.

**El mapa de territorios** (`3515927`). El servidor llevaba desde siempre
sirviendo `GET /territories` con los siete territorios, su estado y su dominio
por usuario, y el cliente tenía repositorio, DTO, enum con etiquetas y widget
del emblema. Nadie llamaba a `repos.conocimiento`: era código muerto entero. Lo
que se veía era un `for (int i = 0; i < 4; i++)` de cuatro siluetas constantes
bajo la frase «Cada ruta que abres ilumina uno», que era verificablemente
falsa. Ahora `ControladorAventura.cargarTerritorios` los pide —con su propio
guard, para que un fallo del mapa no tumbe la pantalla de rutas— y
`MapaDelReino` pinta tantos emblemas como territorios haya. Verificado contra
producción: siete territorios, los siete sellos distintos.

**El desafío del módulo.** Este sí había que construirlo. El nodo mandaba
`assessment_best_score` y `assessment_passed` sueltos —por eso parecía que el
dato estaba— pero no el objeto `assessment`, que es de donde cuelga todo el
dibujo del nodo en el cliente (`ModuloRuta.desdeJson`, y de ahí
`_estiloDesafio`, `ContenidoDesafio` y `_tocarDesafio`). Con `evaluacion` en
`null`, el remate de cada módulo no se pintaba en ninguna ruta, para nadie, sin
dar un solo síntoma: el mapa cargaba bien y con los módulos correctos.

Ahora `ServicioProgreso._evaluaciones_del_mapa` lo construye. Tres decisiones
que vale la pena dejar escritas:

* **Dos consultas para toda la ruta, no una por módulo.** La pantalla de
  entrada del desafío (§7.7) calcula lo mismo con `info_evaluacion`, pero esa
  llama a `asegurar_desbloqueado` y consulta por módulo: reutilizarla habría
  sido N consultas y, peor, habría lanzado en los módulos bloqueados, que son
  justo los que el mapa tiene que poder dibujar apagados.
* **Las reglas no se duplican.** `_usados_hoy`, `_tope_diario` y
  `_enfriamiento_vigente` son funciones puras sobre la lista de intentos y se
  reutilizan tal cual, para que no haya dos verdades sobre el mismo tope.
* **`can_start` mira solo el desafío**, no el bloqueo del módulo: eso ya lo
  dice `status` del nodo. Mezclarlos habría dejado al mapa sin poder
  distinguir «bloqueado» de «hoy ya no te quedan intentos», y el aprendiz
  vería «te queda un intento» sobre un botón mudo.

Contrato en §7.5, `ModuleAssessmentOut` en `content/schemas.py`. Tres pruebas
de servidor —el sobre completo, el tope diario por fecha local y el
enfriamiento— y siete de cliente.

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

**Estado: las 18 armas limpias.** Las piezas de mano secundaria no se tocan.

#### Cómo se cerraron las cinco que faltaban (18-09)

Lo que faltaba para poder decidir era **poder mirar**.
`scripts/revisar_punos.py` compone cada arma como la compone el cliente —el
mismo orden de capas, el mismo `modulate` al teñir—, recorta alrededor de la
mano, amplía ×3 y la pone sobre un gris medio, para que un agujero y el fondo
no se confundan. Sobre el tono **más claro**, que es donde un resto sin teñir
se ve; sobre «Ébano» todo parece oscuro y desaparecen. Y lee los `.webp`
exportados, no el taller: ya pasó una vez que los dos se separaran.

Con eso delante, tres cambios en `quitar_punos.py`, cada uno con su medida:

* **Rellenar los huecos de la máscara del puño** (`_sin_huecos`). Las rayas que
  separan los dedos no son color piel, así que el etiquetado las dejaba fuera y
  el borrado las dejaba en la pieza: en pantalla, trazos marrones curvos junto a
  la empuñadura. Acotado por su propia forma —solo puede añadir lo que el puño
  ya encierra—: entre 0 y 270 px en las dieciocho, y ninguna cambia de camino.
* **`JUNTOS_ALARGAMIENTO = 1.95`**, el 1,8 que estaba suelto dentro de
  `puno_de`. Desbloquea el `arco_fresno` femenino, cuyo puño partido en dorso y
  dedos se junta en 1,897. **No se subió `ALARGAMIENTO_MAXIMO` en su lugar, y
  está medido por qué no**: con 1,85 el arco de fresno masculino pasa de un puño
  bueno de 1.936 px a un trozo de 789, y el `arco_bosque_antiguo` femenino
  —que funcionaba— se queda sin mano. La madera del arco es del color de la piel.
* **`ASTILLA_MAXIMA` de 1.200 a 2.200.** Saca los dos antebrazos que se veían
  como una banda clara cruzando el muslo: 2.038 px en `arco_bosque_antiguo`
  femenino y 1.628 en `cetro_bigquery` femenino. Parecía el cambio peligroso y
  no lo es, y la razón importa: **la guarda que protege la madera no es el
  tamaño, es el color**. Medido pieza a pieza, subir el tope solo absorbe esos
  dos, y los dos están a distancia de color 25 y 2 del puño. Las cuatro piezas
  de madera ni llegan ahí, porque `PIEL_QUE_YA_NO_INFORMA` las corta antes.

Y una regla nueva, **`PUNO_QUE_SUSTITUYE = 1.0`**: un puño que deja muñeca al
aire todavía puede hacer de mano si es al menos tan grande como la que
sustituye. Sale de componer las dos piezas que pasan del tope de muñeca y
mirarlas: el arco femenino (1,77 veces la mano) se ve bien sacado; la espada de
entrenamiento masculina (0,41) se ve **peor** sacada que borrada —el puño sale
roto y con un hueco entre brazo y mano—. Las separan quince píxeles de muñeca
(397 contra 380), así que el tope de muñeca no podía distinguirlas; el tamaño sí,
con un factor cuatro de margen.

#### La última: un puño prestado, sin gastar arte

**`espada_entrenamiento` masculino** agotó las dos salidas del guion. Su puño
mide 954 px, el 0,41 de la mano del cuerpo: sacarlo deja un muñón —compuesto y
mirado: sale roto y con un hueco entre brazo y mano—, y borrarlo entero deja
2.685 px de agujero contra el fondo, con el tope en 1.100.

La salida no era redibujarla: era **prestarle el puño de otra pieza**. Funciona
por una propiedad que no salta a la vista —**todos los puños acaban en el mismo
sitio**, porque cada capa se mueve para que su centro caiga en
`centro_de_la_mano`—, así que el puño de una espada cae exactamente donde está
la empuñadura de la otra. Se compusieron los tres candidatos masculinos y se
miraron: `espada_corta_acero` es el que se asienta bajo el gavilán dejando ver
el pomo. Mide 2.177 px, el 0,93 de la mano del cuerpo.

Va en `PUNO_PRESTADO`, explícito y con su razón. Prestado y no copiado a mano:
el día que se redibuje la pieza se quita esa línea y su propio puño vuelve a
mandar.

**Lo que no se puede limpiar:** quedan 352 px de agujero junto a la empuñadura.
Crecer el borrado los quitaría, pero lo sube a 1.635 —por encima del tope—
porque el puño original sobresale de la silueta de la mano y el prestado no
llega a tapar esa parte. Está medido.

**Y un aviso sobre las pruebas:** con esto, las dos familias declaran por
primera vez la **misma** lista de nueve piezas. Había una prueba que fijaba que
fueran distintas —para justificar el reparto por familia— y se puso roja sin que
nada estuviera mal: fijaba un hecho de ese día, no una regla. Ahora no afirma ni
una cosa ni la otra; lo invariante —que cada familia declare lo exportado para
ella— lo cubren las otras dos.

#### Medido y dejado como está: el puño sale más oscuro que el brazo

Los diecisiete puños salen con más color propio que la piel del cuerpo —croma
25–46 contra 14–20— y más oscuros —media 173–196 contra 229—. Las dos
normalizaciones son **idénticas** (percentil 95 por canal); lo que cambia es la
región: un puño cerrado tiene sombras profundas y el percentil se calcula solo
sobre él.

Las dos correcciones obvias empeoran, y están probadas: igualar la media recorta
entre el 54 % y el 73 % de los píxeles y aplana la mano; corregir solo el tono
baja el croma a 11–20 pero **no mejora la distancia final** —70,6 contra 69,6—
porque lo que se ve es la sombra, no el tinte. Se deja. No es un fallo de la
tubería: es que una mano cerrada está más sombreada que un antebrazo.

#### Un resto de 257 px en el arco de fresno femenino, y por qué se queda

Es la sombra bajo la palma, aislada y a 24 px del puño. La regla que lo
describiría —trozo pequeño, suelto y pegado al puño— se llevaría también los
**brazos del arco**, de 514 y 569 px, que quedan sueltos justo porque el corte
de la mano los separa del asta. Medido: seis candidatos, y tres son arma.

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



### 4.6 `/auth/register` no tenía freno — arreglado

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

**Hecho el 18-09.** `rate_limit_register = "10/minute;60/hour"`, y las dos
ventanas no son adorno: con una sola, diez por minuto siguen siendo catorce mil
cuentas al día. `freno()` acepta ahora varios límites separados por `;` y los
exige todos, y cuenta también la petición que rechaza —quien abusa no recupera
hueco por chocar—.

Lo que costó fue la prueba, y son **las primeras de freno del proyecto**: el
limitador se apaga solo en el entorno de pruebas (`enabled=settings.environment
!= "test"`), porque un caso normal llama veinte veces a la misma ruta en el
mismo segundo. Así que una prueba de freno escrita sin pensarlo pasa con el
freno quitado. Estas lo encienden a mano y le dan una ventana limpia. Además de
que corta al once, fijan que el registro **no comparte cubo con el acceso**: si
lo compartieran, abusar del registro dejaría fuera al aprendiz que solo quiere
entrar, que es justo el daño que el freno viene a evitar.


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

### 4.8 La revisión adversarial del 18-09 — los dieciséis, cerrados

Sobre el nodo de desafío y el arreglo del área segura se lanzó una revisión de
cuatro lentes independientes —agregado, contrato, área segura y calidad de las
pruebas— con un escéptico por hallazgo que intentaba refutarlo ejecutando
código. Diecinueve propuestos, dieciséis sobrevivieron a la refutación, y los
dieciséis están cerrados.

**Arreglados en el momento:**

* **El nodo de módulo no mandaba `content_status`.** El hermano exacto del
  fallo que `255065e` arregló para las lecciones, un nivel más arriba. El
  cliente lo lee, no lo encontraba, caía a `pending`, y `enConstruccion` —que
  `_estiloModulo` comprueba **antes** que «actual» y «disponible»— quedaba
  cierto para siempre: **todos** los módulos se pintaban «En construcción» y al
  tocarlos decían que el Reino todavía los estaba escribiendo. Es exactamente
  la captura que mandó Rodrigo esa noche.
* **Las dos pruebas nuevas de intentos eran una bomba de relojería.** El
  ayudante escribía `local_date` en fecha **UTC** y producción compara contra la
  fecha local del usuario, que en las pruebas es `America/Santiago`. Coincidían
  veintiuna horas al día: la suite se habría puesto roja sola entre las 21:00 y
  las 00:00 de Chile, sin que nadie tocara el código. Y mientras tanto la
  prueba afirmaba en su docstring que demostraba la regla de fecha local (§8.6)
  sin llegar a demostrarla nunca. Ahora el ayudante fecha como fecha producción,
  y hay una prueba que congela el reloj a las 01:30 UTC —22:30 del día anterior
  en Santiago— para que el desfase exista de verdad.
* **El 0 % desaparecía al cambiar de pantalla.** El mapa comprobaba
  `is not None` y la pantalla de entrada la verdad del valor; `Decimal('0.00')`
  es falso en Python, así que quien sacaba cero veía su marca en el mapa y la
  perdía al abrir la prueba. Arreglado en `evaluaciones.py`, que era el lado
  equivocado: un cero es un puntaje real, no «sin marca».
* **El rótulo infringía el contrato.** `CONTRACT.md` prohíbe la palabra
  «Desafío» como nombre visible en dos sitios —línea 1383 y decisión D12—
  porque ya nombra otra actividad, `challenge`, que paga recompensas distintas.
  El nodo escribía «Desafío del módulo» a mano e ignoraba el `title` que llega
  del servidor. Este trabajo es además el que hizo visible la infracción por
  primera vez, porque hasta ahora el nodo no se pintaba.
* **«Completa las lecciones» a quien ya las había completado.** El nodo y el
  diálogo elegían el mensaje mirando solo el enfriamiento, así que el aprendiz
  que había gastado sus intentos del día leía que le faltaban lecciones. §7.5
  separa `can_start` de `status` precisamente para poder distinguirlo, y la
  pantalla lo volvía a mezclar. Ahora son tres mensajes.
* **Cuatro pruebas que no podían fallar.** La fixture del cliente había elegido
  `pass_score: 70`, `max_attempts_per_day: 2` y `title: 'Prueba del módulo'`,
  que son **los tres valores por defecto del constructor**: se podía cablear el
  DTO para que ignorase el JSON entero y seis de las siete seguían verdes. Otra
  fijaba un estado que el servidor no puede producir —`can_start: false` con
  cero intentos y sin enfriamiento— y de paso bendecía el mensaje equivocado
  del estado que sí ocurre. Y el tope diario valía 2 por la columna y por
  `game_configs` a la vez, así que no demostraba cuál manda: ahora hay una
  segunda evaluación que pide 5 y el nodo tiene que seguir diciendo 2.
* **`best_score` y `passed` no los comprobaba nadie** —cablearlos a `None` y
  `False` dejaba 94 pruebas verdes— y el reparto por módulo solo se ejercitaba
  con una única evaluación en toda la ruta.
* **El caso del teclado no tenía red.** Es lo más frágil del arreglo del área
  segura y ocho de las hojas que toca llevan `TextField`. Añadir
  `maintainBottomViewPadding: true` —que suena a mejora y el propio SDK
  documenta como remedio para el salto al abrir el teclado— metía 48 dp de
  vacío bajo cada teclado sin que ninguna prueba lo viera. Ahora sí lo ve:
  comprobado rompiéndolo.

**Los dos hallazgos altos — cerrados también.** Tenían la misma raíz: nada
montaba el mapa de la Ruta en una prueba, porque el camino vivía dentro de
`_PantallaMapaRutaState` y montar esa pantalla exige proveedor, enrutador y una
llamada de red. El coste estaba medido: `if (evaluacion != null && false)` —el
nodo de la prueba no se añade nunca, literalmente el fallo que se acababa de
arreglar— dejaba la suite entera verde, y `_estiloDesafio` devolviendo siempre
`EstiloNodo.disponible` también.

Ahora el camino y las tres reglas de estilo viven en
`app/lib/pantallas/aventura/widgets/camino_ruta.dart`. Las reglas salieron como
**funciones puras** —`estiloDeModulo`, `estiloDeLeccion`, `estiloDeDesafio`—: no
tocan `context` ni estado, así que se comprueban sin montar nada, y son la única
consumidora real de la mitad de `ModuleAssessmentOut`. `CaminoDeLaRuta` decide
qué nodos existen y en qué orden, y se monta de verdad desde el sobre del
servidor. La pantalla se queda con lo suyo: pedir los datos, la cabecera, los
avisos y qué pasa al tocar.

El obstáculo de las animaciones resultó ser menor de lo temido: `PulsoSuave`
(`comunes_aventura.dart:298`) es la única sin fin y solo aparece en el nodo
`actual`. **Basta con `pump()` en vez de `pumpAndSettle()`** —lo que cuelga es
esperar a que se asiente, no montar—. Está dicho en el encabezado de
`test/camino_ruta_test.dart` para que no vuelva a costar siete minutos
averiguarlo.

Diecisiete pruebas nuevas. Verificadas contra las dos mutaciones exactas: la
primera rompe tres, la segunda seis. Antes ninguna de las dos rompía nada.

**Menor, del mismo hallazgo y esto sí sigue abierto:** el nodo de módulo tampoco manda `summary`,
`difficulty`, `estimated_minutes`, `stars` ni `locked_reason`, que el cliente lee
y que existen en `path_modules`. Ninguno bloquea nada —solo esconden adornos—
pero son de la misma familia.

**Descartados tras refutarlos,** anotados para que nadie los vuelva a levantar:
que `can_start` diga que sí sobre una evaluación sin banco (el contrato lo
define así a propósito, y el arranque devuelve 409); que la segunda prueba del
área segura pase igual rota y arreglada (es correcto: comprueba la ausencia de
hueco duplicado, no el arreglo); y que falte una prueba con dos usuarios sobre
la misma evaluación (el código es correcto y el «fallo» solo aparece después de
editarlo).

### 4.9 Un segundo rastreo (21-09) — 10 confirmados, 5 cerrados, 5 abiertos

Mismo patrón de §2, buscado a propósito en cinco direcciones —claves que el
servidor no manda, repositorios y controladores sin llamar, `game_configs`
sembrado y sin leer, lo que el servidor calcula y ninguna pantalla pide, y
frases de la interfaz que afirman algo sin respaldo—, con un escéptico por
hallazgo que intentaba refutarlo ejecutando código. Diecinueve propuestos,
diez confirmados.

**Cerrados:**

* **`coverage` del tema y `coverage_notes` de la ruta** (commit `ce37106`).
  Eran tres hallazgos con la misma raíz: sin `coverage` en el nodo de tema, la
  etiqueta «Saber del Reino» no se pintó jamás, en ningún tema de ninguna
  Ruta —la promesa que el producto repite más veces era la única que no se
  podía comprobar—; y sin `coverage_notes` en `PathDetailOut`, la pantalla de
  generación acusaba a **todo el mundo** de que su material no cubre el
  objetivo, incluido quien no subió un solo documento, sin decir nunca qué
  temas son.
* **`GET /chunks/{id}` sin llamar** (esta sesión). El endpoint estaba entero,
  montado y probado del lado servidor; el cliente tenía el repositorio, el DTO
  `Fragmento` y hasta el diseño para pedirlo bajo demanda —y a propósito bajo
  demanda: mandar título, páginas y texto de cada cita en toda respuesta de
  lección multiplicaría el peso por el número de citas, casi ninguna de las
  cuales se abre—. Faltaba la llamada. `_HojaFuente` la hace ahora al abrirse,
  con esqueleto mientras llega y sin que el fallo de una cita arrastre a las
  demás. Cinco pruebas nuevas.

**Abiertos, por orden de daño:**

1. **La recomendación adaptativa del objetivo diario no la calcula nadie.**
   Tres claves sembradas (`goal.adapt.*`), §6.11 la promete con su fórmula
   exacta, y no hay tarea semanal que la escriba. Quien revienta su objetivo
   todos los días nunca recibe la invitación a subirlo; quien lleva dos
   semanas sin llegar nunca recibe la de bajarlo, que es justo el momento en
   que abandona.
2. **«Qué entra» no aparece antes del Desafío.** `topic_titles` y `rules` no
   viajan en `AssessmentInfoOut`: se entra a una prueba puntuada, con tope de
   intentos por día, sin que la pantalla diga de qué trata ni cuáles son las
   reglas.
3. **Las citas de la re-explicación pierden título y páginas.** Es un hallazgo
   distinto del `GET /chunks/{id}` de arriba: aquí el servidor ya resuelve
   `document_title`, `page_start` y `page_end` en `ai/adaptativo.py` al pedir
   «otra explicación», y su propio esquema de salida (`CitationOut` en
   `content/schemas.py`) los tira porque no los declara.
4. **El ajuste de racha por viaje no se dispara nunca.** La bandera
   `viaje_hacia_el_este` existe como parámetro y su único llamador
   (`motor.py:758`) nunca se lo pasa; el umbral sembrado
   (`streak.tz_change_min_delta_h`) no lo lee nadie. Quien viaja hacia el este
   y pierde un día por el salto horario gasta el día de gracia del mes en vez
   de recibir la protección que el contrato le promete por viajar.
5. **`challenges_per_module_max` no genera ni un desafío**, y el logro
   «Retador/a» queda visible, en la cuadrícula de Logros, con progreso clavado
   en 0/5 · 0/25 · 0/100, inalcanzable para siempre: no existe una sola
   actividad de tipo `challenge` en el juego.

**Sin verificar, no confirmados ni descartados:** cuatro candidatos no
llegaron a pasar por el escéptico —se agotó el límite semanal de la cuenta a
mitad del rastreo—. Entre ellos, uno que suena grave: «Dominio del territorio:
0 % en la cabecera de toda ruta y en toda tarjeta de ruta, para siempre».
No se cuentan como hallazgos hasta comprobarlos.

---

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
- **Instalar el APK** para probar el apartado 3.2. El del 18 a las 02:38 está
  enviado y lleva todo lo de ese día; los arreglos del 21 —`coverage`,
  `coverage_notes`, «Ver fuente»— todavía no están en ningún APK enviado.
  Para recompilar basta `flutter build apk --release`: desde `c49ec5a` ya no
  hace falta `--dart-define=ATENEA_API`, porque la URL de producción por
  defecto es la correcta.

- **El Python del sistema se salió del `requirements.txt` fijado, y no hay
  venv que lo aísle.** `starlette` está pinneado en `0.41.3` y el sistema
  tiene `1.6.0`; `fastapi` en `0.115.6` y el sistema tiene `0.136.0`. Con eso,
  `starlette.testclient` exige un paquete `httpx2` que no está instalado y
  **toda la suite de backend deja de poder recolectarse** —no es un fallo de
  ningún test, es que `pytest` no llega a arrancar—. No pasaba hace unas horas
  en esta misma sesión (667 pruebas verdes), así que algo lo instaló encima
  entretanto: probablemente otro de tus proyectos, ya que este Python no tiene
  venv y lo comparten todos.

  No lo toqué: bajar las versiones del sistema a las que este proyecto fija
  arreglaría Atenea, pero es un Python que usan otros proyectos tuyos y no sé
  qué necesitan ellos de la versión nueva. Dos salidas, y la decisión es tuya:
  reinstalar aquí las versiones fijadas (`pip install -r requirements-dev.txt`)
  sabiendo que puede afectar a lo otro que corra en este mismo Python, o crear
  por fin un entorno virtual propio para Atenea, que es lo que evita que esto
  vuelva a pasar.

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
