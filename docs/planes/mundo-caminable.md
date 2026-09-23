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
2. **Fase A — lógica pura, US$0.** `ciclo_marcha.dart` + `figura_del_mundo.dart`
   + pruebas (índice cíclico y monótono por distancia; cobertura exhaustiva de
   clase de arma). Sin widgets, sin arte.
3. **Fase B — `Caminante` con fotogramas de mentira** (rectángulos + "piernas"
   que alternan). Juzga el *timing* real sin un pixel generado.
4. **Fase C — el placeholder reemplaza al disco en `experimento_mundo.dart`.
   APK a Rodrigo. Pregunta única: ¿el sendero se siente un mundo con ALGO que
   camina, o el problema nunca fue el disco?** US$0. Si sigue sin sentirse un
   mundo, se para acá.
5. **Fase D — piloto real: 1 Orden × 1 familia × 2 fotogramas**, no los 6.
   <US$0,50. Si a 2 fotogramas no se lee "camina", ni 6 ni 48 lo arreglan.
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
- **`ciclo_marcha.dart`/`figura_del_mundo.dart` (puro, pendiente):** fotograma
  por distancia monótono y cíclico; `ClaseDeArma.deCodigo` cubre cada código
  real del seed.
- **Manual, en dispositivo real — el único juez que importa en cada parada de
  gasto:** Fase C, D, E, F. Ya quedó demostrado en este mismo plan que el
  veredicto en el teléfono real puede contradecir la teoría de diseño previa;
  ningún test automático lo reemplaza.
