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

## Comprobar que todo sigue en pie

```powershell
.\scripts\dev.ps1 test        # 475 pruebas del backend
cd app; flutter test          # 19 pruebas del cliente
python scripts\recorrido_mvp.py   # recorrido completo del primer día contra la API
python scripts\probar_ia.py       # genera una ruta con Claude de verdad (cuesta dinero)
```

Las pruebas del cliente incluyen `test/contrato_vivo_test.dart`, que recorre el
primer día con los repositorios reales contra la API viva. Es la única que
comprueba que el cliente y el servidor hablan el mismo idioma, así que conviene
tener la API levantada al pasarlas; si no responde, se salta sola.
