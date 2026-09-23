<!-- Plan aprobado el 23-09-2026, revisado el mismo día tras probar la Fase 0
     en un dispositivo real. Los números de línea envejecen; comprueba antes
     de ejecutar sobre ellos. Ver docs/planes/mapa-del-reino.md para el frente
     que este plan revierte en parte (P07, no P22). -->

# PLAN — Un mundo caminable en P07 (Ruta), con una figura hecha para animarse

## 1. Por qué existe, y por qué cambió

Rodrigo encontró [sprite-gen](https://github.com/aldegad/sprite-gen) buscando
mejorar el arte de personajes y, al ver sus demos animadas, pidió personajes
**animados**. Decidió — sabiendo el costo real — la opción más grande: que el
mapa de **Ruta (P07)** deje de ser una lista de nodos y se convierta en un
mundo 2D donde el avatar equipado camina de verdad entre módulos.

Esto revierte a propósito, y solo en parte, la decisión de
`docs/planes/mapa-del-reino.md` (16-09) de no dibujar un mapa navegable — pero
esa decisión hablaba de la **grilla de Territorios (P22)**, que de verdad no
tiene datos de posición ni adyacencia. Ruta es un caso distinto: **sí** tiene
orden y adyacencia reales en el backend.

**La Fase 0 se ejecutó de verdad y cambió la Parte B del plan.** El primer
diseño (un rig de recortes/rotaciones sobre el arte detallado ya existente,
"sin arte nuevo") se probó en tres variantes distintas, todas en el teléfono
real de Rodrigo, y las tres fallaron:

1. Recortar rectángulos del arte real y rotarlos sobre pivotes medidos
   (`ClipRect`+`Transform.rotate`) — el hombro corta el torso al girar, porque
   brazo y torso son una sola silueta conexa en este dibujo (medido con
   `scipy.ndimage.label`: sin hueco real, a diferencia de la entrepierna).
2. Regenerar el arte para darle al hombro un hueco real (edición con máscara
   vía `gpt-image-2`/`images/edits`) — el hombro mejoró, pero **la cadera, que
   siempre tuvo un hueco real, seguía cortándose igual**. Esto prueba que el
   problema no era (solo) la falta de hueco: un rectángulo rígido que gira no
   sigue la curva del cuerpo contra un vecino que no gira, tenga o no tenga
   hueco real la silueta de abajo.
3. Parches fijos de refuerzo en las costuras — se ven como lo que son:
   rectángulos pegados, con su propio borde visible.

Veredicto de Rodrigo, textual: *"se mueve como marioneta"* / *"para que la
tiraran con hilos"*. Un `ClipPath` con la silueta real tendría el mismo
problema de fondo (la silueta gira con el miembro; el vecino fijo no), así
que no se intentó como cuarta variante.

**Decisión, con toda esa evidencia encima:** invertir de verdad en una figura
separada y simplificada, dibujada desde cero para animarse — el "Plan B" que
este mismo documento ya contemplaba como salida de emergencia, ahora
promovido a plan principal. Y revivir el mundo caminable con esa figura real
en vez de un disco de color, porque la hipótesis de Rodrigo es que el disco
—no el sendero— fue lo que se sintió vacío.

`sprite-gen` en sí **sigue sin usarse**: es generación de fotogramas por IA
(costo recurrente por cada ítem nuevo del catálogo) y su propia documentación
marca el ciclo de caminar como experimental, probado en mascotas compactas,
no en ilustraciones detalladas como las de Atenea.

## 2. Lo verificado

- **El mundo caminable de Ruta no necesita ningún cambio de backend.** El
  orden (`PathModule.position`, `prerequisite_module_id`) y el candado (la
  evaluación del módulo, regla A7, `backend/app/modules/progress/progreso.py`)
  ya existen y ya se aplican en el servidor.
- **El personaje siempre mira de frente** — no hay vista de perfil ni de
  espalda en el arte, y la figura del mundo hereda la misma limitación por
  diseño: izquierda/derecha es un espejo horizontal, nunca un giro.

## 3. Parte A — El mundo caminable (sin cambios de diseño)

**Ya construido y probado**, sigue en pie sin cambios:
`app/lib/pantallas/aventura/mundo/senda.dart` (geometría pura — la posición
de la parada `i` es función de `i` sola, nunca del total), `pintor_senda.dart`
(el trazo y los portones) y `experimento_mundo.dart` (el spike de la Fase 0a,
con un disco de color como caminante — sigue en el repo, gateado a
`kDebugMode`, enlazado desde Ajustes → Herramientas del Reino).

**Pendiente para producción:** reemplazar `CaminoDeLaRuta` en `mapa_ruta.dart`
por el mundo real, con el `Caminante` de la Parte B en vez del disco.
`_Cabecera` de `mapa_ruta.dart` (dominio, lecciones completadas, duración
estimada) no puede desaparecer en silencio.

## 4. Parte B — La figura del mundo: una identidad de arte separada

### Por qué esta vez sí converge

La ilustración detallada actual tiene identidad que preservar en cada capa
(cara, tono de piel, pelo, 92 piezas con fidelidad individual) — por eso cada
intento de riggearla terminó recortando algo que no debía cortarse. La figura
del mundo se diseña **sin esa identidad**: sin rasgos de cara, sin pelo
suelto, sin tono de piel — una silueta simplificada por Orden y familia, con
el rostro en sombra bajo capucha o yelmo. Es un diseño, no un atajo: permite
generar un número chico de láminas que cubren a todos, y hace que el ciclo
completo se genere **de una sola llamada**, sin tropezar con el fallo ya
documentado del modelo ("dándole el lienzo entero dibujó otra persona").

### Qué representa, y qué no

**Cuerpo = Orden × familia.** Cuatro Órdenes tienen kit inicial hoy
(`backend/app/seeds/items.py`): Acero, Arcano, Bosque, Muro (de las 8 del
enum `Arquetipo`, `app/lib/datos/modelos.dart:120-128`). Dos familias. 4 × 2
= **8 láminas de cuerpo**.

**Lo empuñado = un prop estático**, no parte de la lámina de cuerpo. Los
fotogramas se generan con las manos cerradas en puño y vacías; el arma o
escudo es una sola imagen por **clase**, compuesta en el ancla de mano medida
por fotograma.

**Estado: la taxonomía y su fontanería en el servidor ya están hechas**
(23-09-2026). Seis clases (`WorldWeaponClass`,
`backend/app/models/enums.py`) cubren los 17 ítems empuñados reales:

| Mano | Clase | Ítems |
|---|---|---|
| diestra | `blade` | espada_entrenamiento, espada_corta_acero, espada_obsidiana, espada_del_sql |
| diestra | `bow` | arco_fresno, arco_bosque_antiguo |
| diestra | `staff` | baston_aprendiz, cetro_bigquery, baculo_maestria_ia |
| diestra | `torch` | antorcha_constancia |
| zurda | `shield` | escudo_madera, escudo_roble, escudo_blason_reino, escudo_data_engineer, escudo_primer_desafio |
| zurda | `tome` | tomo_erudito (no es un escudo — su propia clase) |

`pluma_primer_paso` no entra en ninguna clase a propósito (a 8dp es
invisible). El dato vive en `items.render_manifest["world_class"]` (JSONB, sin
migración), asignado en la semilla vía `manifiesto(..., clase_mundo=...)`, y
se emite en dos sitios reales — `equipment[slot].world_class` **y**
`layers[].world_class` (`configuracion_avatar`/`capas_de`,
`backend/app/modules/economy/equipamiento.py`) — para que el cliente lo pueda
leer desde cualquiera de las dos formas del avatar resuelto. Cubierto por
`backend/tests/economy/test_clase_de_arma_mundo.py` (cobertura exhaustiva de
los 17 ítems + el camino completo semilla→API, verificado por mutación).

**El 65% restante del catálogo (outfit, botas, guantes, capa, cabeza,
accesorios — 30 de 46 ítems) no se refleja en la figura del mundo.** Se dice
claro: caminando se distingue Orden, familia, arma y escudo, no el outfit
específico. Aceptable porque el avatar detallado (`AvatarCapas`,
Vestidor/Perfil) sigue pintando las 92 capas con fidelidad total.

### Generación: una lámina por llamada

Seis fotogramas por combinación (4 de marcha + 2 de reposo), pedidos de una
sola vez como una rejilla 3×2 sobre el lienzo de 1024×1024 — un personaje, un
contexto, sin deriva de identidad entre fotogramas. Las 7 láminas restantes se
editan sobre la primera ya aprobada. Reusa `ESTILO`/`FONDO`/`solo_fondo()`/
`extraer_capa()` de `scripts/vestir.py` tal cual.

**Costo estimado:** ~30 llamadas, entre ~US$1,3 y ~US$5 (techo generoso
US$15). Costo recurrente: un ítem nuevo cuesta una clase en la semilla, cero
imágenes.

### Arquitectura Flutter (pendiente, Fase A en adelante)

`CicloDeMarcha` (puro, elige fotograma **por distancia recorrida**, no por
fase libre — el mundo usa `Curves.easeInOutCubic` y una fase de tiempo lineal
haría patinar las piernas), `figura_del_mundo.dart` (deriva
`familia`/`arquetipo`/`ClaseDeArma` de `List<CapaAvatar>` real, leyendo
`codigoItem`, nunca `assetKey`), `Caminante`/`CaminanteEnSenda` (un solo
widget con dos modos —reposo y marcha—, reemplaza al disco del spike con la
misma interfaz de posición). Memoria: archivos sueltos por fotograma (no
atlas), `cacheWidth` obligatorio, `RepaintBoundary`, `gaplessPlayback`.

## 5. Fases (de gratis a costoso; cada una es un punto de parada real)

1. **Fase 0 — taxonomía de clase de arma. ✅ Hecho (23-09-2026), US$0.**
   `WorldWeaponClass`, `clase_mundo=` en `manifiesto()`, emitido en
   `equipment[slot]` y en `layers[]`, `AvatarLayerOut` actualizado,
   `CONTRACT.md` al día, prueba de cobertura de los 17 ítems.
2. **Fase A — lógica pura. ✅ Hecho (23-09-2026), US$0.**
   `ClaseDeArma` (`app/lib/datos/modelos.dart`, parsea `world_class` — nunca
   una tabla de código de ítem, ese diseño se descartó a favor del dato ya
   resuelto por el servidor), `figura_del_mundo.dart` (deriva
   familia/arquetipo/clase de `List<CapaAvatar>` + `RasgosAvatar` reales),
   `ciclo_marcha.dart` (fotograma por distancia recorrida, nunca por fase de
   reloj). 23 pruebas, dos invariantes verificadas por mutación. Sin
   widgets, sin arte.
3. **Fase B — `Caminante` con fotogramas de mentira. ✅ Hecho (23-09-2026), US$0.**
   `caminante.dart`: `Caminante` (reposo/marcha, un solo widget) +
   `CaminanteEnSenda` (ancla en los pies, espejo por dirección) +
   `PintorDeCaminanteDeMentira` (rectángulo + "piernas" que alternan — se
   borra en cuanto llegue el arte real). 9 pruebas bombeando el reloj,
   verificado por mutación que el fotograma de marcha sale de la distancia
   recorrida y no de la fase del reloj, y que un tramo de longitud cero
   activa el reposo (no congela el fotograma 0 de marcha).
4. **Fase C — el placeholder reemplaza al disco en `experimento_mundo.dart`.
   ✅ Hecho (23-09-2026), US$0.** `CaminanteEnSenda` sustituye al disco, con
   un hueco real encontrado y cerrado en la integración: al llegar a una
   parada, sin un listener de estado sobre el `AnimationController`, el
   caminante quedaba congelado en el último fotograma de marcha en vez de
   volver a reposo — nada más forzaba una reconstrucción de la pantalla solo
   porque el controlador terminó de animar. Probado y verificado por
   mutación. **Veredicto de Rodrigo, en el teléfono: "se ve super mal... no
   se ve el personaje, parecen cuadros."** Aclarado con `AskUserQuestion`: es
   el arte crudo del placeholder lo que no deja juzgar nada más, no el
   sendero ni el mecanismo de caminar — desbloquea la Fase D en vez de
   cerrar el intento.
5. **Fase D — piloto real: 1 Orden (Acero) × 1 familia (masculina) × 2
   fotogramas (contacto + paso), no los 6. ✅ Arte y código hechos
   (23-09-2026), ~US$0,50.** `scripts/experimento_figura_mundo.py` genera
   una sola lámina de 2 casillas vía `images/generations` (no
   `images/edits`: no hay imagen de partida que preservar, la figura
   simplificada no tiene identidad — sin cara, sin pelo suelto). Recortada y
   normalizada con la misma convención de `vestir.py`
   (`ALTO_FIGURA`/`BASE_Y`/`LIENZO`), guardada en
   `app/assets/arte/mundo/masculino/acero/marcha_00..03.webp` (solo 2 poses
   reales; `02`/`03` duplican `00`/`01` hasta la Fase E). `Caminante` ahora
   intenta `Image.asset` primero y cae sola al pintor de mentira vía
   `errorBuilder` — el mismo mecanismo que ya usa `AvatarCapas`, así que las
   Órdenes sin arte real conviven con Acero/masculino sin una sola rama de
   código a mano. `caminante_test.dart` ganó un grupo dedicado ("con arte
   real") que verifica que Acero/masculino en marcha pinta la `Image` real y
   no el pintor de mentira (verificado por mutación: una ruta rota
   reenrojece la prueba); `experimento_mundo_test.dart` se ajustó para
   comprobar el mismo hecho sin depender del pintor, que ya no aparece para
   esa combinación.

   **Primer veredicto real, en el teléfono: "se ve raro, aun veo un
   cuadrado."** Diagnosticado con capturas de pantalla reales (no
   suposición): en marcha el arte real se pintaba bien (una figura
   encapuchada, con jubón de cuero, se ve bien — confirmado con captura), pero
   reposo —el estado antes de tocar y al llegar a cada parada, la mayor parte
   del tiempo en pantalla— no se había generado esta ronda y seguía cayendo
   al cuadrado de mentira. Rodrigo eligió generar también reposo antes de dar
   veredicto, mismo costo (~US$0,50 más).

   **Reposo generado y arreglado dos veces sobre la marcha:** (1) la primera
   pasada normalizó cada casilla de la lámina de reposo a la misma altura
   fija (`ALTO_FIGURA`), lo que borró la única diferencia entre las dos
   poses —el "bob" de exhalar más bajo— dejándolas casi idénticas; se
   corrigió midiendo la escala en la primera casilla y aplicándola por igual
   a la segunda, así la diferencia de alto entre poses (la pose en sí) se
   conserva. (2) El recorte también se comía el marco negro de ~6px que el
   modelo dibuja alrededor de la lámina entera —`solo_fondo` en modo magenta
   no lo reconoce como fondo, así que contaba como "figura" y la silueta
   salía del tamaño de la casilla completa—; se corrigió recortando ese
   margen antes de buscar la silueta. `scripts/experimento_figura_mundo.py`
   ahora soporta `--pose {marcha,reposo}`, con las dos convenciones de
   escalado documentadas en el propio código.

   `caminante_test.dart` ganó una prueba más ("Acero/masculino en reposo
   también pinta la imagen real"); `experimento_mundo_test.dart` se reescribió
   para leer marcha/reposo de la ruta real de la `Image` (`contains('marcha_')`
   / `contains('reposo_')`) en vez de depender del pintor de mentira, que ya
   no aparece nunca para esta combinación. **Pendiente: el segundo APK a
   Rodrigo y su veredicto** — pregunta única: ¿2 fotogramas de marcha + 2 de
   reposo ya se leen como un personaje que camina y descansa? Si no, ni 6 ni
   48 lo arreglan — se para acá, antes de generar la lámina completa (Fase
   E).
6. **Fase E — la lámina completa** de esa combinación + `scripts/laminar.py`.
7. **Fase F — los props** + anclas de mano medidas en Python.
8. **Fase G — las 7 láminas restantes**, editadas sobre la primera aprobada.
9. **Fase H — capa genérica tintada (opcional) + integración en producción**:
   reemplazar `CaminoDeLaRuta` en `mapa_ruta.dart`/P07. DevTools antes de
   cerrar.

## 6. Verificación

- **Backend:** hecho — `test_clase_de_arma_mundo.py`, 5 pruebas, 2 verificadas
  por mutación. `progreso.py` no se toca.
- **`senda.dart`/`pintor_senda.dart`:** ya probado, sin cambios
  (`senda_test.dart` en verde).
- **`ciclo_marcha.dart`/`figura_del_mundo.dart` (puro):** hecho —
  `ciclo_marcha_test.dart` + `figura_del_mundo_test.dart`, 23 pruebas.
  Fotograma por distancia monótono y cíclico (verificado por mutación); la
  clase de arma se deriva de `CapaAvatar.claseArma` (el `world_class` que ya
  resolvió el servidor), nunca de una tabla de código de ítem en el cliente
  (verificado por mutación: una capa de otra ranura no debe contar como
  arma).
- **`caminante.dart` (widget):** hecho — `caminante_test.dart`, 11 pruebas.
  Verificado por mutación que el fotograma en marcha sale de la distancia
  recorrida y no de la fase del reloj; ancla en los pies y espejo por
  dirección, ambos probados montando el widget de verdad. Desde la Fase D,
  un grupo aparte prueba que Acero/masculino (con arte real, marcha y
  reposo) pinta la `Image` real y no el pintor de mentira — verificado por
  mutación (una ruta
  rota reenrojece la prueba).
- **Manual, en dispositivo real — el único juez que importa en cada parada de
  gasto:** Fase C (resuelta: el arte crudo no dejaba juzgar, no el sendero),
  Fase D (pendiente el APK), E, F. Ya quedó demostrado en este mismo plan que
  el veredicto en el teléfono real puede contradecir la teoría de diseño
  previa; ningún test automático lo reemplaza.
