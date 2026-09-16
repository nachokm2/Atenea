# Atenea

Estudiar **es** el juego. Atenea convierte el material de estudio de una persona
en una aventura medieval: sube sus apuntes, la IA los convierte en un mapa de
lecciones, y cada rato de estudio real da experiencia, oro y objetos.

- `app/` — cliente Flutter (Android, iOS y web).
- `backend/` — API FastAPI, PostgreSQL con pgvector y el motor de juego.
- `backend/CONTRACT.md` — la fuente normativa: enums, tablas, eventos, claves de
  configuración, fórmulas y las rutas. Ante cualquier duda, manda el contrato.
- `docs/` — el brief de producto y los documentos de diseño.
- `scripts/dev.ps1` y `scripts/dev.sh` — todos los comandos de desarrollo.

## Probarla en local

Hace falta Docker, Python 3.12 y Flutter 3.38.

```powershell
.\scripts\dev.ps1 install     # dependencias de Python
.\scripts\dev.ps1 db          # PostgreSQL 16 + pgvector en el puerto 55432
.\scripts\dev.ps1 migrate     # crea las 52 tablas
.\scripts\dev.ps1 seed        # áreas, niveles, ítems, misiones, logros y una ruta de ejemplo
.\scripts\dev.ps1 api         # la API en http://localhost:8000
```

En otra terminal, la app:

```powershell
cd app
flutter run -d chrome
```

En web y en escritorio el valor por defecto ya apunta a `localhost:8000`. Para un
emulador de Android o un teléfono real hay que decir a qué máquina conectarse:

```powershell
flutter run --dart-define=ATENEA_API=http://10.0.2.2:8000/api/v1      # emulador Android
flutter run --dart-define=ATENEA_API=http://192.168.1.20:8000/api/v1  # teléfono en la misma red
```

**Para mirar la app, no para programarla, compílala en release.** En el navegador,
el modo de depuración de Flutter va a tirones: no optimiza, no recorta código y
deja todas las aserciones puestas, y Atenea tiene ilustraciones grandes, sombras y
degradados, que es lo que más sufre ahí. Se nota sobre todo al desplazar una
pantalla larga, y parece que la app se ha colgado cuando lo único que pasa es que
está en modo de depuración.

```powershell
cd app
flutter build web --release --dart-define=ATENEA_API=http://localhost:8000/api/v1
cd build\web; python -m http.server 5124
```

Tarda algo más de un minuto en compilar y se desplaza con soltura. El `flutter run`
de arriba sigue siendo lo correcto para programar, porque trae recarga en caliente.

Atenea usa dos servicios de IA distintos y conviene no confundirlos. **Claude**
escribe las lecciones y corrige las respuestas abiertas. **Los embeddings**
(OpenAI o Voyage, a elección) convierten el material en vectores para poder
buscar por significado dentro de él: sin ellos, las lecciones se escribirían sin
mirar lo que subió el aprendiz.

Con la semilla ya hay una ruta jugable de principio a fin sin gastar un peso en
IA. Para que la IA genere rutas a partir de documentos propios hacen falta dos
cosas más: `ANTHROPIC_API_KEY` en el `.env` de la raíz y el procesador de
trabajos corriendo.

```powershell
.\scripts\dev.ps1 worker
```

## Ponerla en el mundo

El despliegue se describe entero en [.railway/railway.ts](.railway/railway.ts), que
sustituye al antiguo `railway.toml`: Railway declaró obsoleto aquel formato y no
admite servicios nuevos con él.

```bash
npm install                        # el SDK que evalúa .railway/railway.ts
railway login
railway link
railway config plan --show-values  # enseña qué cambiaría, sin tocar nada
railway config apply               # lo aplica tras confirmar
railway domain                     # pide la URL pública: no puede ir en el archivo
```

Sin `--show-values`, el plan enseña los valores como «hidden» y no se puede
comprobar lo que de verdad va a subir. Merece la pena mirar tres cosas antes de
aplicar: que `build.builder` diga `DOCKERFILE`, que `source.rootDirectory` diga
`backend`, y que nada aparezca marcado como destructivo sobre la base o el
volumen.

Hace falta la CLI **5.42.1 o superior** (`npm i -g @railway/cli`). En Windows,
usa [scripts/railway.ps1](scripts/railway.ps1) en vez de `railway` a secas: el
SDK comprueba la versión de la CLI buscando un ejecutable llamado `railway`, que
en Windows no existe como tal, y responde que la CLI es vieja aunque esté al día.
El envoltorio le señala el `railway.exe` de verdad.

Los secretos no viven en ese archivo: `preserve()` conserva lo que ya está en
Railway, no lo crea. Hay que cargarlos **antes** del primer despliegue, en el
panel del servicio `api`:

| Variable | Para qué |
|---|---|
| `JWT_SECRET` | Firma de las sesiones. Mínimo 32 caracteres y nunca el de desarrollo. |
| `ANTHROPIC_API_KEY` | Generación de rutas, lecciones y preguntas. |
| `OPENAI_API_KEY` | Embeddings del material (`EMBEDDINGS_PROVIDER=openai`). |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` | Recuperación de contraseña. |

Si falta alguno, o si el secreto de firma sigue siendo el de desarrollo, **la
aplicación no arranca** y dice exactamente cuál falta. Es a propósito: un
servidor mal configurado no falla, responde 200 y hace daño en silencio.

Un detalle que conviene conocer antes de escalar: el material que sube el
aprendiz vive en disco, y en Railway un volumen se monta en un solo servicio. Por
eso hay **un** servicio y el procesador de trabajos corre dentro de la propia API
(`WORKER_EN_PROCESO`). El día que ese material viva en un bucket, se apaga esa
variable y el worker vuelve a ser un servicio aparte, que escala mejor.

## Publicar el Android

El paquete de release necesita una llave de firma que **no** vive en el
repositorio. Se crea una sola vez:

```bash
keytool -genkey -v -keystore ~/atenea-release.jks         -keyalg RSA -keysize 2048 -validity 10000 -alias atenea
```

Copia [app/android/key.properties.ejemplo](app/android/key.properties.ejemplo) a
`app/android/key.properties` y rellénalo. Guarda el `.jks` y sus contraseñas con
copia de seguridad: Play identifica la app por su firma, así que perderlos
significa no poder volver a publicar una actualización de Atenea nunca más.

Sin ese archivo la compilación sigue funcionando, firmada con la clave de
depuración, y avisa por consola. Sirve para probar en local; Play la rechaza.

```bash
cd app
flutter build appbundle --release --dart-define=ATENEA_API=https://tu-api/api/v1
```

Si no pasas `ATENEA_API`, el paquete apunta a `Entorno.apiProduccion`. Nunca a
`localhost`: un paquete publicado que busca el ordenador de quien lo compiló no
le sirve a nadie, y desde Android 9 el tráfico sin cifrar está bloqueado.

### Instalarla en tu propio móvil

Para llevarla a un teléfono y ya —sin Play, sin llave de firma— basta un APK,
que es otro artefacto distinto del `appbundle`:

```bash
cd app
flutter build apk --release --dart-define=ATENEA_API=https://api-production-66b3.up.railway.app/api/v1
```

Sale en `app/build/app/outputs/flutter-apk/app-release.apk`. Se copia al teléfono
y se abre desde el explorador de archivos; Android pedirá permiso para instalar
de fuera de Play, que hay que dar una vez.

Va firmado con la clave de depuración mientras no exista `key.properties`. Para
instalártelo tú da igual; para Play no sirve.

**El `ATENEA_API` tiene que ser `https://`.** Apuntar el APK a la máquina de
desarrollo por la red de casa —`http://192.168.x.x:8000`— no funciona y encima
no avisa: Android bloquea el tráfico en claro desde la versión 9 y el manifiesto
de Atenea no lo permite, así que la app no da error, simplemente no recibe
respuesta nunca.

## Comprobar que todo sigue en pie

```powershell
.\scripts\dev.ps1 test        # las pruebas del backend
cd app; flutter test          # las pruebas del cliente
python scripts\recorrido_mvp.py   # recorrido completo del primer día contra la API
python scripts\probar_ia.py       # genera una ruta con Claude de verdad (cuesta dinero)
```

Las pruebas del cliente incluyen `test/contrato_vivo_test.dart`, que recorre el
primer día con los repositorios reales contra la API viva. Es la única que
comprueba que el cliente y el servidor hablan el mismo idioma, así que conviene
tener la API levantada al pasarlas; si no responde, se salta sola.
