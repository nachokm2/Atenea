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

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repositorio: backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> raíz
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
BACKEND_ROOT: Path = Path(__file__).resolve().parents[2]
ENV_FILE: Path = PROJECT_ROOT / ".env"


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
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # ------------------------------------------------------------------
    # Seguridad
    # ------------------------------------------------------------------
    jwt_secret: str = "dev-solo-para-local-no-usar-en-produccion"
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

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        """Normaliza el nivel de log a mayúsculas."""
        return value.upper()

    @field_validator("embeddings_dim")
    @classmethod
    def _check_embeddings_dim(cls, value: int) -> int:
        """El contrato fija `Vector(512)`: cambiarlo exige reindexar y actualizar CONTRACT.md."""
        if value <= 0:
            raise ValueError("embeddings_dim debe ser un entero positivo")
        return value

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
