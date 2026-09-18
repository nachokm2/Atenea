"""Configuración de la aplicación (12-factor) leída del `.env` de la raíz y del entorno.

Regla de oro del contrato (§8.10, regla 5): los **parámetros de juego** viven en la
tabla `game_configs` y jamás se escriben como literal en el código. Lo que hay aquí
son **parámetros de infraestructura y de plataforma**: credenciales, URLs, modelos de
IA y los topes duros de subida y de plan gratuito que el servidor necesita **antes**
de tocar la base de datos (validación de un fichero entrante, por ejemplo).

Cuando una clave de `game_configs` existe para el mismo concepto (`ingestion.max_file_mb`,
`ai.quotas_per_day`…), **manda `game_configs`**; los campos de aquí son el valor por
defecto y el respaldo cuando la configuración de juego aún no está cargada.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repositorio: backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> raíz
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
BACKEND_ROOT: Path = Path(__file__).resolve().parents[2]
ENV_FILE: Path = PROJECT_ROOT / ".env"

#: Secreto de firma de desarrollo. Está publicado en el repositorio, así que
#: cualquiera que lo conozca puede firmar un token con el identificador de otro
#: usuario. En producción el arranque lo rechaza (ver `_exigir_produccion_seria`).
SECRETO_DE_DESARROLLO: str = "dev-solo-para-local-no-usar-en-produccion"

#: Longitud mínima de un secreto de firma que se pueda tomar en serio.
MINIMO_SECRETO: int = 32


class Settings(BaseSettings):
    """Ajustes del backend de Atenea.

    Todos los campos se pueden sobrescribir por variable de entorno con el mismo
    nombre en MAYÚSCULAS (`DATABASE_URL`, `JWT_SECRET`, …). Los valores por defecto
    son seguros para desarrollo local y nunca para producción.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Entorno y observabilidad
    # ------------------------------------------------------------------
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    app_name: str = "Atenea API"
    api_v1_prefix: str = "/api/v1"

    # ------------------------------------------------------------------
    # Base de datos (psycopg3 síncrono; prohibido async en la capa de datos)
    # ------------------------------------------------------------------
    database_url: str = "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea"
    """URL de la base. Se acepta también la forma estándar, sin el driver.

    Toda plataforma que provisiona un PostgreSQL entrega su URL como
    `postgresql://…` (Railway, Fly, Supabase) o como `postgres://…` (la forma
    antigua de Heroku, que SQLAlchemy ya no reconoce). Atenea usa psycopg3
    síncrono, así que necesita `postgresql+psycopg://`.

    Antes había que reescribir esa URL a mano en la configuración del despliegue,
    componiéndola pieza a pieza a partir de usuario, contraseña y dominio
    privado. Eso es exactamente donde se coló un fallo que no se veía en local:
    la URL compuesta acababa siendo literalmente
    `postgresql+psycopg://[object Object]:[object Object]@…`. Normalizar aquí
    permite pasar la referencia de la plataforma tal cual, sin componer nada.
    """

    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # ------------------------------------------------------------------
    # Seguridad
    # ------------------------------------------------------------------
    jwt_secret: str = SECRETO_DE_DESARROLLO
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 30
    jwt_refresh_ttl_days: int = 60
    jwt_issuer: str = "atenea"
    bcrypt_rounds: int = 12

    # ------------------------------------------------------------------
    # Proveedor de IA
    # ------------------------------------------------------------------
    ai_provider: Literal["mock", "claude"] = "mock"
    anthropic_api_key: str | None = None
    ai_model_architect: str = "claude-opus-5"
    ai_model_author: str = "claude-sonnet-5"
    ai_model_judge: str = "claude-haiku-4-5"

    # ------------------------------------------------------------------
    # Embeddings (el contrato fija 512 dimensiones, `Vector(512)`, coseno)
    # ------------------------------------------------------------------
    embeddings_provider: Literal["mock", "voyage", "openai"] = "mock"
    embeddings_dim: int = 512
    voyage_api_key: str | None = None
    openai_api_key: str | None = None

    # ------------------------------------------------------------------
    # Almacenamiento de material del usuario
    # ------------------------------------------------------------------
    storage_dir: str = "./storage"

    #: Corre el procesador de trabajos dentro del propio proceso de la API.
    #:
    #: Hace falta mientras el material del aprendiz viva en disco: un volumen se
    #: monta en un solo servicio, así que una API y un worker separados no
    #: comparten archivos y la ingesta no encontraría nunca el documento que se
    #: acaba de subir. Con el material en un bucket, esto se apaga y el worker
    #: vuelve a ser un servicio aparte, que escala mejor.
    worker_en_proceso: bool = False

    # ------------------------------------------------------------------
    # Límites de subida (respaldo de `ingestion.*` en `game_configs`)
    # ------------------------------------------------------------------
    max_file_mb: int = Field(default=25, description="`ingestion.max_file_mb`")
    max_pdf_pages: int = Field(default=300, description="`ingestion.max_pdf_pages`")
    max_files_per_path: int = Field(default=10, description="`ingestion.max_files_per_path`")
    max_corpus_tokens: int = Field(default=150_000, description="`ingestion.max_corpus_tokens`")
    min_words_for_path: int = Field(default=300, description="`ingestion.min_words_for_path`")
    max_ingest_minutes: int = Field(default=5, description="`ingestion.max_ingest_minutes`")
    purge_documents_after_days: int = Field(default=30, description="`ingestion.purge_after_days`")

    # ------------------------------------------------------------------
    # Cuotas del plan gratuito (respaldo de `ai.quotas_per_day` en `game_configs`)
    # ------------------------------------------------------------------
    free_path_designs_per_day: int = 2
    free_active_paths: int = 3
    free_re_explanations_per_day: int = 10
    free_judged_answers_per_day: int = 50
    free_content_reports_per_day: int = 10
    free_upload_mb_per_day: int = 100
    free_module_regenerations_per_day: int = 2
    ai_global_budget_usd_per_day: int = 30

    # ------------------------------------------------------------------
    # Paginación y límite de peticiones (§8.2 y §8.7)
    # ------------------------------------------------------------------
    page_limit_default: int = 20
    page_limit_max: int = 100
    rate_limit_default: str = "60/minute"
    rate_limit_login: str = "10/minute"
    #: Registrar también hashea con bcrypt de coste 12, así que el argumento del
    #: acceso vale igual aquí. Y además crea filas: con el freno general de 60
    #: por minuto, abrir cuentas en masa salía barato. Dos ventanas porque una
    #: sola no defiende de lo que hay que defender —diez por minuto son catorce
    #: mil cuentas al día—: la corta corta la ráfaga, la larga el goteo.
    rate_limit_register: str = "10/minute;60/hour"
    rate_limit_ai: str = "6/minute"
    rate_limit_upload: str = "12/minute"

    # ------------------------------------------------------------------
    # Correo (solo para recuperar la contraseña)
    # ------------------------------------------------------------------
    #: `consola` escribe el mensaje en el registro en vez de enviarlo: sirve para
    #: recorrer el flujo entero en local sin dar de alta ningún servicio. En
    #: producción es un error de arranque, porque dejaría a quien olvide su
    #: contraseña esperando un correo que nadie envió.
    email_provider: Literal["consola", "smtp"] = "consola"
    email_from: str = "Atenea <no-responder@atenea.cl>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None

    #: A quién se avisa cuando algo va mal en el servicio. No es la dirección de
    #: ningún aprendiz: es la de quien opera el Reino.
    #:
    #: Sin ella, el aviso no se envía y queda anotado en el registro. A propósito
    #: no entra en las comprobaciones de arranque: añadir un motivo nuevo de
    #: caída a un despliegue vivo, por un aviso, sale más caro que el aviso.
    #:
    #: Conviene que no sea un correo institucional con filtros ajenos, sino uno
    #: que suene en el teléfono. Y como `email_from` es `no-responder@atenea.cl`,
    #: el primer aviso tiene números de acabar en la carpeta de no deseado: vale
    #: la pena mandarse uno de prueba y marcarlo antes de fiarse.
    alert_email: str | None = None

    #: Cuánto vive el permiso para elegir una contraseña nueva. Corto a
    #: propósito: es una llave a la cuenta viajando por correo.
    password_reset_ttl_min: int = 30

    #: Dónde abre la app el enlace del correo. En móvil es un enlace profundo.
    password_reset_url: str = "atenea://password/reset"

    #: Reportes de personas distintas que hacen falta para retirar una pregunta
    #: de una Ruta del Reino. En el material propio basta con uno: es del
    #: aprendiz. En el compartido, retirarlo afecta a todos, y con un solo
    #: reporte una cuenta nueva podía dejar la Ruta semilla sin preguntas.
    content_flag_threshold: int = 3

    # ------------------------------------------------------------------
    # Orígenes permitidos del cliente web (CORS)
    # ------------------------------------------------------------------
    #: En desarrollo se acepta cualquier `localhost`. En producción hay que
    #: enumerarlos: sin esta lista el servidor se negaba a nada y CORS quedaba
    #: en comodín, porque el campo no existía y `getattr` devolvía vacío.
    cors_origins: list[str] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        """Normaliza el nivel de log a mayúsculas."""
        return value.upper()

    @field_validator("database_url")
    @classmethod
    def _con_driver(cls, value: str) -> str:
        """Le pone el driver a una URL estándar de PostgreSQL.

        `postgresql://` y `postgres://` se convierten en `postgresql+psycopg://`.
        Cualquier otra cosa se deja intacta: si alguien pone un driver distinto a
        propósito, sabrá lo que hace, y si pone una barbaridad, es mejor que falle
        al conectar con su propio texto delante que con uno reescrito por aquí.
        """
        for prefijo in ("postgresql://", "postgres://"):
            if value.startswith(prefijo):
                return "postgresql+psycopg://" + value[len(prefijo) :]
        return value

    @field_validator("embeddings_dim")
    @classmethod
    def _check_embeddings_dim(cls, value: int) -> int:
        """El contrato fija `Vector(512)`: cambiarlo exige reindexar y actualizar CONTRACT.md."""
        if value <= 0:
            raise ValueError("embeddings_dim debe ser un entero positivo")
        return value

    @model_validator(mode="after")
    # `self`, no `cls`: un validador de modo `after` recibe la instancia ya
    # construida. Con `cls`, Pydantic no reconoce la firma y la aplicación no
    # arranca en ningún entorno.
    def _exigir_produccion_seria(self) -> Settings:  # noqa: N804 - modo `after`
        """Se niega a arrancar en producción con la configuración de juguete.

        Un servidor mal configurado no falla: responde 200 y hace daño en
        silencio. Con el secreto por defecto cualquiera firma un token ajeno y
        lee el material de otro; con el proveedor simulado el aprendiz recibe
        lecciones inventadas que parecen buenas; con CORS en comodín cualquier
        página puede hablar con la API en nombre de quien la visite.

        Por eso el arranque se cae aquí, que es el único momento en que el fallo
        se ve. `staging` cuenta como producción a todos estos efectos.
        """
        if not self.is_production:
            return self

        faltas: list[str] = []
        if self.jwt_secret == SECRETO_DE_DESARROLLO:
            faltas.append(
                "JWT_SECRET sigue siendo el de desarrollo, que está publicado en el repositorio"
            )
        elif len(self.jwt_secret) < MINIMO_SECRETO:
            faltas.append(f"JWT_SECRET necesita al menos {MINIMO_SECRETO} caracteres")

        if self.ai_provider == "mock":
            faltas.append("AI_PROVIDER es 'mock': se servirían lecciones inventadas")
        elif self.ai_provider == "claude" and not self.anthropic_api_key:
            faltas.append("AI_PROVIDER es 'claude' pero falta ANTHROPIC_API_KEY")

        if self.embeddings_provider == "mock":
            faltas.append(
                "EMBEDDINGS_PROVIDER es 'mock': la búsqueda por significado no encontraría nada"
            )
        elif self.embeddings_provider == "voyage" and not self.voyage_api_key:
            faltas.append("EMBEDDINGS_PROVIDER es 'voyage' pero falta VOYAGE_API_KEY")
        elif self.embeddings_provider == "openai" and not self.openai_api_key:
            faltas.append("EMBEDDINGS_PROVIDER es 'openai' pero falta OPENAI_API_KEY")

        if not self.cors_origins:
            faltas.append(
                "CORS_ORIGINS está vacío: sin orígenes declarados CORS quedaría en comodín"
            )

        if self.email_provider == "consola":
            faltas.append(
                "EMAIL_PROVIDER es 'consola': quien olvide su contraseña esperaría "
                "un correo que nadie envía"
            )

        if faltas:
            detalle = "\n  - ".join(faltas)
            raise ValueError(
                f"Atenea no puede arrancar en '{self.environment}':\n  - {detalle}\n"
                "Corrige esas variables de entorno (ver .env.example) y vuelve a desplegar."
            )
        return self

    # ------------------------------------------------------------------
    # Derivados
    # ------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        """`True` en producción o staging: activa logs JSON y desactiva detalles técnicos."""
        return self.environment in ("production", "staging")

    @property
    def is_development(self) -> bool:
        """`True` en desarrollo local."""
        return self.environment == "development"

    @property
    def is_test(self) -> bool:
        """`True` durante la suite de pruebas."""
        return self.environment == "test"

    @property
    def storage_path(self) -> Path:
        """Ruta absoluta del directorio de almacenamiento, resuelta desde la raíz del proyecto."""
        raw = Path(self.storage_dir).expanduser()
        return raw if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()

    @property
    def max_file_bytes(self) -> int:
        """Tamaño máximo de fichero en bytes."""
        return self.max_file_mb * 1024 * 1024

    def ensure_storage_dir(self) -> Path:
        """Crea el directorio de almacenamiento si no existe y devuelve su ruta."""
        path = self.storage_path
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la instancia cacheada de `Settings` (dependencia de FastAPI)."""
    return Settings()


#: Instancia global de configuración. Los módulos la importan directamente.
settings: Settings = get_settings()

__all__ = ["BACKEND_ROOT", "ENV_FILE", "PROJECT_ROOT", "Settings", "get_settings", "settings"]
