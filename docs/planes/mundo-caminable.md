<!-- Plan aprobado el 23-09-2026, en curso. Los números de línea envejecen;
     comprueba antes de ejecutar sobre ellos. Ver docs/planes/mapa-del-reino.md
     para el frente que este plan revierte en parte (P07, no P22). -->

# PLAN — Un mundo caminable en P07 (Ruta), con el avatar equipado de verdad

## 1. Por qué existe

Rodrigo encontró [sprite-gen](https://github.com/aldegad/sprite-gen) buscando
mejorar el arte de personajes y, al ver sus demos animadas, pidió personajes
**animados**. Al precisar el alcance, decidió — sabiendo el costo real — la
opción más grande: que el mapa de **Ruta (P07)** deje de ser una lista de
nodos y se convierta en un mundo 2D donde el avatar equipado camina de verdad
entre módulos.

Esto revierte a propósito, y solo en parte, la decisión de
`docs/planes/mapa-del-reino.md` (16-09) de no dibujar un mapa navegable — pero
esa decisión hablaba de la **grilla de Territorios (P22)**, que de verdad no
tiene datos de posición ni adyacencia. Ruta es un caso distinto: **sí** tiene
orden y adyacencia reales en el backend.

`sprite-gen` en sí **no se usa**: es generación de fotogramas por IA (costo
recurrente por cada ítem nuevo del catálogo, para siempre) y su propia
documentación marca el ciclo de caminar como experimental, probado en
mascotas compactas, no en ilustraciones detalladas como las de Atenea.

## 2. Lo verificado antes de decidir

- **El mundo caminable de Ruta no necesita ningún cambio de backend.** El
  orden (`PathModule.position`, `prerequisite_module_id`) y el candado (la
  evaluación del módulo, regla A7, `backend/app/modules/progress/progreso.py`)
  ya existen y ya se aplican en el servidor. `desbloquear_siguiente_modulo`
  usa exactamente `prerequisite_module_id` o `position + 1` como el borde del
  grafo. Un sendero dibujado sobre esto no inventa nada; dibuja un dato que el
  servidor ya recorre.
- **El avatar equipado puede caminar sin generar ni un pixel de arte nuevo.**
  Medido con `numpy`/`scipy.ndimage.label` sobre
  `app/assets/arte/capas/cuerpos/base_masculino_002_sin_manos.webp`
  (silueta = alfa > 40, misma técnica que `scripts/medir_figuras.py`):
  - Las **piernas** son dos componentes conexas de verdad, separadas por un
    hueco real en la entrepierna (fila ≈560 del lienzo de 1024). Ninguna de
    las 92 capas de equipo actuales cruza esa línea.
  - Los **brazos**, en cambio, **no** tienen un hueco real respecto al torso
    en este dibujo — es una sola silueta conexa entre el hombro (fila ≈328) y
    la cadera. Recortar un rectángulo para el brazo corta, por fuerza, un poco
    de torso con él. Es el riesgo central que la Fase 0b existe para evaluar,
    no algo que se pueda medir hasta que desaparezca.
- **El personaje siempre mira de frente** — no hay vista de perfil ni de
  espalda en el arte, y no se puede generar una que combine con el estilo
  existente. El mundo se diseña para una figura de frente que se desliza
  marchando, no para un personaje que gira.

## 3. Parte A — El mundo caminable (reemplaza `CaminoDeLaRuta`)

**Cero cambios de backend.** La posición de cada parada es una función
determinista `índice → Offset` calculada en el cliente — nunca normalizada
por el total de módulos, porque estos se generan de a uno
(`content/rutas.py._encargar_contenido`) y el total cambia en vivo mientras el
aprendiz mira la pantalla. Ver `app/lib/pantallas/aventura/mundo/senda.dart`.

**El mundo es: paradas de módulo + portones de evaluación + el tesoro
final.** Lecciones, la ficha de la prueba y el Reto quedan dentro de un panel
que se abre al llegar a la parada.

**Movimiento: tocar para caminar, no joystick.** El dominio tiene un solo
grado de libertad (el orden de módulos); tocar una parada abierta camina
hasta ella, tocar una bloqueada lleva hasta el portón cerrado y explica el
motivo (el mismo `locked_reason` que ya manda el servidor).

**Técnica: Flutter a mano (`CustomPainter` + `AnimationController` +
`ScrollController` como cámara), no Flame.** No justifica una dependencia de
motor de juego nueva, y perdería `Semantics` y el estilo de pruebas de widget
que ya usa el proyecto.

## 4. Parte B — El avatar camina: rig de huesos en Dart, sin arte nuevo

Un "muñeco de papel" articulado en tiempo de ejecución sobre el arte que ya
existe: por cada parte del cuerpo, se recorta su rectángulo medido
(`ClipRect`) y se rota alrededor de su pivote medido (`Transform.rotate`),
con el ángulo como función del tiempo (`sin(fase)`).

**Por qué no las otras rutas:** generar cada fotograma con IA no converge
(no hay una base fija que editar entre poses, y multiplica el catálogo para
siempre); riggear en Rive/Spine exige separar arte a mano por cada ítem nuevo
(contradice "ítems nuevos se agregan con filas y assets, sin release");
un bob rígido de todo el conjunto (lo que `06c-inventario-equipamiento-tienda.md`
proponía para reposo) no sirve para caminar — las piernas son el 45% de la
altura de la figura y son dos objetos separables; moverlas como un bloque se
lee como una estatua deslizándose. Sí es lo correcto para el reposo (Fase 4).

**Costo: cero recurrente.** Un ítem nuevo del catálogo solo necesita que su
`layer key` exista en `PILA_DE_CAPAS` (servidor) y en el mapa Dart
`ParteDelCuerpo.de(clave)` (Fase 2) — una línea, con una prueba de cobertura
exhaustiva contra la pila real.

## 5. Fases

1. **Fase 0 — dos experimentos descartables, sin backend, sin tocar
   `CaminoDeLaRuta`.** ✅ Construidos y probados (`flutter test`, 259
   pruebas verdes); pendiente el juicio humano en un dispositivo real.
   - **0a** — `app/lib/pantallas/aventura/mundo/senda.dart` (geometría pura),
     `pintor_senda.dart` (el trazo y los portones) y
     `experimento_mundo.dart` (la pantalla del spike: sendero + cámara que
     sigue + un disco de color como caminante). Pregunta: ¿un serpenteante
     vertical con paradas se siente como un mundo, o como la misma lista con
     un delay?
   - **0b** — `experimento_marcha.dart`: la marcha con recortes/rotaciones
     sobre `base_masculino_002` únicamente, con cuatro sliders en vivo
     (cadera, brazos, bob, inclinación). Pregunta: ¿se lee como caminar, o
     como una marioneta rota? ¿se nota el corte en el hombro?
   - Ambos viven solo en compilaciones de depuración, enlazados desde
     Ajustes → Herramientas del Reino, y se borran enteros sin dejar rastro
     si la respuesta es "no". Siguiente paso: un APK a Rodrigo.
2. **Fase 1** — el mundo reemplaza la lista en P07, con el disco de la
   Fase 0 como caminante. Sin arte nuevo, sin backend.
3. **Fase 2** — `scripts/medir_miembros.py` (mide las seis figuras, como
   `medir_figuras.py`, no un cuerpo suelto) + `PilaDeAvatar` compartida (con
   una prueba dorada de que `AvatarCapas` sigue pintando igual) +
   `AvatarCaminante` real.
4. **Fase 3** — integrar `AvatarCaminante` en el mundo. Medir memoria y
   rendimiento con DevTools.
5. **Fase 4** — bob sutil + parpadeo en reposo (la deuda de
   `06c-inventario-equipamiento-tienda.md`, nunca construida), gratis con el
   rig ya hecho, aplicado también en Vestidor y Perfil.
6. **Fase 5** — pulido: cámara, textura del sendero, sombra, variación
   sembrada por ruta.

**Plan B, si la Fase 0b falla:** una figura desacoplada y simplificada solo
para el mundo (4 arquetipos × 2 familias × 1 dirección × 6 fotogramas, una
sola vez), con la clase de arma derivada de la `layer key` en vez de
fidelidad por ítem. Cuesta una segunda identidad de arte que mantener en
sync para siempre — por eso es el plan B, no el plan.

## 6. Verificación

- **Backend:** ninguna prueba nueva — no se toca.
- **`senda.dart`:** N módulos → N+1 paradas en orden; estabilidad ante
  crecimiento (una senda de 4 y una de 6 módulos ubican las paradas 0-3 en el
  mismo lugar); `ultimaAlcanzable` coincide con el primer bloqueado;
  determinismo. Ver `app/test/senda_test.dart`.
- **`experimento_mundo.dart`:** tocar una parada abierta no avisa; tocar una
  bloqueada detiene al caminante en el portón y explica el motivo real (no
  uno inventado en el spike). Ver `app/test/experimento_mundo_test.dart`.
- **`experimento_marcha.dart`:** la animación corre varios ciclos completos
  sin lanzar excepción; los cuatro sliders existen y responden. No hay, ni
  puede haber, una prueba de "se ve como caminar" — es la pregunta que el
  spike existe para responder, y solo un humano mirando el dispositivo real
  puede contestarla. Ver `app/test/experimento_marcha_test.dart`.
- **Manual, en dispositivo real:** las dos preguntas de la Fase 0. Ningún
  test las reemplaza.
