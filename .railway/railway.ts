/**
 * Despliegue de Atenea en Railway.
 *
 * Sustituye a `railway.toml`, que usaba Config as Code: Railway lo declaró
 * obsoleto, no admite servicios nuevos y deja de leerse el 1 de diciembre de
 * 2026. Aquel archivo, además, describía el worker, las variables y el volumen
 * solo en comentarios, así que la mitad del plan no se aplicaba ni en su día.
 *
 * Se aplica con la CLI, que enseña el plan antes de tocar nada:
 *
 *     railway login
 *     railway link
 *     railway config plan --show-values   # sin --show-values los valores salen ocultos
 *     railway config apply                # lo aplica tras confirmar
 *
 * ## Este archivo nunca se había ejecutado
 *
 * `railway config plan` salía limpio, y eso engañó: un plan limpio dice que el
 * archivo es coherente consigo mismo, no que el despliegue vaya a arrancar. Una
 * auditoría contra el SDK instalado encontró cinco defectos que impedían llegar
 * a un contenedor vivo. Están corregidos aquí y cada uno lleva su porqué al lado,
 * porque todos eran invisibles desde fuera:
 *
 *   1. La imagen de base no traía `pgvector` y la primera migración moría.
 *   2. `build: "docker"` no elegía constructor: el SDK convierte una cadena en
 *      **comando** de compilación.
 *   3. Sin `rootDirectory`, el contexto de construcción era la raíz del
 *      repositorio, donde no hay Dockerfile.
 *   4. El volumen se monta como root y el contenedor corría sin privilegios: la
 *      primera subida de material habría dado un 500.
 *   5. `DATABASE_URL` se componía interpolando referencias en una plantilla de
 *      texto, y una referencia del SDK es un objeto: lo que se habría desplegado
 *      era, literalmente, `postgresql+psycopg://[object Object]:[object Object]@…`.
 *
 * ## Un solo servicio, a propósito
 *
 * El material que sube el aprendiz vive hoy en disco, y en Railway un volumen se
 * monta en **un** servicio. Una API y un worker separados no compartirían esos
 * archivos: el aprendiz subiría un PDF y el worker no lo encontraría nunca. Por
 * eso la API lleva el procesador de trabajos dentro (`WORKER_EN_PROCESO`).
 *
 * El día que el material viva en un bucket, hay que apagar esa variable y añadir
 * aquí un segundo servicio con el mismo repositorio y `python -m app.worker`.
 * Está preparado para eso y no antes: separarlo ahora rompería la ingesta.
 *
 * ## Lo que este archivo no puede hacer
 *
 * Tres cosas quedan fuera a propósito y hay que hacerlas en el panel o con la
 * CLI, una sola vez:
 *
 *   - **Los secretos.** `preserve()` conserva lo que ya está en Railway; no crea
 *     nada. Hay que cargarlos antes del primer despliegue o el arranque se niega.
 *   - **El dominio.** El SDK solo sabe declarar dominios propios, que necesitan
 *     CNAME y TXT de verificación. El generado (`*.up.railway.app`) se pide con
 *     `railway domain`, y Railway lo deja deliberadamente fuera de este archivo.
 *   - **El `Custom Build Command`**, si el defecto 2 llegó a aplicarse alguna vez:
 *     poner `buildCommand: null` no lo borra, porque el SDK descarta los nulos.
 *     Se vacía a mano en Settings → Build.
 */

import { database, defineRailway, github, preserve, project, service, volume } from "railway/iac";

export default defineRailway((ctx) => {
  const esProduccion = ctx.environment === "production";

  // `postgres()` fija la imagen de Railway, que **no trae pgvector**: su propia
  // documentación dice que no piensan añadir extensiones a las plantillas. La
  // migración 0001 hace `CREATE EXTENSION vector` y crea un índice HNSW, así que
  // el `preDeploy` moría ahí y el despliegue nunca llegaba a servir nada.
  //
  // `database()` es exactamente lo mismo que `postgres()` —mismo tipo, misma
  // dirección `database.postgres`, mismo `env`— solo que deja elegir la imagen.
  //
  // pg16 y no pg18 (que es lo que usa `postgres()` hoy) para que la base de
  // producción tenga la misma versión mayor que la de desarrollo y la de
  // integración continua, que ya usan `pgvector/pgvector:pg16`. Subir de versión
  // mayor es una decisión deliberada con su propio cambio; hacerlo sin querer, en
  // el sitio donde están los datos de verdad, no.
  const base = database("postgres", "postgres", {
    image: "pgvector/pgvector:pg16",
    output: "DATABASE_URL",
    defaultMountPath: "/var/lib/postgresql/data",
  });

  // El material del aprendiz. `sizeMB` se puede subir sin perder nada; bajarlo
  // o quitarlo es destructivo y Railway lo marca como tal antes de aplicar.
  const material = volume("material", { sizeMB: 5120 });

  const api = service("api", {
    // `rootDirectory` es obligatorio: el Dockerfile vive en `backend/` y espera
    // su contexto ahí (sus `COPY` son rutas de backend/, no de la raíz). Sin
    // esto, Railway construye desde la raíz del repositorio, donde no hay
    // Dockerfile sino un `package.json`, y adivina un proyecto de Node.
    source: github("nachokm2/Atenea", { branch: "main", rootDirectory: "backend" }),

    // Forma de objeto, no cadena. El SDK normaliza una cadena en `build` como
    // **comando** de compilación (`{ buildCommand: "docker" }`), así que
    // `build: "docker"` le pedía a Railway que ejecutara un programa llamado
    // `docker` y dejaba el constructor sin elegir.
    //
    // `dockerfilePath` es relativo a `rootDirectory`: "Dockerfile", nunca
    // "backend/Dockerfile".
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile",
    },

    // Las migraciones y las semillas van **antes** del arranque, no dentro del
    // comando de inicio: si fallan, el despliegue se detiene y la versión
    // anterior sigue sirviendo. Ambas son idempotentes, así que repetirlas no
    // hace nada. Sin la siembra, una base recién migrada arranca sin
    // configuración de juego, sin niveles, sin objetos y sin misiones, y la app
    // respondería 200 a todo sin tener nada que mostrar.
    preDeploy: "alembic upgrade head && python -m app.seeds",

    // `${PORT:-8000}` y no `$PORT` pelado: este comando sustituye al `CMD` del
    // Dockerfile, que sí llevaba respaldo. Si `PORT` no estuviera puesto —y
    // Railway lo inyecta a partir del puerto destino de un dominio, que al
    // principio no existe—, el shell borraría la palabra vacía y uvicorn
    // recibiría `--port --proxy-headers`. El contenedor no arrancaría y el
    // healthcheck no llegaría ni a ejecutarse.
    start:
      "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} " +
      "--proxy-headers --forwarded-allow-ips='*'",

    // La ruta del contrato es `/api/v1/health`; `/health` existe porque es la
    // que esperan las plataformas, que no saben del prefijo de versión. Apuntar
    // aquí a una ruta que devuelve 404 pone el servicio en bucle de reinicios
    // con la aplicación perfectamente sana.
    healthcheck: "/health",
    healthcheckTimeout: 30,

    // Una sola réplica mientras el material esté en disco: dos no compartirían
    // ni los archivos ni el contador del freno de peticiones. Railway además
    // prohíbe varias réplicas en un servicio con volumen, así que esto no es una
    // preferencia sino un requisito.
    replicas: 1,

    volumeMounts: {
      "/data/material": material,
    },

    // Los dominios propios no se declaran todavía. Necesitan CNAME **y** TXT de
    // verificación en el registrador; con solo el CNAME, Railway devuelve 404 a
    // todo y parece un fallo de la aplicación. Primero un dominio generado
    // (`railway domain`) para comprobar que el despliegue funciona de verdad.
    // Cuando el DNS esté listo, y con `CORS_ORIGINS` diciendo exactamente lo
    // mismo:
    //
    //     domains: [
    //       { domain: "atenea.cl", port: 8080 },
    //       { domain: "www.atenea.cl", port: 8080 },
    //     ],
    //
    // Quitar una entrada de ese array **borra** el dominio en Railway, y el plan
    // lo marcará como destructivo.

    env: {
      ENVIRONMENT: esProduccion ? "production" : "staging",
      LOG_LEVEL: "INFO",

      // El contenedor corre como `atenea`, uid 10001 (Dockerfile), y Railway
      // monta la raíz del volumen como root. Sin esto, la primera escritura en
      // /data/material da EACCES y la primera subida de material devuelve un 500.
      // Tiene que ser la **cadena** "0": con el número, el SDK ni evalúa.
      //
      // Es una regresión de seguridad consciente: hace que el contenedor entero
      // corra como root y anula el `USER atenea` del Dockerfile. Se acepta a
      // cambio de poder escribir en el volumen, y se va el día que el material
      // viva en un bucket. La alternativa fina es un entrypoint con `gosu` que
      // haga `chown` y baje de privilegios; merece su propio cambio.
      RAILWAY_RUN_UID: "0",

      // La referencia tal cual, sin componer nada. Railway entrega esta URL con
      // el esquema estándar `postgresql://` y por el dominio privado, que no
      // paga egreso ni expone la base a internet; el backend le pone el driver
      // de psycopg3 al leerla (`Settings._con_driver`).
      //
      // Antes se componía a mano interpolando `base.env.PGUSER` y compañía en
      // una plantilla de texto. Una referencia del SDK es un objeto sin
      // `toString()`, así que lo que se habría desplegado era
      // `postgresql+psycopg://[object Object]:[object Object]@[object Object]…`,
      // y el plan no tenía forma de notarlo.
      DATABASE_URL: base.env.DATABASE_URL,

      // Ruta absoluta y dentro del volumen. El valor por defecto (`./storage`)
      // se resolvía fuera del directorio de la aplicación, donde el usuario del
      // contenedor no puede escribir: la primera subida daba un 500.
      STORAGE_DIR: "/data/material",

      WORKER_EN_PROCESO: "true",

      AI_PROVIDER: "claude",

      // OpenAI y no Voyage porque es la cuenta que ya existe. Son
      // intercambiables: mismas 512 dimensiones y misma métrica coseno.
      //
      // Cambiar de proveedor con material ya indexado obliga a reindexarlo: los
      // vectores de dos proveedores no se pueden comparar entre sí, y mientras
      // tanto la búsqueda por significado devolvería cualquier cosa. Por eso
      // `document_chunks.embedding_model` guarda con cuál se generó cada uno.
      EMBEDDINGS_PROVIDER: "openai",

      // Correo. Solo se usa para recuperar la contraseña, pero sin él el
      // arranque falla a propósito: dejaría a quien la olvide esperando un
      // mensaje que nadie envía.
      EMAIL_PROVIDER: "smtp",
      EMAIL_FROM: "Atenea <no-responder@atenea.cl>",
      SMTP_PORT: "587",

      CORS_ORIGINS: '["https://atenea.cl","https://www.atenea.cl"]',

      // Cargados a mano en el panel una sola vez. `preserve()` significa
      // "deja el valor que ya está en Railway": este archivo no los conoce y no
      // debe conocerlos.
      JWT_SECRET: preserve(),
      ANTHROPIC_API_KEY: preserve(),
      OPENAI_API_KEY: preserve(),
      SMTP_HOST: preserve(),
      SMTP_USER: preserve(),
      SMTP_PASSWORD: preserve(),
    },
  });

  return project("atenea", {
    resources: [api, base, material],
  });
});
