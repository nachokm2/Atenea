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
 *     railway config plan     # enseña qué cambiaría, sin cambiar nada
 *     railway config apply    # lo aplica tras confirmar
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
 * ## Secretos
 *
 * Ninguno se escribe aquí. `preserve()` significa "deja el valor que ya está en
 * Railway", así que se cargan una vez en el panel y este archivo no los conoce.
 * El arranque se niega a levantar la aplicación si alguno falta o es el de
 * desarrollo, así que un despliegue mal configurado se cae en vez de responder
 * 200 y hacer daño en silencio.
 */

import { defineRailway, github, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway((ctx) => {
  const esProduccion = ctx.environment === "production";

  const base = postgres("postgres");

  // El material del aprendiz. `sizeMB` se puede subir sin perder nada; bajarlo
  // o quitarlo es destructivo y Railway lo marca como tal antes de aplicar.
  const material = volume("material", { sizeMB: 5120 });

  const api = service("api", {
    source: github("nachokm2/Atenea", { branch: "main" }),

    // El Dockerfile espera su contexto en `backend/`.
    build: "docker",

    // Las migraciones y las semillas van **antes** del arranque, no dentro del
    // comando de inicio: si fallan, el despliegue se detiene y la versión
    // anterior sigue sirviendo. Ambas son idempotentes, así que repetirlas no
    // hace nada. Sin la siembra, una base recién migrada arranca sin
    // configuración de juego, sin niveles, sin objetos y sin misiones, y la app
    // respondería 200 a todo sin tener nada que mostrar.
    preDeploy: "alembic upgrade head && python -m app.seeds",

    start:
      "uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'",

    // La ruta del contrato es `/api/v1/health`; `/health` existe porque es la
    // que esperan las plataformas, que no saben del prefijo de versión. Apuntar
    // aquí a una ruta que devuelve 404 pone el servicio en bucle de reinicios
    // con la aplicación perfectamente sana.
    healthcheck: "/health",
    healthcheckTimeout: 30,

    // Una sola réplica mientras el material esté en disco: dos no compartirían
    // ni los archivos ni el contador del freno de peticiones.
    replicas: 1,

    volumeMounts: {
      "/data/material": material,
    },

    env: {
      ENVIRONMENT: esProduccion ? "production" : "staging",
      LOG_LEVEL: "INFO",

      // Railway publica `DATABASE_URL` con el esquema `postgresql://`, y el
      // backend usa psycopg3 síncrono: hay que armarla con el driver correcto.
      // El dominio privado evita pagar egreso y no expone la base a internet.
      DATABASE_URL: `postgresql+psycopg://${base.env.PGUSER}:${base.env.PGPASSWORD}@${base.env.RAILWAY_PRIVATE_DOMAIN}:5432/${base.env.PGDATABASE}`,

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
