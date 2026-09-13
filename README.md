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
railway login
railway link
railway config plan     # enseña qué cambiaría, sin tocar nada
railway config apply    # lo aplica tras confirmar
```

Los secretos no viven en ese archivo. Se cargan una vez en el panel de Railway:
`JWT_SECRET`, `ANTHROPIC_API_KEY` y `VOYAGE_API_KEY`. Si falta alguno, o si el
secreto de firma sigue siendo el de desarrollo, **la aplicación no arranca** y
dice exactamente qué falta. Es a propósito: un servidor mal configurado no falla,
responde 200 y hace daño en silencio.

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

## Comprobar que todo sigue en pie

```powershell
.\scripts\dev.ps1 test        # 498 pruebas del backend
cd app; flutter test          # 29 pruebas del cliente
python scripts\recorrido_mvp.py   # recorrido completo del primer día contra la API
python scripts\probar_ia.py       # genera una ruta con Claude de verdad (cuesta dinero)
```

Las pruebas del cliente incluyen `test/contrato_vivo_test.dart`, que recorre el
primer día con los repositorios reales contra la API viva. Es la única que
comprueba que el cliente y el servidor hablan el mismo idioma, así que conviene
tener la API levantada al pasarlas; si no responde, se salta sola.
