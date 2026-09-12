# Atenea — cliente Flutter

Cliente móvil y web de **Atenea**, un RPG medieval de aprendizaje con IA. El
usuario sube su propio material (un PDF, unos apuntes o una sola frase:
"quiero aprender SQL"), el servidor lo convierte en una **Ruta** con módulos,
lecciones y desafíos, y cada lección completada paga **XP**, **Oro**,
**Dominio** y **Racha** de verdad: el héroe sube de nivel y se equipa
aprendiendo, nunca comprando ventajas.

Esta carpeta contiene **solo el cliente**. El backend y su contrato viven en
`../backend` (`CONTRACT.md`); la dirección de experiencia, en
`../docs/auditoria/07-ux-ui-pantallas-flujo.md`.

## Reglas que el cliente no rompe

Tres decisiones gobiernan todo el código y conviene tenerlas presentes antes de
tocar nada:

1. **La app nunca calcula cifras de juego.** XP, oro, nivel, dominio, precios y
   puntajes llegan resueltos desde el servidor, en el `RewardsReceipt` (§7.10
   del contrato) y en las respuestas de cada endpoint. El cliente los pinta y
   los anima; no los deduce. El `presentation_order` del recibo también es
   autoritativo: la cola de celebraciones lo respeta al pie de la letra.
2. **Ningún valor visual se escribe a mano.** Colores, espaciados, radios,
   duraciones y tamaños salen de `lib/design/tokens.dart`. No hay `Colors.algo`
   en las pantallas salvo `Colors.transparent`.
3. **Los identificadores del código van en español; las claves JSON, no.** Las
   claves respetan literalmente el `snake_case` del contrato (`skin_tone`,
   `is_first_activity_of_day`, `presentation_order`…).

## Puesta en marcha

Requisitos: **Flutter 3.38** o superior (Dart 3.10+).

```bash
flutter pub get
```

### Apuntar el cliente al backend

La URL de la API se fija **al compilar**, con `--dart-define`; no hay que tocar
código para cambiar de entorno:

```bash
flutter run --dart-define=ATENEA_API=https://api.atenea.cl/api/v1
```

La ruta incluye el prefijo de versión (`/api/v1`). Si no se define nada,
`lib/nucleo/entorno.dart` elige un valor por defecto razonable según la
plataforma:

| Plataforma        | Valor por defecto                  | Por qué |
|-------------------|------------------------------------|---------|
| Web y escritorio  | `http://localhost:8000/api/v1`     | El backend corre en la misma máquina. |
| Emulador Android  | `http://10.0.2.2:8000/api/v1`      | Dentro del emulador, `localhost` es el propio emulador. |

En un **teléfono físico** hay que usar la IP de la máquina de desarrollo en la
red local:

```bash
flutter run --dart-define=ATENEA_API=http://192.168.1.20:8000/api/v1
```

### Correr en web

```bash
flutter run -d chrome --dart-define=ATENEA_API=http://localhost:8000/api/v1
flutter build web --release --dart-define=ATENEA_API=https://api.atenea.cl/api/v1
```

El resultado queda en `build/web`. Dos avisos para el navegador:

- **CORS.** El backend debe permitir el origen desde el que se sirve la app.
- **Almacenamiento de tokens.** En móvil los tokens viven en el llavero del
  sistema (Keychain / EncryptedSharedPreferences) vía `flutter_secure_storage`;
  en web no existe un almacén seguro real, así que `AlmacenTokens` cae a
  `SharedPreferences`. Es una limitación conocida del navegador, y por eso el
  token de acceso es de vida corta. La caída de plataforma ya está resuelta
  dentro de `lib/data/almacen_tokens.dart`: no hay que envolver nada más.

### Correr en Android

```bash
flutter run -d <id-del-dispositivo> --dart-define=ATENEA_API=http://10.0.2.2:8000/api/v1
flutter build apk --release --dart-define=ATENEA_API=https://api.atenea.cl/api/v1
flutter build appbundle --release --dart-define=ATENEA_API=https://api.atenea.cl/api/v1
```

El identificador de aplicación es `cl.atenea.atenea`. Los enlaces profundos de
las notificaciones usan el esquema propio `atenea://` (`atenea://home`,
`atenea://route/{id}`, `atenea://lesson/{id}`…); `EnlacesProfundos` los traduce
a direcciones internas en `lib/navegacion/rutas.dart`.

Si el backend se sirve por HTTP plano en desarrollo, Android bloqueará el
tráfico en claro salvo que se habilite en la configuración de red de la
aplicación.

## Estructura de carpetas

```
lib/
├─ main.dart              Arranque: tokens, ApiClient, repositorios,
│                         controladores y carga inicial antes de pintar.
├─ app.dart               MaterialApp.router: temas, idioma, enrutador y la
│                         capa de celebraciones por encima de todo.
│
├─ nucleo/                Entorno (ATENEA_API, esquema de enlaces) y la
│                         preferencia de tema.
│
├─ data/                  Transporte: ApiClient (Bearer, reintento tras
│                         refrescar el token, claves de idempotencia),
│                         AlmacenTokens y ErrorAtenea (mensajes en español).
│
├─ datos/                 Contrato hecho Dart: modelos y enums (modelos.dart),
│                         DTO de cada esquema (dtos.dart), paginación y los
│                         once repositorios, uno por sección de §7.
│
├─ estado/                Controladores ChangeNotifier: sesion, panel,
│                         aventura, leccion, evaluacion, personaje,
│                         gamificacion y la cola de celebraciones.
│
├─ design/                Sistema de diseño: tokens, temas y componentes.
│
├─ navegacion/            rutas.dart (direcciones y enlaces profundos),
│                         enrutador.dart (go_router) y armazon.dart (la barra
│                         inferior y la capa de celebraciones).
│
└─ pantallas/             Las 22 pantallas, agrupadas por flujo:
   ├─ entrada/            P01 bienvenida · P02 acceso · P03 crear personaje
   ├─ inicio/             P04 inicio · P19 misiones · bandeja de avisos
   ├─ aventura/           P22 aventura · P05 crear ruta · P06 generación ·
   │                      P07 mapa de la ruta
   ├─ leccion/            P08 y P09 lección y preguntas · P10 fin de lección
   ├─ evaluacion/         P11 desafío del módulo · P12 resultado
   ├─ celebraciones/      P13 subida de nivel · P14 ítem desbloqueado
   ├─ personaje/          P16 vestidor · P15 mercado
   ├─ perfil/             P17 perfil · P18 racha · P20 logros · P21 ajustes
   └─ galeria_estilo.dart Galería del sistema de diseño (solo en depuración)
```

Cada carpeta de pantallas tiene su subcarpeta `widgets/` con las piezas que
solo usa ese flujo. Lo que comparten varias pantallas vive en
`lib/design/components.dart`.

### Cómo se enchufa todo

- **Estado:** `provider` (`ChangeNotifier` + `Consumer` / `context.watch`). No
  hay Riverpod ni bloc.
- **Navegación:** `go_router`. Un `StatefulShellRoute` sostiene los cuatro
  destinos con barra inferior (Inicio, Aventura, Personaje, Perfil); los flujos
  inmersivos —crear ruta, generación, lección, desafío— van a pantalla completa,
  fuera del armazón. La redirección por fase de sesión decide entre la entrada,
  la creación de personaje y el Inicio.
- **Red:** siempre a través del `ApiClient`; ninguna pantalla usa Dio directo ni
  llama a un repositorio por su cuenta: consume su controlador.
- **Serialización:** `fromJson` escritos a mano y tolerantes a campos ausentes
  o nulos. **No hay generación de código**: ni `build_runner`, ni `freezed`, ni
  `json_serializable`.
- **Gráficos:** `fl_chart`. **Animaciones:** `flutter_animate` o las implícitas
  de Flutter. **Archivos:** `file_picker` (API 12.x: `FilePicker.pickFiles`
  devuelve `Future<List<PlatformFile>>` y los bytes se leen con
  `PlatformFile.readAsBytes()`).

## Sistema de diseño

El concepto visual es **"Crónica luminosa"**: un reino nocturno, elegante y
limpio donde el conocimiento es luz. Medieval en la forma, moderno en la
ejecución. Vive en tres archivos.

### `lib/design/tokens.dart`

| Token | Qué define |
|---|---|
| `Espacio` | `xxs` 4 · `xs` 8 · `sm` 12 · `md` 16 · `lg` 24 · `xl` 32 · `xxl` 48 dp. Toda separación sale de aquí. |
| `Redondeo` | `chip` 8 · `boton` 12 · `tarjeta` 16 · `hoja` 24 · `pildora` 999, con sus `BorderRadius` ya construidos. |
| `Movimiento` | `micro` 180 ms · `corta` 250 · `transicion` 380 · `celebracion` 1400 · `celebracionLarga` 2400, más las curvas `estandar` y `entrada`. |
| `Tipo` | Escala tipográfica: leyenda 12 · secundario 14 · cuerpo 16 · subtítulo 20 · título 24 · display 32 · héroe 44 dp. |
| `Medida` | `lecturaMax` 640 dp y `areaTactilMin` 48 dp. |
| `Rareza` | Las seis rarezas con su color, su radio de brillo y su **etiqueta textual**, más `Rareza.desdeApi`. |
| `AteneaPalette` | La paleta semántica como `ThemeExtension`, en sus dos versiones: `noche` (oscuro, por defecto) y `dia` (claro). |
| `Sombra` | `Sombra.brillo(color, radio)` para recompensas y rarezas; `Sombra.hoja(brillo)` para modales. |

La paleta se lee **siempre** por semántica, nunca por valor:
`fondo`, `superficie`, `superficieElevada`, `lectura`, `borde`,
`textoPrimario`, `textoSecundario`, `arcano` (acción y foco), `oro` (XP y
recompensa), `brasa` (racha), `dominio`, `exito`, `advertencia`, `error`,
`info`, más los pares de contraste `sobreArcano` y `sobreOro`.

Tres atajos desde cualquier widget: `context.paleta`, `context.textos` y
`context.esOscuro`.

### `lib/design/theme.dart`

`AteneaTheme.oscuro()` y `AteneaTheme.claro()` construyen el `ThemeData`
completo a partir de los tokens. Reglas tipográficas:

- **Cinzel** solo para display y títulos de celebración, siempre de 20 dp
  hacia arriba; nunca en cuerpo ni en botones.
- **Nunito Sans** para toda la interfaz, con 16 dp mínimo e interlineado 1,5 en
  el cuerpo de texto.
- `Cifras.heroe/grande/media/pequena(context)` dan **numerales tabulares**, para
  que los dígitos no bailen mientras una cifra se anima.

### `lib/design/components.dart`

La biblioteca de piezas: `PantallaAtenea` (andamio estándar; **no desplaza su
cuerpo**, cada pantalla decide cómo se recorre), `TarjetaAtenea`,
`EncabezadoSeccion`, `Medallon` y `FichaMedallon` (XP, oro, racha, dominio,
tiempo, nivel), `BarraProgreso`, `ChipRareza`, `Pildora`, `BotonPrimario`,
`EstadoVacio`, `EstadoError`, `EstadoCarga`, `Esqueleto`, `FilaDato`,
`OrnamentoEsquina`, `CifraAnimada` y el ayudante `reducirMovimiento(context)`.

### Accesibilidad, no negociable

- Área táctil mínima de **48 dp**, aunque el dibujo sea más pequeño.
- **El color nunca es el único portador de significado**: rareza, estado y
  resultado llevan siempre icono o etiqueta.
- Contadores y barras anuncian su valor al lector de pantalla.
- **Toda celebración tiene versión estática** cuando `reducirMovimiento(context)`
  es verdadero. Esa preferencia suma la del sistema y la de Ajustes (P21).
- La interfaz se sostiene con la fuente del sistema al 200 %.

### Galería del sistema de diseño

`lib/pantallas/galeria_estilo.dart` es la **referencia viva**: pinta tokens,
tipografía, cifras, medallones, rarezas, botones, tarjetas y estados con el
mismo código que usan las pantallas, y permite alternar tema y escala de texto
sin salir de ella. Se abre desde **Ajustes → Herramientas del Reino → Sistema
de diseño**, y solo existe en compilaciones de depuración (`kDebugMode`).

Si una pantalla no se parece a lo que muestra la galería, la que se equivoca es
la pantalla.

## Análisis y pruebas

Las reglas del analizador están en `analysis_options.yaml` (sobre
`flutter_lints`). El proyecto se mantiene **en cero avisos**:

```bash
flutter analyze          # debe responder "No issues found!"
flutter test             # toda la suite
flutter test test/cola_celebraciones_test.dart   # un solo archivo
```

La suite vive en `test/`:

| Archivo | Qué protege |
|---|---|
| `ayudas.dart` | Utilidades compartidas: un `AlmacenTokens` en memoria (para no tocar el llavero), repositorios apuntando a un servidor inexistente y el apagado de la descarga de tipografías. |
| `arranque_test.dart` | Que la aplicación se levante con los controladores reales y que el enrutador lleve a P02 cuando ya se vio el onboarding, y a P01 cuando no. |
| `cola_celebraciones_test.dart` | El corazón del contrato de recompensas: que `presentation_order` mande sobre el orden canónico, el tope de tres overlays, los chips para P10 y P12, el límite de 2,4 s y la versión de movimiento reducido. Incluye una prueba de widget que recorre los tres overlays en el orden que pidió el servidor. |
| `galeria_estilo_test.dart` | Que la galería se pinte sin un solo desborde en los dos temas, a 320, 412 y 800 dp de ancho, con la escala de texto al 100 %, 130 % y 200 %. |

Compilación de web, que es la que más rápido detecta una dependencia
incompatible:

```bash
flutter build web --release
```

## Estado conocido

- **Sin recursos gráficos por capa.** El avatar se dibuja con `CustomPainter`
  a partir de las claves de la API (`skin_tone`, `hair_style_id`, `body_type`…).
  Cuando exista el arte, se sustituye el pintor por un `Stack` ordenado por `z`
  sin cambiar la API pública de los widgets de avatar.
- **Sin OAuth ni recuperación de contraseña.** El contrato define el enum
  `AuthProvider` pero no publica las rutas, así que P02 no pinta botones que no
  funcionarían.
- **Sin modo sin conexión.** No hay caché de lecciones ni cola de envíos
  diferidos: las pantallas muestran el error traducido y ofrecen reintentar.
- **Sin push nativo.** `ControladorGamificacion.registrarTokenPush` existe, pero
  falta la integración con FCM/APNs y la petición del permiso del sistema.
- **Sin analítica.** Las métricas de experiencia del documento de UX todavía no
  se emiten desde ninguna pantalla.
