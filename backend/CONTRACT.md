# CONTRATO TÉCNICO DEL BACKEND — PROYECTO ATENEA

> **Estado:** normativo y vinculante. Versión 1.0 · 2026-09-10 · Autor: arquitecto técnico principal.
> **Alcance:** este documento es la **única fuente de verdad** para los agentes de construcción del backend. Los documentos de diseño (`docs/00-brief-producto.md`, `docs/auditoria/01`, `04`, `06a`, `06b`, `06c`, `07`, `anexos/A1`) ya fueron leídos, reconciliados y condensados aquí. **Ningún agente de construcción debe volver a leerlos**: si algo no está en este contrato, no existe.
> **Regla de oro:** cada nombre escrito aquí (clase, tabla, columna, enum, valor de enum, clave de configuración, evento, ruta) se teclea **literalmente** en el código. No se traduce, no se abrevia, no se pluraliza distinto, no se "mejora".

---

## Índice

1. [Resumen del sistema](#1-resumen-del-sistema)
2. [Catálogo de enums (`app/models/enums.py`)](#2-catálogo-de-enums-appmodelsenumspy)
3. [Catálogo de tablas](#3-catálogo-de-tablas)
4. [Catálogo de eventos de dominio](#4-catálogo-de-eventos-de-dominio)
5. [Parámetros de juego (`game_configs`)](#5-parámetros-de-juego-game_configs)
6. [Fórmulas exactas](#6-fórmulas-exactas)
7. [Mapa de rutas de la API v1](#7-mapa-de-rutas-de-la-api-v1)
8. [Convenciones transversales](#8-convenciones-transversales)

---

# 1. Resumen del sistema

## 1.1 Qué se construye

**Atenea** es un RPG medieval de aprendizaje: el usuario carga material propio (o elige una ruta del catálogo) y la IA lo convierte en una **ruta de aprendizaje jugable** (Conocimiento → Ruta → Módulo → Tema → Lección → Actividades, con una Evaluación por módulo). El progreso intelectual **es** la progresión del personaje: XP, niveles, oro, racha, misiones, logros, inventario y equipamiento se ganan exclusivamente demostrando aprendizaje.

Tres medidores se calculan, almacenan y muestran **por separado** y nunca se derivan entre sí:

| Medidor | Qué mide | Fuente de verdad | ¿Puede bajar? |
|---|---|---|---|
| ⭐ **XP** (y ⚔️ nivel, derivado) | Progresión de juego | Ledger `xp_transactions` (append-only) | Nunca |
| ⏱ **Tiempo** | Dedicación | `study_activities.active_seconds` + `learning_sessions` | Nunca |
| 🧠 **Dominio** | Conocimiento demostrado | `question_attempts` + `assessment_attempts` | Sí, por decaimiento; se recupera con repaso |

**El tiempo nunca alimenta XP ni dominio.** El oro nunca compra XP, dominio ni contenido educativo.

Jerarquía normativa del contenido (resuelve la ambigüedad "tema" del brief):

```
Conocimiento (knowledge_areas)  =  territorio del mapa
  └── Ruta (learning_paths)
        └── Módulo (path_modules)  =  zona del territorio, termina en una Evaluación
              └── Tema (topics)    =  unidad de dominio fino
                    └── Lección (lessons)
                          └── Bloques (lesson_blocks) y Preguntas (questions)
```

## 1.2 Stack elegido (Anexo A1, veredicto del panel)

| Capa | Elección | Notas vinculantes |
|---|---|---|
| App móvil | **Flutter** (Dart 3) | Fuera del alcance de este contrato salvo por el contrato de API (§7). |
| Backend | **Python 3.12 · FastAPI 0.115 · Pydantic v2 · SQLAlchemy 2.0 · Alembic** | Monolito modular. **psycopg3 síncrono**. Prohibido `async` en la capa de base de datos. |
| Base de datos | **PostgreSQL 16 + pgvector 0.8** | Única pieza de datos: OLTP + vectores + FTS + eventos de dominio. |
| Vectorial | `pgvector`, `Vector(512)`, índice **HNSW** `vector_cosine_ops` (`m=16`, `ef_construction=128`) + `tsvector('spanish')` con fusión RRF (`k=60`) | Embeddings Voyage `voyage-3-lite`, 512 dimensiones. |
| IA | **Anthropic Claude**: `claude-opus-5` (diseño de ruta), `claude-sonnet-5` (lecciones, preguntas, re-explicación, juez escalado), `claude-haiku-4-5` (juez corto, verificación, narrativa) | IDs de modelo en `game_configs`, nunca en código. |
| Corrección técnica | **DuckDB** embebido en el worker + `sqlglot` para validar SQL | Determinista, coste 0. |
| Hosting | **Railway** (API + worker + Postgres/pgvector + bucket) | Todo dockerizado y 12-factor. |
| Auth | **JWT propio** (`pyjwt`), contraseñas con `bcrypt` vía `passlib`, refresh tokens rotatorios en base de datos | Tabla `users` propia; `AuthProvider` deja abierta la puerta a Google/Apple. |

## 1.3 Límites de módulo del monolito modular

Siete módulos. Cada uno es un paquete en `app/modules/<módulo>/` con su lógica de negocio. **Los modelos de todos los módulos viven en `app/models/`, un archivo por módulo de datos** (para que Alembic vea un solo `Base.metadata`), pero la **propiedad lógica** de cada tabla es la de esta tabla:

| Módulo | Responsabilidad | Archivo de modelos |
|---|---|---|
| `identity` | Cuentas, sesiones JWT, ajustes, personaje, avatar y equipamiento visible | `app/models/identity.py` |
| `content` | Taxonomía de conocimientos, territorios, rutas, módulos, temas, lecciones, bloques, preguntas y evaluaciones. **Contenido reutilizable, sin datos de progreso.** | `app/models/content.py` |
| `ingestion` | Bibliotecas, documentos, versiones, fragmentos, embeddings, trabajos de generación y trazabilidad | `app/models/ingestion.py` |
| `ai` | Orquestación de Claude y del proveedor de embeddings: diseño de ruta, generación perezosa, juez de respuestas abiertas, re-explicación, sandbox DuckDB. **No posee tablas propias**: escribe en `generation_jobs`, `prompt_templates`, `content_provenance` (archivo `ingestion.py`) y en las tablas de `content`. | — |
| `progress` | Progreso por usuario, evidencias de respuesta, dominio, sesiones y tiempo de estudio | `app/models/progress.py` |
| `gamification` | Eventos de dominio, XP, niveles, rachas, objetivo diario, misiones, logros, reglas de recompensa, configuración de juego, notificaciones | `app/models/gamification.py` |
| `economy` | Ítems, requisitos de desbloqueo, inventario, billetera, ledger de oro, tienda y compras | `app/models/economy.py` |

**Dirección de dependencias permitida** (nunca al revés):

```
identity  ←  content  ←  ingestion / ai
    ↑           ↑
    └── progress ──→ gamification ──→ economy
```

- `content` **no** conoce el progreso de ningún usuario; `progress` referencia contenido por id.
- `gamification` es el único que escribe `xp_transactions`, `streaks`, `streak_days`, `user_missions`, `user_achievements`, `notifications`.
- `economy` es el único que escribe `wallets`, `gold_transactions`, `user_items`, `equipped_items` (delegado por `identity`), `purchases`.
- La comunicación entre módulos en tiempo de ejecución se hace **por eventos de dominio** (`domain_events`, §4), nunca importando servicios de otro módulo.

## 1.4 Convenciones de código obligatorias (idénticas para todos los agentes)

1. **Python 3.12**, FastAPI 0.115, SQLAlchemy 2.0 en estilo declarativo moderno (`DeclarativeBase`, `Mapped`, `mapped_column`), Pydantic v2, **psycopg3 síncrono**. Prohibido `async def` en repositorios, servicios de datos y sesiones.
2. **JSON siempre** `from sqlalchemy.dialects.postgresql import JSONB`. **Embeddings siempre** `from pgvector.sqlalchemy import Vector`.
3. **Clave primaria**: columna `id`, tipo `postgresql.UUID(as_uuid=True)`, `default=uuid.uuid4`. **Todas** las tablas, sin excepción; las claves naturales se expresan como `UniqueConstraint`.
4. **Fechas**: `DateTime(timezone=True)`, siempre UTC. `created_at` con `server_default=func.now()`; `updated_at` con `server_default=func.now(), onupdate=func.now()` donde aplique. Las tablas **append-only** (`xp_transactions`, `gold_transactions`, `question_attempts`, `content_provenance`, `domain_events`) llevan **solo** `created_at`.
5. **Tipos numéricos**: XP, oro, precios y segundos → `Integer` (`BigInteger` solo en acumulados de XP). Dominio y porcentajes → `Numeric(5, 2)` en escala **0.00–100.00**. Multiplicadores → `Numeric(5, 3)`. Costos en USD → `Numeric(10, 6)`.
6. **Enums**: se definen **solo** en `app/models/enums.py` como `class Nombre(StrEnum)`. En columnas: `sa.Enum(Nombre, native_enum=False, length=48, validate_strings=True)`.
   **Consecuencia verificada y crítica**: con esa receta la columna es un `VARCHAR(48)` **sin `CHECK`** y SQLAlchemy persiste el **nombre del miembro en MAYÚSCULAS** (`MYTHIC`), no su valor (`mythic`). Por lo tanto:
   - Todo `CheckConstraint`, `server_default` y SQL crudo (migraciones, semillas, consultas de analítica) usa el **nombre**: `server_default="EMAIL"`, `sa.CheckConstraint("origin <> 'KNOWLEDGE'")`, `WHERE status = 'COMPLETED'`.
   - En Python se compara siempre con el miembro del enum (`Item.origin == ItemOrigin.KNOWLEDGE`), nunca con una cadena.
   - La API sigue exponiendo el **valor** (`"knowledge"`), porque Pydantic serializa el `StrEnum` por su valor. Esa asimetría es deliberada y no se "arregla" añadiendo `values_callable`.
   - Añadir un valor a un enum **no requiere migración** (no hay tipo nativo ni `CHECK` que recrear).
   - Modo de fallo comprobado: si un `server_default` guarda el valor en minúsculas (`server_default="gold"`), la **lectura** de esa fila revienta con `LookupError: 'gold' is not among the defined enum values`. Escribe siempre `server_default=Currency.GOLD.name`.
7. **Nombres de tabla** en `snake_case` y **plural**. Todas las restricciones se nombran por la `naming_convention` del `Base`.
8. **REGLA CRÍTICA ANTI-CONFLICTO**: prohibido `relationship()` entre archivos de modelos distintos. Las claves foráneas se declaran con destino en texto: `ForeignKey("users.id", ondelete="CASCADE")`. Solo se permite `relationship()` entre clases del **mismo** archivo. Nunca importes otro archivo de `app/models/` desde un archivo de `app/models/`; las únicas excepciones son `app.models.enums` y `app.core.db`.
9. Cada agente escribe **solo** los archivos que se le asignan (§8.9). No se modifican archivos de otros agentes. No se crea `app/models/__init__.py` salvo asignación explícita.
10. **Idioma**: identificadores, nombres de tabla y de columna en **inglés**; docstrings, comentarios y textos de cara al usuario en **español**.
11. **Server-authoritative**: el cliente informa hechos (empecé, respondí, terminé); el servidor decide y persiste toda recompensa. El cliente **jamás** envía cantidades de XP, oro, dominio ni precios como verdad.

## 1.5 Base declarativa canónica (`app/core/db.py`)

Todos los archivos de modelos importan de aquí. Este código es normativo y está **verificado** contra PostgreSQL 16.15 + pgvector 0.8.6 con SQLAlchemy 2.0.36:

```python
"""Base declarativa, convención de nombres y mixins comunes de Atenea."""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import MetaData, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa única del proyecto. Alembic autogenera desde Base.metadata."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """Clave primaria UUID estándar de Atenea."""

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class CreatedAtMixin:
    """Solo fecha de creación: para tablas append-only (ledgers, eventos, evidencias)."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """Fechas de creación y actualización, en UTC."""

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

Forma canónica de una tabla (patrón que todos los agentes repiten):

```python
class LessonBlock(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Bloque ordenado de una lección (explicación, ejemplo, pregunta intercalada…)."""

    __tablename__ = "lesson_blocks"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    block_type: Mapped[LessonBlockType] = mapped_column(
        sa.Enum(LessonBlockType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )

    __table_args__ = (
        sa.UniqueConstraint("lesson_id", "position"),
        sa.Index("ix_lesson_blocks_lesson_id", "lesson_id"),
    )
```

Notas verificadas en la base de datos de desarrollo:

- `sa.UniqueConstraint("lesson_id", "position")` produce `uq_lesson_blocks_lesson_id_position`; `sa.CheckConstraint("xp >= 0", name="xp_non_negative")` produce `ck_<tabla>_xp_non_negative`; cada `ForeignKey` produce `fk_<tabla>_<columna>_<tabla_destino>`. **Si el nombre autogenerado supera 63 caracteres hay que pasar `name=` explícito** (límite de identificador de PostgreSQL).
- Columna vectorial: `embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)`.
- Columna FTS: `search_vector: Mapped[str | None] = mapped_column(TSVECTOR, sa.Computed("to_tsvector('spanish', coalesce(text, ''))", persisted=True), nullable=True)` (importar `TSVECTOR` de `sqlalchemy.dialects.postgresql`).
- Los índices **HNSW y GIN se crean a mano en la migración de Alembic** con `op.execute(...)`, no con `sa.Index`.
- Valores por defecto en JSONB: `server_default=sa.text("'{}'::jsonb")` para objetos y `sa.text("'[]'::jsonb")` para listas.
---

# 2. Catálogo de enums (`app/models/enums.py`)

Este archivo lo escribe **un solo agente** y lo importan todos los demás. **Es el contenido literal del archivo**: cópialo tal cual, en este orden, sin renombrar miembros ni valores. Si un módulo necesita un enum nuevo, se pide al arquitecto; no se define fuera de aquí.

Reglas:

- `class Nombre(StrEnum)`; miembro en `MAYÚSCULAS`, valor en `snake_case` **en inglés**, salvo las tres excepciones marcadas (`PathSourceMode`, `MissionScope`, `GoalType`), cuyos valores son literales en español fijados por el diseño de producto, y `EventType`, cuyos valores son el nombre del evento en `MAYÚSCULAS_CON_GUION_BAJO`.
- En columnas siempre: `sa.Enum(Nombre, native_enum=False, length=48, validate_strings=True)`. La columna resultante es un `VARCHAR(48)` **sin `CHECK`**: la validación ocurre en Python (`validate_strings=True`) y **lo que se guarda es el nombre del miembro en MAYÚSCULAS** (ver §1.4, regla 6). Añadir un valor no requiere migración.

```python
"""Catálogo único de enumeraciones de Atenea.

Todos los valores son contrato con la app Flutter y con la base de datos:
no se renombran ni se reordenan sin actualizar CONTRACT.md.
"""
from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# Identidad, personaje y avatar
# ---------------------------------------------------------------------------


class UserRole(StrEnum):
    """Rol de la cuenta. El MVP solo crea LEARNER; ADMIN se siembra a mano."""

    LEARNER = "learner"
    ADMIN = "admin"
    SUPPORT = "support"


class AuthProvider(StrEnum):
    """Origen de la credencial. EMAIL es el único activo en el MVP."""

    EMAIL = "email"
    GOOGLE = "google"
    APPLE = "apple"


class CharacterArchetype(StrEnum):
    """Orden a la que pertenece el personaje. Puramente narrativo y visual.

    Los cuatro primeros son del MVP; el resto son fase 2 y no se ofrecen todavía.
    Nombre de la Orden y títulos por forma de tratamiento viven en `game_configs`
    bajo `character.archetypes`.
    """

    STEEL = "steel"                    # Orden del Acero
    ARCANE = "arcane"                  # Círculo del Arcano
    FOREST = "forest"                  # Hermandad del Bosque
    WALL = "wall"                      # Vigilia del Muro
    BANNER = "banner"                  # Compañía del Estandarte (fase 2)
    CROWN = "crown"                    # Casa de la Corona (fase 2)
    RUNES = "runes"                    # Cofradía de las Runas (fase 2)
    ANCIENT_FOREST = "ancient_forest"  # Linaje del Bosque Antiguo (fase 2)


class BodyType(StrEnum):
    """Silueta del avatar. El MVP usa solo NEUTRAL (una única silueta)."""

    NEUTRAL = "neutral"
    SLIM = "slim"
    STOUT = "stout"


class AddressForm(StrEnum):
    """Forma gramatical con la que el juego se dirige al usuario."""

    MASCULINE = "m"
    FEMININE = "f"
    NEUTRAL = "n"


class ThemePreference(StrEnum):
    """Preferencia de tema visual de la app."""

    SYSTEM = "system"
    DARK = "dark"
    LIGHT = "light"


class ReminderMode(StrEnum):
    """Modo del recordatorio diario."""

    SMART = "smart"
    MANUAL = "manual"
    OFF = "off"


# ---------------------------------------------------------------------------
# Conocimiento, rutas y contenido
# ---------------------------------------------------------------------------


class KnowledgeCategory(StrEnum):
    """Categoría de un conocimiento; tinta los ítems derivados por plantilla."""

    DATA = "data"
    PROGRAMMING = "programming"
    CLOUD = "cloud"
    AI = "ai"
    BUSINESS = "business"
    LANGUAGES = "languages"
    SCIENCE = "science"
    HUMANITIES = "humanities"
    ARTS = "arts"
    HEALTH = "health"
    LAW = "law"
    OTHER = "other"


class KnowledgeAreaStatus(StrEnum):
    """Estado de dominio de un conocimiento o de un tema para un usuario."""

    NO_EVIDENCE = "no_evidence"
    IN_PROGRESS = "in_progress"
    MASTERED = "mastered"
    AT_RISK = "at_risk"
    WEAKENED = "weakened"


class TerritoryStatus(StrEnum):
    """Estado visual del territorio en el mapa."""

    FOGGED = "fogged"
    DISCOVERED = "discovered"
    COMPLETED = "completed"


class PathOrigin(StrEnum):
    """Quién creó la ruta. SEED = 'Ruta del Reino' curada por el equipo."""

    SEED = "seed"
    USER = "user"


class PathStatus(StrEnum):
    """Ciclo de vida de la ruta (contenido, no progreso del usuario)."""

    DRAFT = "draft"
    GENERATING = "generating"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    FAILED = "failed"


class PathSourceMode(StrEnum):
    """Respaldo documental de la ruta. Valores en español por decisión de producto."""

    WITH_SOURCE = "con_fuente"
    WITHOUT_SOURCE = "sin_fuente"
    MIXED = "mixta"


class CoveragePolicy(StrEnum):
    """Qué hacer con los temas sin respaldo suficiente en el material."""

    SOURCE_ONLY = "source_only"
    MODEL_KNOWLEDGE = "model_knowledge"
    REQUEST_MORE = "request_more"


class CoverageLevel(StrEnum):
    """Cobertura del material para un tema."""

    FULL = "full"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class DeclaredLevel(StrEnum):
    """Nivel declarado por el usuario al crear la ruta."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class DifficultyLevel(StrEnum):
    """Dificultad de una pregunta, tema o módulo. Pesos de dominio: 1.0 / 1.5 / 2.0."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ContentStatus(StrEnum):
    """Estado de generación del contenido (módulo, tema, lección, pregunta)."""

    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    NEEDS_ATTENTION = "needs_attention"
    FLAGGED = "flagged"
    SUPERSEDED = "superseded"


class ModuleStatus(StrEnum):
    """Estado del módulo para un usuario (progreso)."""

    LOCKED = "locked"
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MASTERED = "mastered"


class ProgressState(StrEnum):
    """Estado genérico de progreso para ruta y lección."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class LessonBlockType(StrEnum):
    """Tipos de bloque de una lección, en el orden habitual de aparición."""

    EXPLANATION = "explanation"
    EXAMPLE = "example"
    CODE_EXAMPLE = "code_example"
    DIAGRAM = "diagram"
    INLINE_QUESTION = "inline_question"
    SUMMARY = "summary"


class QuestionType(StrEnum):
    """Los 7 tipos del MVP más 2 reservados para fase 2/3.

    Los reservados NO se generan en el MVP: el validador de contenido rechaza
    CASE_STUDY y CODE_EXERCISE.
    """

    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    MATCHING = "matching"
    ORDERING = "ordering"
    OPEN_SHORT = "open_short"
    SQL_EXERCISE = "sql_exercise"
    CASE_STUDY = "case_study"          # reservado, fase 2
    CODE_EXERCISE = "code_exercise"    # reservado, fase 3


class ActivityContext(StrEnum):
    """Contexto en el que se respondió una pregunta. Pesa en el dominio."""

    LESSON = "lesson"
    PRACTICE = "practice"
    REVIEW = "review"
    CHALLENGE = "challenge"
    ASSESSMENT = "assessment"


class EvaluationMethod(StrEnum):
    """Cómo se corrigió la respuesta."""

    DETERMINISTIC = "deterministic"
    SANDBOX = "sandbox"
    LLM_JUDGE = "llm_judge"
    PENDING = "pending"


class AttemptResult(StrEnum):
    """Resultado de una respuesta individual."""

    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"


class AttemptStatus(StrEnum):
    """Estado de un intento de actividad o de evaluación."""

    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EXPIRED = "expired"
    ABANDONED = "abandoned"


class AssessmentOutcome(StrEnum):
    """Resultado de un intento de evaluación de módulo."""

    FAILED = "failed"
    PASSED = "passed"
    PASSED_DISTINCTION = "passed_distinction"  # >= 90 %
    PASSED_PERFECT = "passed_perfect"          # 100 %


class StudyActivityType(StrEnum):
    """Tipo de actividad de estudio (intento abierto por el usuario)."""

    LESSON = "lesson"
    PRACTICE = "practice"
    REVIEW = "review"
    CHALLENGE = "challenge"
    ASSESSMENT = "assessment"


class SessionEndReason(StrEnum):
    """Motivo de cierre de una sesión de estudio."""

    IDLE_TIMEOUT = "idle_timeout"
    APP_CLOSED = "app_closed"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# Ingesta documental e IA
# ---------------------------------------------------------------------------


class DocumentType(StrEnum):
    """Formato de origen del material. URL e IMAGE son fase 2."""

    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    TXT = "txt"
    PASTED_TEXT = "pasted_text"
    URL = "url"      # reservado, fase 2
    IMAGE = "image"  # reservado, fase 2


class DocumentStatus(StrEnum):
    """Estado del documento o de una de sus versiones."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class ChunkType(StrEnum):
    """Naturaleza del fragmento, detectada por heurísticas en la ingesta."""

    PROSE = "prose"
    CODE = "code"
    TABLE = "table"
    LIST = "list"


class JobType(StrEnum):
    """Tipo de trabajo de generación o procesamiento. También clasifica prompts."""

    DOCUMENT_INGESTION = "document_ingestion"
    EMBEDDING_BATCH = "embedding_batch"
    PATH_DESIGN = "path_design"
    MODULE_GENERATION = "module_generation"
    LESSON_GENERATION = "lesson_generation"
    QUESTION_GENERATION = "question_generation"
    ASSESSMENT_COMPLEMENT = "assessment_complement"
    ANSWER_JUDGEMENT = "answer_judgement"
    SQL_EVALUATION = "sql_evaluation"
    RE_EXPLANATION = "re_explanation"
    REMEDIAL_EXERCISES = "remedial_exercises"
    GROUNDEDNESS_CHECK = "groundedness_check"
    NARRATIVE_GENERATION = "narrative_generation"
    TERRITORY_NAMING = "territory_naming"


class JobStatus(StrEnum):
    """Estado de un `generation_jobs`."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_ATTENTION = "needs_attention"


class JobMode(StrEnum):
    """Modo de ejecución frente al proveedor de IA."""

    SYNC = "sync"
    BATCH = "batch"


class ProvenanceOrigin(StrEnum):
    """Origen del contenido generado: material del usuario o conocimiento del modelo."""

    SOURCE = "source"
    MODEL_KNOWLEDGE = "model_knowledge"


class ProvenanceContentType(StrEnum):
    """Qué elemento generado se está trazando."""

    PATH = "path"
    MODULE = "module"
    TOPIC = "topic"
    LESSON = "lesson"
    LESSON_BLOCK = "lesson_block"
    QUESTION = "question"
    TERRITORY = "territory"
    EXPLANATION = "explanation"


# ---------------------------------------------------------------------------
# Eventos de dominio
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    """Catálogo cerrado de eventos de dominio. El valor es el propio nombre.

    Ver CONTRACT.md §4 para productor, payload y consumidores de cada uno.
    """

    # Identidad y onboarding
    USER_REGISTERED = "USER_REGISTERED"
    USER_LOGGED_IN = "USER_LOGGED_IN"
    USER_DELETED = "USER_DELETED"
    CHARACTER_CREATED = "CHARACTER_CREATED"
    AVATAR_UPDATED = "AVATAR_UPDATED"
    SETTINGS_UPDATED = "SETTINGS_UPDATED"

    # Contenido, ingesta y generación
    KNOWLEDGE_AREA_CREATED = "KNOWLEDGE_AREA_CREATED"
    PATH_CREATED = "PATH_CREATED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    TEXT_PASTED = "TEXT_PASTED"
    DOCUMENT_INGESTED = "DOCUMENT_INGESTED"
    DOCUMENT_FAILED = "DOCUMENT_FAILED"
    PATH_GENERATED = "PATH_GENERATED"
    PATH_CONFIRMED = "PATH_CONFIRMED"
    MODULE_CONTENT_READY = "MODULE_CONTENT_READY"
    GENERATION_FAILED = "GENERATION_FAILED"
    CONTENT_REPORTED = "CONTENT_REPORTED"
    AI_BUDGET_THRESHOLD = "AI_BUDGET_THRESHOLD"

    # Aprendizaje
    TOPIC_STARTED = "TOPIC_STARTED"
    LESSON_STARTED = "LESSON_STARTED"
    LESSON_COMPLETED = "LESSON_COMPLETED"
    QUESTION_ANSWERED = "QUESTION_ANSWERED"
    CHALLENGE_COMPLETED = "CHALLENGE_COMPLETED"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    ASSESSMENT_STARTED = "ASSESSMENT_STARTED"
    ASSESSMENT_COMPLETED = "ASSESSMENT_COMPLETED"
    MODULE_COMPLETED = "MODULE_COMPLETED"
    PATH_COMPLETED = "PATH_COMPLETED"
    STUDY_TIME_TICKED = "STUDY_TIME_TICKED"
    STUDY_SESSION_ENDED = "STUDY_SESSION_ENDED"

    # Dominio
    MASTERY_UPDATED = "MASTERY_UPDATED"
    TOPIC_MASTERED = "TOPIC_MASTERED"
    MODULE_MASTERED = "MODULE_MASTERED"
    AREA_MASTERED = "AREA_MASTERED"
    WEAKNESS_DETECTED = "WEAKNESS_DETECTED"

    # Gamificación
    XP_AWARDED = "XP_AWARDED"
    LEVEL_UP = "LEVEL_UP"
    RANK_UP = "RANK_UP"
    DAILY_GOAL_MET = "DAILY_GOAL_MET"
    STREAK_UPDATED = "STREAK_UPDATED"
    STREAK_MILESTONE_REACHED = "STREAK_MILESTONE_REACHED"
    WEEK_PERFECT = "WEEK_PERFECT"
    MISSION_ASSIGNED = "MISSION_ASSIGNED"
    MISSION_COMPLETED = "MISSION_COMPLETED"
    MISSION_CLAIMED = "MISSION_CLAIMED"
    MISSION_EXPIRED = "MISSION_EXPIRED"
    ACHIEVEMENT_UNLOCKED = "ACHIEVEMENT_UNLOCKED"
    NOTIFICATION_SCHEDULED = "NOTIFICATION_SCHEDULED"

    # Economía, inventario y mundo
    GOLD_AWARDED = "GOLD_AWARDED"
    GOLD_SPENT = "GOLD_SPENT"
    ITEM_ACQUIRED = "ITEM_ACQUIRED"
    ITEM_EQUIPPED = "ITEM_EQUIPPED"
    ITEM_UNEQUIPPED = "ITEM_UNEQUIPPED"
    ITEM_PREVIEWED = "ITEM_PREVIEWED"
    DERIVED_ITEMS_MATERIALIZED = "DERIVED_ITEMS_MATERIALIZED"
    TERRITORY_UNLOCKED = "TERRITORY_UNLOCKED"

    # Analítica de cliente (embudo del MVP)
    REWARD_VIEWED = "REWARD_VIEWED"
    PROFILE_VIEWED = "PROFILE_VIEWED"
    KNOWLEDGE_VIEWED = "KNOWLEDGE_VIEWED"


class EventStatus(StrEnum):
    """Estado de procesamiento de una fila de `domain_events`."""

    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Economía: XP y oro
# ---------------------------------------------------------------------------


class XPSource(StrEnum):
    """Origen de una transacción de XP (dimensión del ledger)."""

    LESSON = "lesson"
    QUESTION = "question"
    CHALLENGE = "challenge"
    ASSESSMENT = "assessment"
    MODULE = "module"
    PATH = "path"
    REVIEW = "review"
    DAILY_MISSION = "daily_mission"
    WEEKLY_MISSION = "weekly_mission"
    SPECIAL_MISSION = "special_mission"
    STREAK_MILESTONE = "streak_milestone"
    ACHIEVEMENT = "achievement"
    FIRST_ACTIVITY_OF_DAY = "first_activity_of_day"
    ADJUSTMENT = "adjustment"


class GoldSource(StrEnum):
    """Fuente de oro (transacción `credit`)."""

    WELCOME = "welcome"
    LESSON = "lesson"
    CHALLENGE = "challenge"
    ASSESSMENT = "assessment"
    MODULE = "module"
    PATH = "path"
    REVIEW = "review"
    DAILY_GOAL = "daily_goal"
    DAILY_MISSION = "daily_mission"
    WEEKLY_MISSION = "weekly_mission"
    SPECIAL_MISSION = "special_mission"
    STREAK_MILESTONE = "streak_milestone"
    ACHIEVEMENT = "achievement"
    LEVEL_UP = "level_up"
    RANK_UP = "rank_up"
    PURCHASE_REVERSAL = "purchase_reversal"
    ADJUSTMENT = "adjustment"


class GoldSink(StrEnum):
    """Sumidero de oro (transacción `debit`)."""

    PURCHASE = "purchase"
    STREAK_PROTECTOR = "streak_protector"  # reservado, fase 2
    ADJUSTMENT = "adjustment"


class LedgerDirection(StrEnum):
    """Sentido de una transacción del ledger de oro."""

    CREDIT = "credit"
    DEBIT = "debit"


class Currency(StrEnum):
    """Monedas del juego. GEMS está reservado y desactivado en el MVP."""

    GOLD = "gold"
    GEMS = "gems"


class LevelScope(StrEnum):
    """Curva de nivel a la que pertenece una fila de `level_definitions`."""

    GLOBAL = "global"
    KNOWLEDGE_AREA = "knowledge_area"


# ---------------------------------------------------------------------------
# Racha, objetivo diario, misiones y logros
# ---------------------------------------------------------------------------


class DayStatus(StrEnum):
    """Estado de una fecha local en el calendario del usuario."""

    INACTIVE = "inactive"
    ACTIVE = "active"
    GRACE = "grace"
    TRAVEL = "travel"


class StreakChange(StrEnum):
    """Motivo del último cambio de la racha."""

    STARTED = "started"
    EXTENDED = "extended"
    GRACE_USED = "grace_used"
    TRAVEL_SKIP = "travel_skip"
    BROKEN = "broken"


class StreakKind(StrEnum):
    """Qué racha se compara en un requisito de desbloqueo."""

    CURRENT = "current"
    BEST = "best"


class GoalType(StrEnum):
    """Tipo de objetivo diario. Valores en español por decisión de producto."""

    MINUTES = "minutos"
    ACTIVITIES = "actividades"
    XP = "xp"


class MissionScope(StrEnum):
    """Horizonte de la misión. Valores en español por decisión de producto.

    SPECIAL cubre las misiones de ruta (se instancian al crear la ruta y no expiran).
    """

    DAILY = "diaria"
    WEEKLY = "semanal"     # desactivada en el MVP por `missions.weekly.enabled`
    SPECIAL = "especial"


class MissionStatus(StrEnum):
    """Ciclo de vida de una misión asignada."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CLAIMED = "claimed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class MissionTier(StrEnum):
    """Dificultad de la instancia de misión diaria."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class MissionMetricType(StrEnum):
    """Tipos de regla compartidos por el evaluador de misiones y de logros."""

    COUNTER = "counter"
    SUM = "sum"
    MAX = "max"
    CONSECUTIVE = "consecutive"
    DISTINCT_COUNT = "distinct_count"
    FLAG = "flag"
    STAT_THRESHOLD = "stat_threshold"


class AchievementCategory(StrEnum):
    """Pestañas de la sala de trofeos."""

    LEARNING = "learning"
    MASTERY = "mastery"
    CONSISTENCY = "consistency"
    COLLECTION = "collection"
    EXPLORATION = "exploration"
    MILESTONE = "milestone"


class AchievementTier(StrEnum):
    """Nivel de un logro. SINGLE para logros de un solo nivel."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    SINGLE = "single"


class AchievementVisibility(StrEnum):
    """Si el logro se muestra con progreso o como silueta con pista."""

    VISIBLE = "visible"
    HIDDEN = "hidden"


# ---------------------------------------------------------------------------
# Inventario, equipamiento y tienda
# ---------------------------------------------------------------------------


class ItemSlot(StrEnum):
    """Ranura del avatar. PET y MOUNT están reservadas (fase 2/3)."""

    HEAD = "head"
    BODY = "body"
    CAPE = "cape"
    GLOVES = "gloves"
    BOOTS = "boots"
    WEAPON = "weapon"
    OFFHAND = "offhand"
    ACCESSORY = "accessory"
    PET = "pet"      # reservado
    MOUNT = "mount"  # reservado


class ItemRarity(StrEnum):
    """Rareza. Afecta solo apariencia, exclusividad, requisitos y precio."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"


class ItemOrigin(StrEnum):
    """Etiqueta de origen del ítem (catálogo) o de la instancia (inventario)."""

    STARTER = "starter"
    SHOP = "shop"
    ACHIEVEMENT = "achievement"
    STREAK = "streak"
    KNOWLEDGE = "knowledge"
    EVENT = "event"
    MISSION = "mission"


class ItemVisibility(StrEnum):
    """Quién ve el ítem aunque esté bloqueado."""

    PUBLIC = "public"
    OWNER = "owner"
    HIDDEN = "hidden"


class RequirementType(StrEnum):
    """Tipos de condición del DSL de desbloqueo (profundidad máxima 2: any de all)."""

    PATH_COMPLETED = "path_completed"
    MASTERY_GTE = "mastery_gte"
    AREAS_MASTERED_GTE = "areas_mastered_gte"
    ASSESSMENT_SCORE_GTE = "assessment_score_gte"
    STREAK_GTE = "streak_gte"
    LEVEL_GTE = "level_gte"
    ACHIEVEMENT_UNLOCKED = "achievement_unlocked"
    LESSONS_COMPLETED_GTE = "lessons_completed_gte"
    WITHIN_WINDOW = "within_window"


class PurchaseStatus(StrEnum):
    """Estado de una orden de compra."""

    COMPLETED = "completed"
    REVERSED = "reversed"


# ---------------------------------------------------------------------------
# Notificaciones
# ---------------------------------------------------------------------------


class NotificationType(StrEnum):
    """Tipos de notificación (push e in-app)."""

    PATH_READY = "path_ready"
    GENERATION_FAILED = "generation_failed"
    STREAK_REMINDER = "streak_reminder"
    STREAK_LAST_CALL = "streak_last_call"
    STREAK_MILESTONE_NEAR = "streak_milestone_near"
    DAILY_MISSION = "daily_mission"
    REVIEW_RECOMMENDED = "review_recommended"
    REACTIVATION = "reactivation"
    ITEM_UNLOCKED = "item_unlocked"
    ACHIEVEMENT_UNLOCKED = "achievement_unlocked"
    SYSTEM = "system"


class NotificationChannel(StrEnum):
    """Canal de entrega."""

    IN_APP = "in_app"
    PUSH = "push"


class NotificationStatus(StrEnum):
    """Estado de entrega/lectura."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"
    DISMISSED = "dismissed"
```

## 2.1 Resumen: 65 enums

| Enum | Nº valores | Usado en |
|---|---|---|
| `UserRole` | 3 | `users.role` |
| `AuthProvider` | 3 | `users.auth_provider` |
| `CharacterArchetype` | 8 (4 MVP) | `characters.archetype` |
| `BodyType` | 3 (1 MVP) | `avatar_configs.body_type` |
| `AddressForm` | 3 | `avatar_configs.address_form` |
| `ThemePreference` | 3 | `user_settings.theme` |
| `ReminderMode` | 3 | `user_settings.reminder_mode` |
| `KnowledgeCategory` | 12 | `knowledge_areas.category` |
| `KnowledgeAreaStatus` | 5 | `user_area_progress.status`, `user_topic_progress.status` |
| `TerritoryStatus` | 3 | respuesta de `/territories` (derivado) |
| `PathOrigin` | 2 | `learning_paths.origin` |
| `PathStatus` | 7 | `learning_paths.status` |
| `PathSourceMode` | 3 | `learning_paths.source_mode` |
| `CoveragePolicy` | 3 | `learning_paths.coverage_policy` |
| `CoverageLevel` | 3 | `topics.coverage` |
| `DeclaredLevel` | 3 | `learning_paths.declared_level` |
| `DifficultyLevel` | 3 | `path_modules.difficulty`, `topics.difficulty`, `questions.difficulty`, `question_attempts.difficulty` |
| `ContentStatus` | 6 | `path_modules`, `topics`, `lessons`, `questions`, `assessments` |
| `ModuleStatus` | 5 | `user_module_progress.status` |
| `ProgressState` | 4 | `user_path_progress.status`, `user_lesson_progress.status` |
| `LessonBlockType` | 6 | `lesson_blocks.block_type` |
| `QuestionType` | 9 (7 MVP) | `questions.question_type` |
| `ActivityContext` | 5 | `question_attempts.context` |
| `EvaluationMethod` | 4 | `question_attempts.evaluation_method` |
| `AttemptResult` | 5 | `question_attempts.result` |
| `AttemptStatus` | 4 | `assessment_attempts.status`, `study_activities.status` |
| `AssessmentOutcome` | 4 | `assessment_attempts.outcome` |
| `StudyActivityType` | 5 | `study_activities.activity_type` |
| `SessionEndReason` | 3 | `learning_sessions.end_reason` |
| `DocumentType` | 7 (5 MVP) | `documents.document_type` |
| `DocumentStatus` | 10 | `documents.status`, `document_versions.status` |
| `ChunkType` | 4 | `document_chunks.chunk_type` |
| `JobType` | 14 | `generation_jobs.job_type`, `prompt_templates.task_type` |
| `JobStatus` | 6 | `generation_jobs.status` |
| `JobMode` | 2 | `generation_jobs.mode` |
| `ProvenanceOrigin` | 2 | `lessons.origin`, `lesson_blocks.origin`, `questions.origin`, `content_provenance.origin` |
| `ProvenanceContentType` | 8 | `content_provenance.content_type` |
| `EventType` | 59 | `domain_events.event_type`, `xp_transactions.event_type`, `reward_rules.event_type` |
| `EventStatus` | 4 | `domain_events.processing_status` |
| `XPSource` | 14 | `xp_transactions.source` |
| `GoldSource` | 17 | `gold_transactions.source` |
| `GoldSink` | 3 | `gold_transactions.sink` |
| `LedgerDirection` | 2 | `gold_transactions.direction` |
| `Currency` | 2 | `wallets.currency`, `gold_transactions.currency`, `shop_listings.currency`, `purchases.currency` |
| `LevelScope` | 2 | `level_definitions.scope` |
| `DayStatus` | 4 | `streak_days.day_status` |
| `StreakChange` | 5 | `streaks.last_change` |
| `StreakKind` | 2 | `item_requirements.streak_kind` |
| `GoalType` | 3 | `daily_goals.goal_type`, `streak_days.goal_type_snapshot` |
| `MissionScope` | 3 | `mission_templates.scope`, `user_missions.scope` |
| `MissionStatus` | 5 | `user_missions.status` |
| `MissionTier` | 3 | `user_missions.tier` |
| `MissionMetricType` | 7 | dentro de `mission_templates.metric` y `achievements.rule` (JSONB) |
| `AchievementCategory` | 6 | `achievements.category` |
| `AchievementTier` | 4 | `user_achievements.highest_tier` |
| `AchievementVisibility` | 2 | `achievements.visibility` |
| `ItemSlot` | 10 (8 MVP) | `items.slot`, `equipped_items.slot` |
| `ItemRarity` | 6 | `items.rarity` |
| `ItemOrigin` | 7 | `items.origin`, `user_items.origin` |
| `ItemVisibility` | 3 | `items.visibility` |
| `RequirementType` | 9 | `item_requirements.requirement_type` |
| `PurchaseStatus` | 2 | `purchases.status` |
| `NotificationType` | 11 | `notifications.notification_type` |
| `NotificationChannel` | 2 | `notifications.channel` |
| `NotificationStatus` | 5 | `notifications.status` |
---

# 3. Catálogo de tablas

**52 tablas** repartidas en 6 archivos de modelos. Reglas de diseño obligatorias que atraviesan todo el catálogo:

1. **Ledgers append-only**: XP y oro se registran en `xp_transactions` y `gold_transactions`; jamás se hace `UPDATE`/`DELETE` sobre ellos. Los saldos cacheados (`characters.xp_total`, `user_area_progress.xp`, `wallets.balance`) se recalculan desde el ledger y se reconcilian de noche (`SUM(amount)` contra el contador).
2. **Idempotencia**: toda tabla que registre un hecho del cliente o una recompensa lleva `idempotency_key` con restricción única (por usuario donde aplique). Un reintento de red nunca duplica XP, oro, ítems ni progreso de misión.
3. **Contenido reutilizable ≠ progreso**: `content.*` describe el contenido generado (una lección se genera una vez y puede ser estudiada por varios usuarios, p. ej. las Rutas del Reino); `progress.*` guarda lo que hizo **cada** usuario. Nunca se mezclan.
4. **Trazabilidad**: `document_chunks` guarda el fragmento con su documento, versión, páginas y offsets; `content_provenance` vincula lección/bloque/pregunta con fragmento, versión de documento, modelo, plantilla de prompt, trabajo y fecha de procesamiento.
5. **Omisión deliberada**: en todas las tablas se omiten de la enumeración de columnas `id` (UUID PK, `default=uuid.uuid4`), `created_at` y `updated_at`, que vienen de los mixins de §1.5. Se indica en cada tabla si es **append-only** (solo `created_at`).
6. **Convenciones de `ondelete`**: datos del usuario → `CASCADE`; referencias a catálogo → `RESTRICT`; referencias opcionales de auditoría → `SET NULL`.

Convenciones de lectura de las tablas de columnas: la columna «Tipo» es el tipo SQLAlchemy literal; `E(X)` abrevia `sa.Enum(X, native_enum=False, length=48, validate_strings=True)`; `UUIDc` abrevia `postgresql.UUID(as_uuid=True)`; «Nulo» indica `nullable`.

---

## 3.1 `app/models/identity.py` — módulo `identity`

### `users`
Cuenta de la persona: credenciales, rol, zona horaria y estado.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `email` | `sa.String(320)` | No | — | Correo normalizado a minúsculas por la aplicación. |
| `password_hash` | `sa.String(255)` | Sí | — | Hash bcrypt; nulo si la cuenta es de proveedor social. |
| `auth_provider` | `E(AuthProvider)` | No | `AuthProvider.EMAIL` | Origen de la credencial. |
| `auth_provider_id` | `sa.String(255)` | Sí | — | Identificador en el proveedor social. |
| `role` | `E(UserRole)` | No | `UserRole.LEARNER` | Rol de la cuenta. |
| `timezone` | `sa.String(64)` | No | `"America/Santiago"` | Zona IANA; base del cálculo de `local_date`. |
| `locale` | `sa.String(10)` | No | `"es-CL"` | Idioma de la interfaz. |
| `is_active` | `sa.Boolean` | No | `sa.true()` | Baja lógica sin borrar. |
| `email_verified_at` | `sa.DateTime(timezone=True)` | Sí | — | Verificación de correo (opcional en MVP). |
| `last_login_at` | `sa.DateTime(timezone=True)` | Sí | — | Último inicio de sesión exitoso. |
| `timezone_changed_at` | `sa.DateTime(timezone=True)` | Sí | — | Control de 1 cambio efectivo cada 24 h. |
| `previous_timezone` | `sa.String(64)` | Sí | — | Zona anterior; habilita el ajuste por viaje. |
| `deleted_at` | `sa.DateTime(timezone=True)` | Sí | — | Borrado lógico a petición del usuario. |

Únicos: `uq_users_email`; `uq_users_auth_provider_auth_provider_id` (`auth_provider`, `auth_provider_id`).
Índices: `ix_users_deleted_at`.
Checks: `ck_users_email_lowercase` → `email = lower(email)`.

### `refresh_tokens`
Tokens de refresco rotatorios con revocación y cadena de reemplazo.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Dueño del token. |
| `token_hash` | `sa.String(64)` | No | — | SHA-256 hex del token; el token en claro nunca se guarda. |
| `issued_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Emisión. |
| `expires_at` | `sa.DateTime(timezone=True)` | No | — | Vencimiento (`JWT_REFRESH_TTL_DAYS`). |
| `revoked_at` | `sa.DateTime(timezone=True)` | Sí | — | Revocación por logout o rotación. |
| `replaced_by_id` | `UUIDc` FK `refresh_tokens.id` SET NULL | Sí | — | Token que lo sustituyó (detección de reuso). |
| `user_agent` | `sa.String(255)` | Sí | — | Dispositivo declarado. |
| `ip_address` | `sa.String(45)` | Sí | — | IPv4/IPv6 del emisor. |

Únicos: `uq_refresh_tokens_token_hash`.
Índices: `ix_refresh_tokens_user_id`, `ix_refresh_tokens_expires_at`.

### `user_settings`
Preferencias de apariencia, notificaciones y contenido. Una fila por usuario.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Dueño. |
| `theme` | `E(ThemePreference)` | No | `SYSTEM` | Tema visual. |
| `reduce_motion` | `sa.Boolean` | No | `sa.false()` | Accesibilidad: animaciones reducidas. |
| `sound_enabled` | `sa.Boolean` | No | `sa.true()` | Sonidos de recompensa. |
| `haptics_enabled` | `sa.Boolean` | No | `sa.true()` | Vibración. |
| `push_enabled` | `sa.Boolean` | No | `sa.false()` | Permiso de push concedido. |
| `push_token` | `sa.String(255)` | Sí | — | Token FCM/APNs del dispositivo. |
| `reminder_mode` | `E(ReminderMode)` | No | `SMART` | Recordatorio inteligente, manual o apagado. |
| `reminder_time_local` | `sa.Time` | Sí | — | Hora fija si `reminder_mode = MANUAL`. |
| `last_call_enabled` | `sa.Boolean` | No | `sa.false()` | Segundo aviso 21:30 (opt-in). |
| `quiet_hours_start` | `sa.Time` | No | `"22:00"` | Inicio de horas de silencio. |
| `quiet_hours_end` | `sa.Time` | No | `"08:00"` | Fin de horas de silencio. |
| `notify_path_ready` | `sa.Boolean` | No | `sa.true()` | Aviso "tu ruta está lista". |
| `notify_streak` | `sa.Boolean` | No | `sa.true()` | Avisos de racha. |
| `notify_missions` | `sa.Boolean` | No | `sa.false()` | Aviso matutino de misiones. |
| `content_language` | `sa.String(10)` | No | `"es"` | Idioma en que se genera el contenido. |
| `last_reminder_sent_on` | `sa.Date` | Sí | — | Antifatiga: un recordatorio por día local. |

Únicos: `uq_user_settings_user_id`.

### `characters`
Personaje del usuario: identidad de juego, nivel y contadores cacheados.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Dueño (1:1). |
| `name` | `sa.String(30)` | No | — | Nombre visible del personaje (3–20 caracteres en la API). |
| `archetype` | `E(CharacterArchetype)` | No | — | Orden elegida; **sin efecto educativo**. |
| `level` | `sa.Integer` | No | `1` | Nivel global cacheado (derivado de `xp_total`). |
| `xp_total` | `sa.BigInteger` | No | `0` | XP acumulado cacheado (= `SUM(xp_transactions.amount)`). |
| `rank_title` | `sa.String(48)` | No | `"Aprendiz"` | Título del rango vigente. |
| `total_study_seconds` | `sa.Integer` | No | `0` | Tiempo de estudio acumulado (cacheado). |
| `onboarded_at` | `sa.DateTime(timezone=True)` | Sí | — | Fin de la creación de personaje. |

Únicos: `uq_characters_user_id`.
Checks: `ck_characters_level_range` → `level >= 1 AND level <= 99`; `ck_characters_xp_total_non_negative` → `xp_total >= 0`.

### `avatar_configs`
Rasgos gratuitos del avatar (no son ítems): piel, rostro, cabello, orejas y trato.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `character_id` | `UUIDc` FK `characters.id` CASCADE | No | — | Personaje (1:1). |
| `body_type` | `E(BodyType)` | No | `NEUTRAL` | Silueta; el MVP solo usa `NEUTRAL`. |
| `skin_tone` | `sa.String(16)` | No | `"skin_03"` | Clave de la paleta (6 tonos). |
| `face_id` | `sa.String(32)` | No | `"face_01"` | Rostro elegido (4 en el MVP). |
| `ear_style` | `sa.String(16)` | No | `"round"` | `round` o `pointed`. |
| `hair_style_id` | `sa.String(32)` | No | `"hair_01"` | Estilo de cabello (8 en el MVP). |
| `hair_color` | `sa.String(16)` | No | `"hair_black"` | Clave de color (10 en el MVP). |
| `address_form` | `E(AddressForm)` | No | `NEUTRAL` | Forma de tratamiento en los textos. |
| `accent_color` | `sa.String(9)` | Sí | — | Color de acento del perfil (`#RRGGBB`). |
| `asset_version` | `sa.Integer` | No | `1` | Versión del manifiesto de assets aplicada. |

Únicos: `uq_avatar_configs_character_id`.

### `equipped_items`
Qué instancia del inventario ocupa cada ranura. La clave única hace imposible equipar dos ítems en el mismo slot.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `character_id` | `UUIDc` FK `characters.id` CASCADE | No | — | Personaje. |
| `slot` | `E(ItemSlot)` | No | — | Ranura ocupada. |
| `user_item_id` | `UUIDc` FK `user_items.id` CASCADE | No | — | Instancia equipada (debe pertenecer al mismo usuario). |
| `equipped_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Momento de equipar. |

Únicos: `uq_equipped_items_character_id_slot`.
Índices: `ix_equipped_items_user_item_id`.

---

## 3.2 `app/models/content.py` — módulo `content`

> Todo lo de este archivo es **contenido reutilizable**: no contiene ninguna columna de progreso, XP ni dominio. Las Rutas del Reino (`learning_paths.user_id IS NULL`) son estudiadas por muchos usuarios sin duplicar contenido.

### `knowledge_areas`
Conocimiento de nivel superior (SQL, BigQuery…). Es la unidad con nivel, XP, dominio y tiempo propios, y se representa como territorio.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `slug` | `sa.String(64)` | No | — | Identificador canónico estable (`sql`, `bigquery`). |
| `name` | `sa.String(80)` | No | — | Nombre visible ("SQL"). |
| `short_name` | `sa.String(18)` | No | — | Nombre corto para plantillas de ítems ("SQL"). |
| `category` | `E(KnowledgeCategory)` | No | `OTHER` | Categoría; tinta los ítems derivados. |
| `description` | `sa.Text` | Sí | — | Descripción breve. |
| `is_canonical` | `sa.Boolean` | No | `sa.false()` | `true` para la taxonomía semilla curada. |
| `created_by_user_id` | `UUIDc` FK `users.id` SET NULL | Sí | — | Usuario que originó el área (si no es canónica). |
| `icon_key` | `sa.String(32)` | Sí | — | Icono/emblema. |
| `accent_color` | `sa.String(9)` | Sí | — | Color de la categoría. |
| `is_active` | `sa.Boolean` | No | `sa.true()` | Retirada sin borrar. |

Únicos: `uq_knowledge_areas_slug`.
Índices: `ix_knowledge_areas_category`, `ix_knowledge_areas_created_by_user_id`.

### `territories`
Representación narrativa del conocimiento en el mapa (1:1 con el conocimiento).

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` CASCADE | No | — | Conocimiento representado. |
| `name` | `sa.String(80)` | No | — | Nombre narrativo ("Castillo de las Consultas"). |
| `icon_hint` | `sa.String(32)` | Sí | — | Pista visual devuelta por la IA (`castle`, `forest`). |
| `concept_keyword` | `sa.String(48)` | Sí | — | Palabra clave que valida la coherencia del nombre. |
| `description` | `sa.Text` | Sí | — | Texto de sabor, generado una vez y cacheado. |
| `generated_by_job_id` | `UUIDc` FK `generation_jobs.id` SET NULL | Sí | — | Trabajo que lo nombró. |

Únicos: `uq_territories_knowledge_area_id`.

### `learning_paths`
Ruta: secuencia ordenada de módulos para un objetivo concreto.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | Sí | — | Dueño. **Nulo = Ruta del Reino** (catálogo semilla compartido). |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` RESTRICT | No | — | Conocimiento principal. |
| `title` | `sa.String(120)` | No | — | Título ("Maestro de SQL"). |
| `goal_text` | `sa.Text` | Sí | — | Objetivo escrito por el usuario. |
| `summary` | `sa.Text` | Sí | — | Resumen generado. |
| `declared_level` | `E(DeclaredLevel)` | No | `BEGINNER` | Nivel declarado al crearla. |
| `source_mode` | `E(PathSourceMode)` | No | `WITH_SOURCE` | `con_fuente` / `sin_fuente` / `mixta`. |
| `origin` | `E(PathOrigin)` | No | `USER` | `seed` o `user`. |
| `status` | `E(PathStatus)` | No | `DRAFT` | Ciclo de vida del contenido. |
| `language` | `sa.String(10)` | No | `"es"` | Idioma del contenido generado. |
| `knowledge_base_id` | `UUIDc` FK `knowledge_bases.id` SET NULL | Sí | — | Corpus asociado. |
| `coverage_policy` | `E(CoveragePolicy)` | No | `MODEL_KNOWLEDGE` | Qué hacer con temas sin respaldo. |
| `coverage_notes` | `JSONB` | No | `'[]'::jsonb` | Avisos de cobertura devueltos por la Fase A. |
| `module_count` | `sa.Integer` | No | `0` | Número de módulos (cacheado). |
| `estimated_minutes` | `sa.Integer` | Sí | — | Duración estimada total. |
| `is_public` | `sa.Boolean` | No | `sa.false()` | Visible para todos (solo rutas semilla). |
| `generated_by_job_id` | `UUIDc` FK `generation_jobs.id` SET NULL | Sí | — | Trabajo de diseño (Fase A). |
| `confirmed_at` | `sa.DateTime(timezone=True)` | Sí | — | Confirmación del esquema por el usuario. |
| `completed_at` | `sa.DateTime(timezone=True)` | Sí | — | Fecha en que se completó (solo rutas de usuario). |
| `archived_at` | `sa.DateTime(timezone=True)` | Sí | — | Archivado por el usuario. |

Índices: `ix_learning_paths_user_id_status`, `ix_learning_paths_knowledge_area_id`, `ix_learning_paths_origin_is_public`.
Checks: `ck_learning_paths_seed_has_no_owner` → `(origin <> 'SEED') OR (user_id IS NULL)` (los enums se guardan por su nombre, §1.4 regla 6).

### `path_modules`
Módulo de una ruta (zona del territorio). Termina en una evaluación.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `learning_path_id` | `UUIDc` FK `learning_paths.id` CASCADE | No | — | Ruta. |
| `position` | `sa.Integer` | No | — | Orden 1..n dentro de la ruta. |
| `title` | `sa.String(120)` | No | — | Título temático ("JOINs"). |
| `flavor_name` | `sa.String(120)` | Sí | — | Nombre narrativo de la zona. |
| `summary` | `sa.Text` | Sí | — | Resumen del módulo. |
| `difficulty` | `E(DifficultyLevel)` | No | `MEDIUM` | Dificultad declarada. |
| `estimated_minutes` | `sa.Integer` | Sí | — | Duración estimada. |
| `content_status` | `E(ContentStatus)` | No | `PENDING` | Estado de generación perezosa. |
| `prerequisite_module_id` | `UUIDc` FK `path_modules.id` SET NULL | Sí | — | Prerrequisito (MVP: lineal; se guarda para fase 3). |
| `topic_count` | `sa.Integer` | No | `0` | Temas (cacheado). |
| `lesson_count` | `sa.Integer` | No | `0` | Lecciones (cacheado). |
| `generated_by_job_id` | `UUIDc` FK `generation_jobs.id` SET NULL | Sí | — | Trabajo que generó su contenido. |

Únicos: `uq_path_modules_learning_path_id_position`.
Índices: `ix_path_modules_learning_path_id`.
Checks: `ck_path_modules_position_positive` → `position >= 1`.

### `topics`
Tema dentro de un módulo. Es la granularidad del dominio fino y del repaso.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `module_id` | `UUIDc` FK `path_modules.id` CASCADE | No | — | Módulo. |
| `position` | `sa.Integer` | No | — | Orden dentro del módulo. |
| `title` | `sa.String(140)` | No | — | Título ("INNER vs LEFT JOIN"). |
| `learning_objectives` | `JSONB` | No | `'[]'::jsonb` | Lista de objetivos de aprendizaje. |
| `coverage` | `E(CoverageLevel)` | No | `FULL` | Cobertura del material para el tema. |
| `difficulty` | `E(DifficultyLevel)` | No | `MEDIUM` | Dificultad declarada. |
| `estimated_minutes` | `sa.Integer` | Sí | — | Duración estimada. |
| `suggested_question_types` | `JSONB` | No | `'[]'::jsonb` | Tipos sugeridos por la Fase A. |
| `source_chunk_ids` | `JSONB` | No | `'[]'::jsonb` | Fragmentos asignados en el diseño (traza fina en `content_provenance`). |
| `lesson_count` | `sa.Integer` | No | `0` | Lecciones (cacheado). |
| `content_status` | `E(ContentStatus)` | No | `PENDING` | Estado de generación. |

Únicos: `uq_topics_module_id_position`.
Índices: `ix_topics_module_id`.

### `lessons`
Lección de 5–15 minutos: unidad mínima que otorga la recompensa "lección completada".

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `topic_id` | `UUIDc` FK `topics.id` CASCADE | No | — | Tema. |
| `position` | `sa.Integer` | No | — | Orden dentro del tema. |
| `title` | `sa.String(140)` | No | — | Título. |
| `summary` | `sa.Text` | Sí | — | Síntesis de cierre. |
| `estimated_seconds` | `sa.Integer` | No | `540` | Duración estimada (9 min); base del tiempo mínimo plausible. |
| `content_status` | `E(ContentStatus)` | No | `PENDING` | Estado de generación. |
| `origin` | `E(ProvenanceOrigin)` | No | `SOURCE` | Respaldada por material o por conocimiento del modelo. |
| `is_low_content` | `sa.Boolean` | No | `sa.false()` | Material insuficiente → paga 50 % de XP y oro (regla A8). |
| `coverage_report` | `JSONB` | No | `'[]'::jsonb` | `[{objective, status}]` por objetivo. |
| `block_count` | `sa.Integer` | No | `0` | Bloques (cacheado). |
| `question_count` | `sa.Integer` | No | `0` | Preguntas asociadas (cacheado). |
| `content_version` | `sa.Integer` | No | `1` | Sube con cada regeneración; el progreso anterior se conserva. |
| `generated_by_job_id` | `UUIDc` FK `generation_jobs.id` SET NULL | Sí | — | Trabajo generador. |

Únicos: `uq_lessons_topic_id_position`.
Índices: `ix_lessons_topic_id`.

### `lesson_blocks`
Bloque ordenado dentro de una lección.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `lesson_id` | `UUIDc` FK `lessons.id` CASCADE | No | — | Lección. |
| `position` | `sa.Integer` | No | — | Orden de presentación. |
| `block_type` | `E(LessonBlockType)` | No | — | Tipo de bloque. |
| `body` | `sa.Text` | Sí | — | Markdown restringido (sin HTML ni URLs). |
| `payload` | `JSONB` | No | `'{}'::jsonb` | Extras: `{language}` en código, `{mermaid}` en diagrama, `{question_id}` en pregunta intercalada. |
| `origin` | `E(ProvenanceOrigin)` | No | `SOURCE` | Respaldo del bloque. |
| `is_flagged` | `sa.Boolean` | No | `sa.false()` | Reportado por el usuario o por el eval automático. |
| `flag_reason` | `sa.String(32)` | Sí | — | `incorrect`, `ambiguous`, `not_in_material`, `poorly_written`, `too_easy`, `too_hard`, `other`. |

Únicos: `uq_lesson_blocks_lesson_id_position`.
Índices: `ix_lesson_blocks_lesson_id`.

### `questions`
Pregunta o ejercicio del pool del tema. Reutilizable en lección, repaso y evaluación.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `topic_id` | `UUIDc` FK `topics.id` CASCADE | No | — | Tema al que está etiquetada (**exactamente uno**). |
| `lesson_id` | `UUIDc` FK `lessons.id` SET NULL | Sí | — | Lección donde aparece intercalada, si aplica. |
| `question_type` | `E(QuestionType)` | No | — | Uno de los 7 tipos del MVP. |
| `difficulty` | `E(DifficultyLevel)` | No | `EASY` | Peso de dominio 1.0 / 1.5 / 2.0. |
| `stem` | `sa.Text` | No | — | Enunciado. |
| `body` | `JSONB` | No | `'{}'::jsonb` | Cuerpo por tipo: opciones, huecos, parejas, rúbrica, `schema_sql`/`seed_data`. |
| `answer_key` | `JSONB` | No | `'{}'::jsonb` | Clave de corrección. **Nunca se serializa al cliente.** |
| `explanation` | `sa.Text` | Sí | — | Explicación que se muestra tras responder. |
| `learning_objective` | `sa.String(240)` | Sí | — | Objetivo que evalúa. |
| `estimated_seconds` | `sa.Integer` | No | `45` | Duración estimada. |
| `origin` | `E(ProvenanceOrigin)` | No | `SOURCE` | Respaldo. |
| `is_remedial` | `sa.Boolean` | No | `sa.false()` | Generada como ejercicio dirigido tras una debilidad. |
| `content_status` | `E(ContentStatus)` | No | `READY` | `FLAGGED` la excluye del pool y de evaluaciones. |
| `is_flagged` | `sa.Boolean` | No | `sa.false()` | Reportada. |
| `flag_reason` | `sa.String(32)` | Sí | — | Igual catálogo que `lesson_blocks.flag_reason`. |
| `flag_count` | `sa.Integer` | No | `0` | Reportes acumulados. |
| `content_version` | `sa.Integer` | No | `1` | Versión del contenido. |
| `generated_by_job_id` | `UUIDc` FK `generation_jobs.id` SET NULL | Sí | — | Trabajo generador. |

Índices: `ix_questions_topic_id_question_type`, `ix_questions_lesson_id`, `ix_questions_content_status`.

### `assessments`
Evaluación de cierre de módulo ("Prueba del Castillo"). Una por módulo.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `module_id` | `UUIDc` FK `path_modules.id` CASCADE | No | — | Módulo evaluado. |
| `title` | `sa.String(140)` | No | `"Prueba del módulo"` | Nombre narrativo (**no** usar la palabra "Desafío"). |
| `question_count` | `sa.Integer` | No | `10` | Preguntas que se muestran por intento. |
| `pass_score` | `sa.Numeric(5, 2)` | No | `70.00` | Umbral de aprobación en porcentaje. |
| `bank_size` | `sa.Integer` | No | `25` | Tamaño objetivo del banco (2,5×). |
| `max_attempts_per_day` | `sa.Integer` | No | `2` | Tope diario de intentos. |
| `content_status` | `E(ContentStatus)` | No | `PENDING` | Estado del banco. |

Únicos: `uq_assessments_module_id`.

### `assessment_questions`
Banco de preguntas de una evaluación (relación N:M con `questions`).

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `assessment_id` | `UUIDc` FK `assessments.id` CASCADE | No | — | Evaluación. |
| `question_id` | `UUIDc` FK `questions.id` CASCADE | No | — | Pregunta del banco. |
| `position` | `sa.Integer` | Sí | — | Orden sugerido en el banco. |
| `is_active` | `sa.Boolean` | No | `sa.true()` | `false` si la pregunta fue reportada. |

Únicos: `uq_assessment_questions_assessment_id_question_id`.
Índices: `ix_assessment_questions_assessment_id`.
---

## 3.3 `app/models/ingestion.py` — módulos `ingestion` y `ai`

### `knowledge_bases`
Corpus de material de un usuario; una ruta apunta a una biblioteca.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Dueño del material. |
| `name` | `sa.String(120)` | No | — | Nombre visible ("Material de SQL"). |
| `description` | `sa.Text` | Sí | — | Descripción. |
| `document_count` | `sa.Integer` | No | `0` | Documentos activos (cacheado). |
| `total_tokens` | `sa.Integer` | No | `0` | Tokens del corpus; tope 150 000 por ruta. |
| `is_default` | `sa.Boolean` | No | `sa.false()` | Biblioteca por defecto del usuario. |

Índices: `ix_knowledge_bases_user_id`.

### `documents`
Identidad lógica de un material ("Manual SQL.pdf"), independiente de sus versiones.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `knowledge_base_id` | `UUIDc` FK `knowledge_bases.id` CASCADE | No | — | Biblioteca. |
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Dueño (desnormalizado: **toda** consulta filtra por él). |
| `title` | `sa.String(255)` | No | — | Título visible. |
| `document_type` | `E(DocumentType)` | No | — | Formato de origen. |
| `original_filename` | `sa.String(255)` | Sí | — | Nombre del archivo subido. |
| `status` | `E(DocumentStatus)` | No | `UPLOADED` | Estado agregado del documento. |
| `version_count` | `sa.Integer` | No | `0` | Versiones (cacheado). |
| `deleted_at` | `sa.DateTime(timezone=True)` | Sí | — | Borrado lógico inmediato. |
| `purge_after` | `sa.DateTime(timezone=True)` | Sí | — | Purga física diferida (30 días). |

Índices: `ix_documents_user_id_status`, `ix_documents_knowledge_base_id`.

### `document_versions`
Versión inmutable de un documento (hash, binario, estadísticas de procesamiento).

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `document_id` | `UUIDc` FK `documents.id` CASCADE | No | — | Documento. |
| `version_number` | `sa.Integer` | No | `1` | Número incremental. |
| `content_hash` | `sa.String(64)` | No | — | SHA-256 del binario; deduplica subidas idénticas. |
| `storage_key` | `sa.String(512)` | No | — | Clave en el bucket / ruta local. |
| `byte_size` | `sa.Integer` | No | `0` | Tamaño (máx. 25 MB). |
| `page_count` | `sa.Integer` | Sí | — | Páginas (máx. 300). |
| `word_count` | `sa.Integer` | Sí | — | Palabras (mín. 300 para generar ruta). |
| `token_count` | `sa.Integer` | Sí | — | Tokens estimados. |
| `chunk_count` | `sa.Integer` | No | `0` | Fragmentos generados. |
| `language` | `sa.String(10)` | Sí | — | Idioma detectado. |
| `status` | `E(DocumentStatus)` | No | `UPLOADED` | Estado del procesamiento. |
| `is_current` | `sa.Boolean` | No | `sa.true()` | Versión vigente (una por documento). |
| `error_message` | `sa.Text` | Sí | — | Motivo de rechazo o fallo. |
| `processed_at` | `sa.DateTime(timezone=True)` | Sí | — | Fin de la ingesta. |

Únicos: `uq_document_versions_document_id_version_number`; `uq_document_versions_document_id_content_hash`.
Índices: `ix_document_versions_document_id`; índice parcial creado en la migración: `CREATE UNIQUE INDEX uq_document_versions_current ON document_versions (document_id) WHERE is_current`.

### `document_chunks`
Fragmento indexado: texto, metadatos de trazabilidad, embedding y vector de búsqueda léxica.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `document_version_id` | `UUIDc` FK `document_versions.id` CASCADE | No | — | Versión de origen. |
| `document_id` | `UUIDc` FK `documents.id` CASCADE | No | — | Documento (desnormalizado). |
| `knowledge_base_id` | `UUIDc` FK `knowledge_bases.id` CASCADE | No | — | Biblioteca (filtro de recuperación). |
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Dueño (aislamiento obligatorio). |
| `chunk_index` | `sa.Integer` | No | — | Orden dentro de la versión. |
| `chunk_type` | `E(ChunkType)` | No | `PROSE` | Prosa, código, tabla o lista. |
| `heading_path` | `JSONB` | No | `'[]'::jsonb` | `["Capítulo 5. JOINs", "LEFT JOIN"]`; se antepone al texto al embeber. |
| `text` | `sa.Text` | No | — | Texto normalizado del fragmento. |
| `token_count` | `sa.Integer` | No | `0` | Objetivo 450, máx. 800, mín. 80. |
| `page_start` | `sa.Integer` | Sí | — | Página inicial (trazabilidad). |
| `page_end` | `sa.Integer` | Sí | — | Página final. |
| `char_start` | `sa.Integer` | Sí | — | Offset inicial en el texto extraído. |
| `char_end` | `sa.Integer` | Sí | — | Offset final. |
| `language` | `sa.String(10)` | Sí | — | Idioma del fragmento. |
| `content_hash` | `sa.String(64)` | No | — | SHA-256 del texto normalizado (deduplicación). |
| `embedding` | `Vector(512)` | Sí | — | `voyage-3-lite`, 512 dimensiones, distancia coseno. |
| `embedding_model` | `sa.String(64)` | Sí | — | Modelo usado; permite reindexar. |
| `embedding_dim` | `sa.Integer` | Sí | — | Dimensión efectiva (512). |
| `search_vector` | `TSVECTOR` `Computed` | Sí | generada | `to_tsvector('spanish', coalesce(text, ''))`, `persisted=True`. |

Append-only (solo `created_at`).
Únicos: `uq_document_chunks_document_version_id_chunk_index`.
Índices declarados: `ix_document_chunks_knowledge_base_id`, `ix_document_chunks_user_id`, `ix_document_chunks_document_id`.
Índices creados con `op.execute` en la migración:

```sql
CREATE INDEX ix_document_chunks_embedding_hnsw
  ON document_chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 128);
CREATE INDEX ix_document_chunks_search_vector
  ON document_chunks USING gin (search_vector);
```

### `generation_jobs`
Todo trabajo de IA o de ingesta, con su coste y su trazabilidad. Es también la cola: el worker toma filas `PENDING`.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | Sí | — | Usuario que lo originó (nulo en trabajos de sistema). |
| `job_type` | `E(JobType)` | No | — | Tipo de trabajo. |
| `status` | `E(JobStatus)` | No | `PENDING` | Estado. |
| `mode` | `E(JobMode)` | No | `SYNC` | `sync` o `batch` (−50 % de costo). |
| `queue` | `sa.String(24)` | No | `"generate"` | `ingest`, `generate`, `housekeeping`. |
| `priority` | `sa.Integer` | No | `100` | Menor = antes. |
| `target_type` | `sa.String(32)` | Sí | — | `path`, `module`, `topic`, `lesson`, `question`, `assessment`, `document`, `answer`. |
| `target_id` | `UUIDc` | Sí | — | Id del objetivo. |
| `learning_path_id` | `UUIDc` FK `learning_paths.id` SET NULL | Sí | — | Ruta afectada (progreso visible en la app). |
| `document_version_id` | `UUIDc` FK `document_versions.id` SET NULL | Sí | — | Versión procesada. |
| `prompt_template_id` | `UUIDc` FK `prompt_templates.id` SET NULL | Sí | — | Plantilla usada. |
| `provider` | `sa.String(32)` | No | `"anthropic"` | Proveedor. |
| `model_id` | `sa.String(64)` | Sí | — | Modelo exacto devuelto por la API. |
| `input_tokens` | `sa.Integer` | No | `0` | Tokens de entrada. |
| `cached_input_tokens` | `sa.Integer` | No | `0` | Lecturas de caché de prompt. |
| `output_tokens` | `sa.Integer` | No | `0` | Tokens de salida. |
| `cost_usd` | `sa.Numeric(10, 6)` | No | `0` | Costo calculado. |
| `attempt_count` | `sa.Integer` | No | `0` | Reintentos consumidos. |
| `max_attempts` | `sa.Integer` | No | `3` | Tope de reintentos. |
| `steps` | `JSONB` | No | `'[]'::jsonb` | Pasos persistidos: reanudable e idempotente. |
| `progress_pct` | `sa.Numeric(5, 2)` | No | `0` | Progreso para la pantalla de generación. |
| `progress_label` | `sa.String(120)` | Sí | — | Etapa visible ("Diseñando módulos"). |
| `payload` | `JSONB` | No | `'{}'::jsonb` | Entrada del trabajo. |
| `result` | `JSONB` | No | `'{}'::jsonb` | Salida resumida. |
| `error_message` | `sa.Text` | Sí | — | Último error. |
| `idempotency_key` | `sa.String(120)` | Sí | — | Evita encolar dos veces lo mismo. |
| `queued_at` | `sa.DateTime(timezone=True)` | Sí | — | Encolado. |
| `started_at` | `sa.DateTime(timezone=True)` | Sí | — | Inicio. |
| `finished_at` | `sa.DateTime(timezone=True)` | Sí | — | Fin. |

Únicos: `uq_generation_jobs_idempotency_key`.
Índices: `ix_generation_jobs_status_queue_priority`, `ix_generation_jobs_user_id_created_at`, `ix_generation_jobs_learning_path_id`.

### `prompt_templates`
Versión de prompt registrada en el despliegue; toda generación referencia una.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `task_type` | `E(JobType)` | No | — | Tarea que cubre. |
| `version` | `sa.String(20)` | No | — | Versión semántica del prompt (`v3`, `2026-09-10.1`). |
| `content_hash` | `sa.String(64)` | No | — | SHA-256 del cuerpo. |
| `body` | `sa.Text` | No | — | Texto del prompt (system + instrucciones). |
| `default_model` | `sa.String(64)` | No | — | Modelo por defecto. |
| `effort` | `sa.String(16)` | Sí | — | `low`, `medium`, `high`. |
| `max_tokens` | `sa.Integer` | Sí | — | Tope de salida. |
| `output_schema` | `JSONB` | No | `'{}'::jsonb` | Esquema de `output_config.format`. |
| `notes` | `sa.Text` | Sí | — | Notas de cambio. |
| `is_active` | `sa.Boolean` | No | `sa.true()` | Solo una activa por `task_type`. |

Únicos: `uq_prompt_templates_task_type_version`.

### `content_provenance`
Trazabilidad fina: qué fragmento, versión de documento, modelo y prompt produjeron cada pieza generada.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `content_type` | `E(ProvenanceContentType)` | No | — | Qué se traza. |
| `content_id` | `UUIDc` | No | — | Id del elemento generado. |
| `block_key` | `sa.String(64)` | Sí | — | Sub-elemento (posición de bloque, id de pregunta). |
| `chunk_id` | `UUIDc` FK `document_chunks.id` SET NULL | Sí | — | Fragmento que respalda. |
| `document_version_id` | `UUIDc` FK `document_versions.id` SET NULL | Sí | — | Versión de documento. |
| `document_id` | `UUIDc` FK `documents.id` SET NULL | Sí | — | Documento (para mostrar "generado a partir de"). |
| `retrieval_rank` | `sa.Integer` | Sí | — | Posición en la recuperación híbrida. |
| `origin` | `E(ProvenanceOrigin)` | No | `SOURCE` | `source` o `model_knowledge`. |
| `generation_job_id` | `UUIDc` FK `generation_jobs.id` SET NULL | Sí | — | Trabajo generador. |
| `prompt_template_id` | `UUIDc` FK `prompt_templates.id` SET NULL | Sí | — | Plantilla usada. |
| `model_id` | `sa.String(64)` | Sí | — | Modelo exacto. |
| `processed_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Fecha de procesamiento mostrada al usuario. |

Append-only (solo `created_at`).
Índices: `ix_content_provenance_content_type_content_id`, `ix_content_provenance_chunk_id`, `ix_content_provenance_document_id`.

---

## 3.4 `app/models/progress.py` — módulo `progress`

### `learning_sessions`
Ventana de actividad del usuario; agrupa actividades y acumula tiempo efectivo.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `started_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Primera interacción educativa. |
| `last_heartbeat_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Último latido aceptado. |
| `ended_at` | `sa.DateTime(timezone=True)` | Sí | — | Cierre (10 min de inactividad). |
| `active_seconds` | `sa.Integer` | No | `0` | Suma de latidos válidos (≤ 60 s por latido). |
| `local_date` | `sa.Date` | No | — | Fecha local del inicio. |
| `device` | `sa.String(32)` | Sí | — | `android`, `ios`, `web`. |
| `end_reason` | `E(SessionEndReason)` | Sí | — | Motivo del cierre. |

Índices: `ix_learning_sessions_user_id_started_at`, `ix_learning_sessions_user_id_local_date`.

### `study_activities`
**Intento de actividad**: la lección, repaso, desafío o evaluación que el usuario abrió. Es la unidad que se completa, la que valida el tiempo mínimo plausible y la que dispara las recompensas.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `session_id` | `UUIDc` FK `learning_sessions.id` SET NULL | Sí | — | Sesión que la contiene. |
| `activity_type` | `E(StudyActivityType)` | No | — | Lección, práctica, repaso, desafío o evaluación. |
| `status` | `E(AttemptStatus)` | No | `IN_PROGRESS` | Expira a las 2 h (`xp.attempt_ttl_hours`). |
| `lesson_id` | `UUIDc` FK `lessons.id` SET NULL | Sí | — | Lección, si aplica. |
| `assessment_id` | `UUIDc` FK `assessments.id` SET NULL | Sí | — | Evaluación, si aplica. |
| `topic_id` | `UUIDc` FK `topics.id` SET NULL | Sí | — | Tema. |
| `module_id` | `UUIDc` FK `path_modules.id` SET NULL | Sí | — | Módulo. |
| `learning_path_id` | `UUIDc` FK `learning_paths.id` SET NULL | Sí | — | Ruta. |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` SET NULL | Sí | — | Conocimiento (dimensión de XP y dominio). |
| `started_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Reloj **del servidor**. |
| `completed_at` | `sa.DateTime(timezone=True)` | Sí | — | Cierre válido. |
| `elapsed_seconds` | `sa.Integer` | No | `0` | `completed_at − started_at` del servidor. |
| `active_seconds` | `sa.Integer` | No | `0` | Tiempo efectivo con tope de 3× la duración estimada. |
| `reported_seconds` | `sa.Integer` | No | `0` | Tiempo bruto reportado por latidos (auditoría). |
| `questions_total` | `sa.Integer` | No | `0` | Preguntas presentadas. |
| `questions_correct` | `sa.Integer` | No | `0` | Aciertos. |
| `accuracy_pct` | `sa.Numeric(5, 2)` | Sí | — | Precisión de la actividad. |
| `completion_index` | `sa.Integer` | No | `1` | Nº de finalización de esa actividad (regla A1: 1 → 100 %, 2 → 20 %, 3+ → 0). |
| `counts_for_progress` | `sa.Boolean` | No | `sa.true()` | `false` si es repetición trivial o duró menos del mínimo plausible. |
| `xp_awarded` | `sa.Integer` | No | `0` | XP total otorgado (auditoría rápida). |
| `gold_awarded` | `sa.Integer` | No | `0` | Oro total otorgado. |
| `local_date` | `sa.Date` | No | — | Fecha local del usuario (día activo, topes diarios). |
| `idempotency_key` | `sa.String(120)` | No | — | Clave del cliente al abrir la actividad. |

Únicos: `uq_study_activities_user_id_idempotency_key`.
Índices: `ix_study_activities_user_id_local_date`, `ix_study_activities_user_id_status`, `ix_study_activities_lesson_id`.

### `question_attempts`
**Evidencia de dominio**: una fila por respuesta. Append-only.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `question_id` | `UUIDc` FK `questions.id` CASCADE | No | — | Pregunta. |
| `topic_id` | `UUIDc` FK `topics.id` CASCADE | No | — | Tema (agregación de dominio). |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` SET NULL | Sí | — | Conocimiento. |
| `study_activity_id` | `UUIDc` FK `study_activities.id` SET NULL | Sí | — | Actividad en curso que la contiene. |
| `assessment_attempt_id` | `UUIDc` FK `assessment_attempts.id` SET NULL | Sí | — | Intento de evaluación, si aplica. |
| `context` | `E(ActivityContext)` | No | — | Peso de contexto: lección 1.0, repaso 1.0, desafío 1.5, evaluación 2.0. |
| `attempt_no` | `sa.Integer` | No | `1` | Nº de intento sobre la misma pregunta dentro de la actividad. |
| `response` | `JSONB` | No | `'{}'::jsonb` | Respuesta enviada por el usuario. |
| `result` | `E(AttemptResult)` | No | — | Resultado normalizado. |
| `is_correct` | `sa.Boolean` | No | — | Atajo booleano para misiones y logros. |
| `partial_score` | `sa.Numeric(5, 2)` | No | `0` | Crédito parcial 0–100 (relacionar/ordenar/abierta). |
| `correctness_weight` | `sa.Numeric(3, 2)` | No | `0` | `c` de la fórmula: 1.00 / 0.50 / 0.00. |
| `difficulty` | `E(DifficultyLevel)` | No | — | Copiada de la pregunta al momento de responder. |
| `evaluation_method` | `E(EvaluationMethod)` | No | — | Determinista, sandbox, juez LLM o pendiente. |
| `judge_confidence` | `sa.Numeric(3, 2)` | Sí | — | Confianza del juez (escala a Sonnet si < 0.60). |
| `judge_payload` | `JSONB` | No | `'{}'::jsonb` | Rúbrica evaluada, `verdict`, `flags`, retroalimentación. |
| `response_ms` | `sa.Integer` | No | `0` | Tiempo de respuesta (regla A4: < 2 000 ms no paga XP). |
| `hint_used` | `sa.Boolean` | No | `sa.false()` | Reservado para el multiplicador "sin ayuda". |
| `is_retry_of_failed` | `sa.Boolean` | No | `sa.false()` | Revancha sobre una pregunta fallada (misión D12, logro Revancha). |
| `counts_for_progress` | `sa.Boolean` | No | `sa.true()` | Alimenta objetivo diario, misiones y logros. |
| `counts_for_mastery` | `sa.Boolean` | No | `sa.true()` | `false` si está `NEEDS_REVIEW`. |
| `xp_awarded` | `sa.Integer` | No | `0` | XP pagado por esta respuesta. |
| `answered_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Marca del servidor. |
| `local_date` | `sa.Date` | No | — | Fecha local. |
| `idempotency_key` | `sa.String(120)` | No | — | Clave del cliente. |

Append-only (solo `created_at`).
Únicos: `uq_question_attempts_user_id_idempotency_key`.
Índices: `ix_question_attempts_user_id_topic_id_answered_at`, `ix_question_attempts_question_id`, `ix_question_attempts_user_id_local_date`.

### `assessment_attempts`
Intento de evaluación de módulo, con banco muestreado, puntaje y enfriamiento.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `assessment_id` | `UUIDc` FK `assessments.id` CASCADE | No | — | Evaluación. |
| `module_id` | `UUIDc` FK `path_modules.id` CASCADE | No | — | Módulo (desnormalizado). |
| `learning_path_id` | `UUIDc` FK `learning_paths.id` SET NULL | Sí | — | Ruta. |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` SET NULL | Sí | — | Conocimiento. |
| `attempt_no` | `sa.Integer` | No | `1` | Nº de intento (penaliza `E_mod` en 0.05 por intento previo). |
| `status` | `E(AttemptStatus)` | No | `IN_PROGRESS` | Estado del intento. |
| `question_ids` | `JSONB` | No | `'[]'::jsonb` | Preguntas muestreadas (solapamiento ≤ 30 % con el intento previo). |
| `question_count` | `sa.Integer` | No | `10` | Preguntas presentadas. |
| `correct_count` | `sa.Integer` | No | `0` | Aciertos. |
| `score` | `sa.Numeric(5, 2)` | Sí | — | Puntaje 0–100. |
| `effective_score` | `sa.Numeric(5, 2)` | Sí | — | Puntaje con penalización por reintento. |
| `outcome` | `E(AssessmentOutcome)` | Sí | — | Resultado final. |
| `per_topic_scores` | `JSONB` | No | `'[]'::jsonb` | `[{topic_id, correct, total, pct}]` para el desglose. |
| `weak_topic_ids` | `JSONB` | No | `'[]'::jsonb` | Temas por debajo del 60 % en este intento. |
| `started_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Inicio. |
| `submitted_at` | `sa.DateTime(timezone=True)` | Sí | — | Envío. |
| `cooldown_until` | `sa.DateTime(timezone=True)` | Sí | — | Enfriamiento tras reprobar (4 h / 24 h / 48 h). |
| `cooldown_waived_at` | `sa.DateTime(timezone=True)` | Sí | — | Anulado por completar el repaso recomendado. |
| `xp_awarded` | `sa.Integer` | No | `0` | XP otorgado. |
| `gold_awarded` | `sa.Integer` | No | `0` | Oro otorgado. |
| `local_date` | `sa.Date` | No | — | Fecha local. |
| `idempotency_key` | `sa.String(120)` | No | — | Clave del cliente. |

Únicos: `uq_assessment_attempts_user_id_assessment_id_attempt_no`; `uq_assessment_attempts_user_id_idempotency_key`.
Índices: `ix_assessment_attempts_user_id_assessment_id`.

### `user_path_progress`
Avance del usuario en una ruta.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `learning_path_id` | `UUIDc` FK `learning_paths.id` CASCADE | No | — | Ruta. |
| `status` | `E(ProgressState)` | No | `NOT_STARTED` | Estado del avance. |
| `modules_total` | `sa.Integer` | No | `0` | Módulos de la ruta. |
| `modules_completed` | `sa.Integer` | No | `0` | Módulos completados. |
| `lessons_total` | `sa.Integer` | No | `0` | Lecciones de la ruta. |
| `lessons_completed` | `sa.Integer` | No | `0` | Lecciones completadas. |
| `completion_pct` | `sa.Numeric(5, 2)` | No | `0` | Porcentaje de avance. |
| `current_module_id` | `UUIDc` FK `path_modules.id` SET NULL | Sí | — | Dónde está el usuario ("Continuar"). |
| `current_lesson_id` | `UUIDc` FK `lessons.id` SET NULL | Sí | — | Siguiente lección recomendada. |
| `started_at` | `sa.DateTime(timezone=True)` | Sí | — | Primera actividad. |
| `completed_at` | `sa.DateTime(timezone=True)` | Sí | — | Ruta completada. |
| `last_activity_at` | `sa.DateTime(timezone=True)` | Sí | — | Última actividad. |

Únicos: `uq_user_path_progress_user_id_learning_path_id`.
Índices: `ix_user_path_progress_user_id_last_activity_at`.

### `user_module_progress`
Avance y dominio del usuario en un módulo (`M_mod`).

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `module_id` | `UUIDc` FK `path_modules.id` CASCADE | No | — | Módulo. |
| `learning_path_id` | `UUIDc` FK `learning_paths.id` CASCADE | No | — | Ruta (desnormalizado). |
| `status` | `E(ModuleStatus)` | No | `LOCKED` | Bloqueo progresivo. |
| `lessons_total` | `sa.Integer` | No | `0` | Lecciones del módulo. |
| `lessons_completed` | `sa.Integer` | No | `0` | Completadas. |
| `mean_topic_mastery` | `sa.Numeric(5, 2)` | No | `0` | Promedio ponderado de `M_t`. |
| `assessment_best_score` | `sa.Numeric(5, 2)` | Sí | — | Mejor puntaje bruto. |
| `assessment_best_effective` | `sa.Numeric(5, 2)` | Sí | — | `E_mod` (mejor puntaje con penalización). |
| `assessment_attempts` | `sa.Integer` | No | `0` | Intentos realizados. |
| `assessment_passed_at` | `sa.DateTime(timezone=True)` | Sí | — | Primera aprobación. |
| `mastery` | `sa.Numeric(5, 2)` | No | `0` | `M_mod` = 0.70 × temas + 0.30 × `E_mod`. |
| `unlocked_at` | `sa.DateTime(timezone=True)` | Sí | — | Desbloqueo. |
| `started_at` | `sa.DateTime(timezone=True)` | Sí | — | Inicio. |
| `completed_at` | `sa.DateTime(timezone=True)` | Sí | — | Todas las lecciones + evaluación aprobada. |
| `mastered_at` | `sa.DateTime(timezone=True)` | Sí | — | `M_mod ≥ 80` y evaluación aprobada. |

Únicos: `uq_user_module_progress_user_id_module_id`.
Índices: `ix_user_module_progress_user_id_learning_path_id`.

### `user_lesson_progress`
Avance del usuario en una lección; sostiene la regla anti-repetición A1.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `lesson_id` | `UUIDc` FK `lessons.id` CASCADE | No | — | Lección. |
| `topic_id` | `UUIDc` FK `topics.id` CASCADE | No | — | Tema (desnormalizado). |
| `module_id` | `UUIDc` FK `path_modules.id` CASCADE | No | — | Módulo (desnormalizado). |
| `status` | `E(ProgressState)` | No | `NOT_STARTED` | Estado. |
| `completion_count` | `sa.Integer` | No | `0` | Nº de finalizaciones (multiplicadores 1.0 / 0.2 / 0.0). |
| `last_block_position` | `sa.Integer` | No | `0` | Paso donde quedó (reanudar). |
| `questions_total` | `sa.Integer` | No | `0` | Preguntas de la última pasada. |
| `questions_correct` | `sa.Integer` | No | `0` | Aciertos. |
| `accuracy_pct` | `sa.Numeric(5, 2)` | Sí | — | Precisión de la última pasada. |
| `active_seconds` | `sa.Integer` | No | `0` | Tiempo acumulado. |
| `first_completed_at` | `sa.DateTime(timezone=True)` | Sí | — | Primera finalización (la que paga completo). |
| `last_completed_at` | `sa.DateTime(timezone=True)` | Sí | — | Última finalización. |
| `last_reviewed_on` | `sa.Date` | Sí | — | Repaso contabilizado una vez por día y lección. |

Únicos: `uq_user_lesson_progress_user_id_lesson_id`.
Índices: `ix_user_lesson_progress_user_id_module_id`.

### `user_topic_progress`
Dominio fino por tema (`P_t`, `C_t`, `M_t`) y detección de debilidad.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `topic_id` | `UUIDc` FK `topics.id` CASCADE | No | — | Tema. |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` CASCADE | No | — | Conocimiento (desnormalizado). |
| `module_id` | `UUIDc` FK `path_modules.id` CASCADE | No | — | Módulo (desnormalizado). |
| `practice_score` | `sa.Numeric(5, 2)` | No | `50.00` | `P_t × 100` (prior `m=3`, `p0=0.5`). |
| `coverage` | `sa.Numeric(5, 2)` | No | `0` | `C_t × 100` = lecciones completadas / lecciones del tema. |
| `mastery_raw` | `sa.Numeric(5, 2)` | No | `0` | `P_t × g(C_t) × 100`, sin decaimiento. |
| `mastery` | `sa.Numeric(5, 2)` | No | `0` | Con decaimiento aplicado (materializado por el job diario). |
| `evidence_count` | `sa.Integer` | No | `0` | Evidencias consideradas. |
| `stability_s` | `sa.Integer` | No | `0` | Repasos exitosos posteriores al primer dominio. |
| `last_evidence_at` | `sa.DateTime(timezone=True)` | Sí | — | Base del decaimiento. |
| `ever_mastered_at` | `sa.DateTime(timezone=True)` | Sí | — | Primera vez que superó el 80 %. |
| `status` | `E(KnowledgeAreaStatus)` | No | `NO_EVIDENCE` | Estado de dominio del tema. |
| `is_weak` | `sa.Boolean` | No | `sa.false()` | `P_t < 50` con ≥ 5 evidencias. |
| `weak_detected_at` | `sa.DateTime(timezone=True)` | Sí | — | Última detección de debilidad (idempotencia 24 h). |
| `weak_rule` | `sa.String(8)` | Sí | — | Regla que la detectó (`R1`…`R5`). |

Únicos: `uq_user_topic_progress_user_id_topic_id`.
Índices: `ix_user_topic_progress_user_id_knowledge_area_id`, `ix_user_topic_progress_user_id_is_weak`.

### `user_area_progress`
Perfil de conocimiento: nivel, XP, dominio y tiempo por conocimiento.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` CASCADE | No | — | Conocimiento. |
| `xp` | `sa.BigInteger` | No | `0` | XP del conocimiento (suma del ledger filtrada). |
| `level` | `sa.Integer` | No | `1` | Nivel por conocimiento (curva base 50). |
| `rank_title` | `sa.String(48)` | No | `"Novato/a en"` | Prefijo de título ("Competente en"). |
| `mastery` | `sa.Numeric(5, 2)` | No | `0` | `M_area × 100`. |
| `study_seconds` | `sa.Integer` | No | `0` | Tiempo dedicado al conocimiento. |
| `modules_total` | `sa.Integer` | No | `0` | Módulos de todas las rutas activas del área. |
| `modules_mastered` | `sa.Integer` | No | `0` | Módulos dominados. |
| `topics_mastered` | `sa.Integer` | No | `0` | Temas dominados. |
| `paths_completed` | `sa.Integer` | No | `0` | Rutas completas del área. |
| `status` | `E(KnowledgeAreaStatus)` | No | `NO_EVIDENCE` | Estado del conocimiento. |
| `mastered_at` | `sa.DateTime(timezone=True)` | Sí | — | Cuándo se declaró dominado (≥ 80 % + ruta completa). |
| `last_activity_at` | `sa.DateTime(timezone=True)` | Sí | — | Última actividad del área. |

Únicos: `uq_user_area_progress_user_id_knowledge_area_id`.
Índices: `ix_user_area_progress_user_id_status`.
---

## 3.5 `app/models/gamification.py` — módulo `gamification`

### `domain_events`
Bitácora única de eventos de dominio. Es el bus del MVP: los productores insertan, el motor de gamificación consume en la misma transacción (mecánicas rápidas) o en el worker (logros y desbloqueos).

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `event_type` | `E(EventType)` | No | — | Nombre canónico del evento (§4). |
| `user_id` | `UUIDc` FK `users.id` CASCADE | Sí | — | Sujeto del evento (nulo en eventos de sistema). |
| `occurred_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Momento del hecho (marca del cliente si difiere ≤ 10 min del servidor). |
| `received_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Recepción en el servidor. |
| `local_date` | `sa.Date` | Sí | — | Fecha local del usuario, calculada al ingerir. Viaja con el evento. |
| `timezone` | `sa.String(64)` | Sí | — | Zona usada para calcular `local_date`. |
| `version` | `sa.Integer` | No | `1` | Versión del contrato del payload. |
| `source_module` | `sa.String(24)` | No | — | `identity`, `content`, `ingestion`, `ai`, `progress`, `gamification`, `economy`, `client`. |
| `payload` | `JSONB` | No | `'{}'::jsonb` | Payload documentado en §4. |
| `correlation_id` | `UUIDc` | Sí | — | Agrupa la cascada de eventos de una misma acción del usuario. |
| `causation_id` | `UUIDc` FK `domain_events.id` SET NULL | Sí | — | Evento que lo provocó. |
| `processing_status` | `E(EventStatus)` | No | `PENDING` | Estado del consumo. |
| `processed_at` | `sa.DateTime(timezone=True)` | Sí | — | Fin del procesamiento. |
| `error_message` | `sa.Text` | Sí | — | Último error del consumidor. |
| `idempotency_key` | `sa.String(120)` | No | — | **Única global.** Reprocesar no duplica efectos. |

Append-only en su contenido de negocio (`processing_status`/`processed_at` son los únicos campos mutables; no lleva `updated_at`).
Únicos: `uq_domain_events_idempotency_key`.
Índices: `ix_domain_events_user_id_occurred_at`, `ix_domain_events_event_type_occurred_at`, `ix_domain_events_processing_status_occurred_at`.

### `xp_transactions`
**Ledger append-only de XP.** Prohibido `UPDATE` y `DELETE`.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `event_id` | `UUIDc` FK `domain_events.id` SET NULL | Sí | — | Evento que la originó. |
| `event_type` | `E(EventType)` | No | — | Evento (desnormalizado para consultas). |
| `source` | `E(XPSource)` | No | — | Dimensión de origen. |
| `source_id` | `UUIDc` | Sí | — | Id de la lección, misión, logro, etc. |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` SET NULL | Sí | — | Conocimiento: **la misma transacción alimenta XP global y XP del conocimiento**. |
| `topic_id` | `UUIDc` FK `topics.id` SET NULL | Sí | — | Tema, si aplica. |
| `is_educational` | `sa.Boolean` | No | `sa.true()` | `true` = XP educativo (cuenta para objetivo diario y día activo); `false` = XP de bonificación. |
| `base_amount` | `sa.Integer` | No | — | Valor base antes de multiplicadores. |
| `multiplier` | `sa.Numeric(5, 3)` | No | `1.000` | Producto de los multiplicadores aplicados. |
| `amount` | `sa.Integer` | No | — | XP final otorgado. |
| `reason_code` | `sa.String(32)` | No | — | `first_completion`, `repeat_20`, `repeat_0`, `question_first_try`, `question_second_try`, `question_cap_reached`, `time_too_short`, `answer_too_fast`, `daily_softcap_50`, `daily_softcap_10`, `low_content_50`, `admin_adjustment`. |
| `config_version` | `sa.Integer` | No | — | Versión de `game_configs` vigente al calcular. |
| `balance_after` | `sa.BigInteger` | No | — | XP total del usuario tras la transacción. |
| `local_date` | `sa.Date` | No | — | Fecha local (topes diarios). |
| `idempotency_key` | `sa.String(120)` | No | — | Clave de idempotencia. |

Append-only (solo `created_at`).
Únicos: `uq_xp_transactions_user_id_idempotency_key`.
Índices: `ix_xp_transactions_user_id_created_at`, `ix_xp_transactions_user_id_knowledge_area_id`, `ix_xp_transactions_user_id_local_date`.
Checks: `ck_xp_transactions_amount_sign` → `amount >= 0 OR source = 'ADJUSTMENT'`.

### `level_definitions`
Tabla materializada de las dos curvas de nivel (global y por conocimiento). Se siembra al arrancar desde `game_configs`.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `scope` | `E(LevelScope)` | No | — | `global` (base 80) o `knowledge_area` (base 50). |
| `level` | `sa.Integer` | No | — | Nivel 1..50. |
| `xp_required` | `sa.BigInteger` | No | — | XP acumulado necesario para alcanzarlo. |
| `xp_delta` | `sa.Integer` | No | `0` | XP entre este nivel y el anterior. |
| `rank_title` | `sa.String(48)` | No | — | Título del rango vigente en ese nivel. |
| `is_rank_start` | `sa.Boolean` | No | `sa.false()` | `true` en 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50. |
| `unlocks` | `JSONB` | No | `'{}'::jsonb` | `{"shop_rarities": ["uncommon"], "gold_bonus": 100}`. |

Únicos: `uq_level_definitions_scope_level`.

### `streaks`
Estado materializado de la racha. Siempre recomputable desde `streak_days`.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `current_length` | `sa.Integer` | No | `0` | Días consecutivos activos. |
| `best_length` | `sa.Integer` | No | `0` | Mejor racha histórica; **nunca disminuye**. |
| `last_active_date` | `sa.Date` | Sí | — | Última fecha local activa. |
| `started_on` | `sa.Date` | Sí | — | Inicio de la racha actual. |
| `total_active_days` | `sa.Integer` | No | `0` | Días activos de por vida (logro Peregrino/a). |
| `grace_used_for_month` | `sa.String(7)` | Sí | — | Mes (`2026-09`) en que se consumió la gracia. |
| `travel_skip_used_on` | `sa.Date` | Sí | — | Último ajuste por viaje (1 cada 30 días). |
| `last_change` | `E(StreakChange)` | Sí | — | Motivo del último cambio. |
| `last_milestone_reached` | `sa.Integer` | No | `0` | Último hito otorgado. |
| `broken_at` | `sa.DateTime(timezone=True)` | Sí | — | Cierre de la última racha. |
| `previous_length` | `sa.Integer` | No | `0` | Longitud de la racha anterior ("Última racha: 21 días"). |

Únicos: `uq_streaks_user_id`.
Índices: `ix_streaks_last_active_date` (el planificador de avisos barre por aquí:
la racha viva se deduce de la última fecha activa, nunca de `current_length`, que
no caduca sola).

### `streak_days`
Agregado por usuario y **fecha local**: fuente de verdad del calendario, del día activo y del objetivo diario.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `local_date` | `sa.Date` | No | — | Fecha local. |
| `educational_xp` | `sa.Integer` | No | `0` | XP educativo del día (piso de día activo: 30). |
| `bonus_xp` | `sa.Integer` | No | `0` | XP de bonificación (no cuenta para el día activo). |
| `effective_seconds` | `sa.Integer` | No | `0` | Tiempo efectivo del día. |
| `activity_units` | `sa.Integer` | No | `0` | Unidades: lección 1, 5 preguntas 1, repaso 1, desafío 1, evaluación 2. |
| `lessons_completed` | `sa.Integer` | No | `0` | Lecciones nuevas completadas. |
| `questions_total` | `sa.Integer` | No | `0` | Preguntas respondidas. |
| `questions_correct` | `sa.Integer` | No | `0` | Aciertos. |
| `activities_completed` | `sa.Integer` | No | `0` | Actividades completadas. |
| `goal_type_snapshot` | `E(GoalType)` | Sí | — | Objetivo vigente al empezar el día (histórico auditable). |
| `goal_target_snapshot` | `sa.Integer` | Sí | — | Meta vigente ese día. |
| `goal_progress` | `sa.Integer` | No | `0` | Avance en la unidad del objetivo. |
| `goal_met_at` | `sa.DateTime(timezone=True)` | Sí | — | Cumplimiento (idempotente: una vez por día). |
| `day_status` | `E(DayStatus)` | No | `INACTIVE` | Inactivo, activo, gracia o viaje. |
| `first_activity_at` | `sa.DateTime(timezone=True)` | Sí | — | Primera actividad (bono +20 XP y hora habitual). |
| `last_activity_at` | `sa.DateTime(timezone=True)` | Sí | — | Última actividad. |
| `xp_softcap_applied` | `sa.String(24)` | Sí | — | `none`, `daily_softcap_50`, `daily_softcap_10`. |

Únicos: `uq_streak_days_user_id_local_date`.
Índices: `ix_streak_days_user_id_local_date` (descendente en la consulta del calendario).

### `daily_goals`
Objetivo diario del usuario, con cambio pendiente y recomendación adaptativa. Una fila por usuario.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `goal_type` | `E(GoalType)` | No | `MINUTES` | Tipo vigente. |
| `target` | `sa.Integer` | No | `20` | Meta vigente. |
| `effective_from` | `sa.Date` | No | — | Desde cuándo rige. |
| `pending_type` | `E(GoalType)` | Sí | — | Cambio programado (las bajadas rigen al día siguiente). |
| `pending_target` | `sa.Integer` | Sí | — | Meta programada. |
| `pending_from` | `sa.Date` | Sí | — | Fecha de entrada en vigor. |
| `recommendation` | `JSONB` | No | `'{}'::jsonb` | `{direction, suggested_type, suggested_target, computed_on}`. |
| `recommendation_shown_at` | `sa.DateTime(timezone=True)` | Sí | — | Última vez mostrada. |
| `recommendation_rejected_at` | `sa.DateTime(timezone=True)` | Sí | — | Rechazo (no se repite en 28 días). |

Únicos: `uq_daily_goals_user_id`.
Checks: `ck_daily_goals_target_positive` → `target > 0`.

### `mission_templates`
Catálogo de plantillas parametrizadas. Sin IA: el selector es determinista.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `code` | `sa.String(24)` | No | — | `D01`…`D13`, `S01`…`S04`, `W01`…`W06`. |
| `scope` | `E(MissionScope)` | No | — | `diaria`, `semanal`, `especial`. |
| `title_template` | `sa.String(160)` | No | — | `"Completa {n} lecciones"`. |
| `narrative_key` | `sa.String(64)` | Sí | — | Clave de texto narrativo. |
| `metric` | `JSONB` | No | `'{}'::jsonb` | `{type, event, where, field}` — tipos de `MissionMetricType`. |
| `params` | `JSONB` | No | `'{}'::jsonb` | `{"n": {"easy": 1, "medium": 2, "hard": 3}}`. |
| `target_scope` | `sa.String(24)` | No | `"any"` | `any`, `knowledge_area`, `path`. |
| `eligibility` | `JSONB` | No | `'[]'::jsonb` | Predicados: `has_weak_topic`, `has_available_assessment`, `has_unstarted_topic`, `has_failed_questions_gte`, `active_areas_gte`, `streak_gte`, `has_available_challenge`. |
| `exclude_if_goal_type` | `JSONB` | No | `'[]'::jsonb` | Evita duplicar el objetivo diario. |
| `reward_profile` | `sa.String(24)` | No | `"daily_default"` | `daily_default`, `weekly_default`, `path_special`. |
| `rewards` | `JSONB` | No | `'{}'::jsonb` | Recompensa explícita si no usa perfil. |
| `weight` | `sa.Integer` | No | `1` | Peso en la selección ponderada. |
| `version` | `sa.Integer` | No | `1` | Las instancias guardan la versión usada. |
| `is_active` | `sa.Boolean` | No | `sa.true()` | Semanales llegan con `false` en el MVP. |

Únicos: `uq_mission_templates_code`.

### `user_missions`
Instancia de misión asignada a un usuario.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `template_id` | `UUIDc` FK `mission_templates.id` RESTRICT | No | — | Plantilla. |
| `template_code` | `sa.String(24)` | No | — | Código (desnormalizado). |
| `template_version` | `sa.Integer` | No | `1` | Versión congelada al asignar. |
| `scope` | `E(MissionScope)` | No | — | Horizonte. |
| `tier` | `E(MissionTier)` | Sí | — | Dificultad de la instancia. |
| `params` | `JSONB` | No | `'{}'::jsonb` | Parámetros resueltos. |
| `title` | `sa.String(200)` | No | — | Título ya interpolado. |
| `target` | `sa.Integer` | No | — | Objetivo numérico. |
| `progress` | `sa.Integer` | No | `0` | Avance (`LEAST(target, progress + delta)`). |
| `status` | `E(MissionStatus)` | No | `ACTIVE` | Estado. |
| `learning_path_id` | `UUIDc` FK `learning_paths.id` CASCADE | Sí | — | Misión de ruta. |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` SET NULL | Sí | — | Área objetivo. |
| `assigned_for` | `sa.Date` | Sí | — | Fecha local de asignación (diarias). |
| `expires_at` | `sa.DateTime(timezone=True)` | Sí | — | Medianoche local; nulo en misiones de ruta. |
| `reward_xp` | `sa.Integer` | No | `0` | XP de bonificación. |
| `reward_gold` | `sa.Integer` | No | `0` | Oro. |
| `reward_item_id` | `UUIDc` FK `items.id` SET NULL | Sí | — | Ítem (solo misiones especiales). |
| `completed_at` | `sa.DateTime(timezone=True)` | Sí | — | Cumplida. |
| `claimed_at` | `sa.DateTime(timezone=True)` | Sí | — | Reclamada (automática al expirar). |
| `last_event_id` | `UUIDc` FK `domain_events.id` SET NULL | Sí | — | Último evento aplicado (idempotencia del progreso). |

Únicos: `uq_user_missions_user_id_template_id_assigned_for`.
Índices: `ix_user_missions_user_id_status_expires_at`, `ix_user_missions_learning_path_id`.

### `achievements`
Catálogo de logros con reglas declarativas y niveles.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `code` | `sa.String(48)` | No | — | `ACH_ORACLE`, `ACH_FLAME_KEEPER`… |
| `name` | `sa.String(80)` | No | — | Nombre visible ("Oráculo"). |
| `description` | `sa.Text` | Sí | — | Descripción o pista si es oculto. |
| `category` | `E(AchievementCategory)` | No | — | Pestaña de la sala de trofeos. |
| `visibility` | `E(AchievementVisibility)` | No | `VISIBLE` | Visible u oculto. |
| `rule` | `JSONB` | No | `'{}'::jsonb` | `{type, event, where, success_when, reset_when, stat, op, on_events}`. |
| `tiers` | `JSONB` | No | `'[]'::jsonb` | `[{tier, target, reward:{xp, gold, title_id}}]`, objetivos crecientes. |
| `icon_key` | `sa.String(48)` | Sí | — | Medalla. |
| `sort_order` | `sa.Integer` | No | `100` | Orden en la cuadrícula. |
| `version` | `sa.Integer` | No | `1` | Versión de la definición. |
| `is_active` | `sa.Boolean` | No | `sa.true()` | Retirar sin borrar. |

Únicos: `uq_achievements_code`.

### `user_achievements`
Progreso y niveles desbloqueados de un logro para un usuario (una fila por par usuario-logro).

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `achievement_id` | `UUIDc` FK `achievements.id` CASCADE | No | — | Logro. |
| `counter` | `sa.Integer` | No | `0` | Estado de `counter` / `sum` / `stat_threshold`. |
| `current_consecutive` | `sa.Integer` | No | `0` | Racha en curso (`consecutive`). |
| `max_consecutive` | `sa.Integer` | No | `0` | Máximo histórico. |
| `distinct_values` | `JSONB` | No | `'[]'::jsonb` | Valores distintos (`distinct_count`). |
| `highest_tier` | `E(AchievementTier)` | Sí | — | Nivel más alto desbloqueado. |
| `unlocked_tiers` | `JSONB` | No | `'[]'::jsonb` | `[{tier, unlocked_at, reward_xp, reward_gold, title_id, reward_granted}]`. |
| `progress_pct` | `sa.Numeric(5, 2)` | No | `0` | Avance hacia el próximo nivel ("casi lo tienes" ≥ 80 %). |
| `first_unlocked_at` | `sa.DateTime(timezone=True)` | Sí | — | Primer nivel. |
| `last_unlocked_at` | `sa.DateTime(timezone=True)` | Sí | — | Último nivel. |
| `last_event_id` | `UUIDc` FK `domain_events.id` SET NULL | Sí | — | Último evento aplicado (idempotencia). |

Únicos: `uq_user_achievements_user_id_achievement_id`.
Índices: `ix_user_achievements_user_id_highest_tier`.

### `reward_rules`
Regla declarativa evento → recompensa. **Sustituye a cualquier constante de XP u oro en el código**: el motor busca aquí, y el importe puede venir de una clave de `game_configs`.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `code` | `sa.String(48)` | No | — | `lesson_completed_base`, `assessment_bonus_90`… |
| `event_type` | `E(EventType)` | No | — | Evento que la dispara. |
| `condition` | `JSONB` | No | `'{}'::jsonb` | `{"passed": true, "score_pct_gte": 90}`. |
| `xp_amount` | `sa.Integer` | No | `0` | XP base (ignorado si hay `xp_config_key`). |
| `xp_config_key` | `sa.String(80)` | Sí | — | Clave de `game_configs` que manda sobre `xp_amount`. |
| `xp_source` | `E(XPSource)` | Sí | — | Dimensión del ledger de XP. |
| `is_educational` | `sa.Boolean` | No | `sa.true()` | XP educativo o de bonificación. |
| `gold_amount` | `sa.Integer` | No | `0` | Oro base. |
| `gold_config_key` | `sa.String(80)` | Sí | — | Clave de `game_configs` que manda sobre `gold_amount`. |
| `gold_source` | `E(GoldSource)` | Sí | — | Dimensión del ledger de oro. |
| `item_id` | `UUIDc` FK `items.id` SET NULL | Sí | — | Ítem otorgado. |
| `first_time_only` | `sa.Boolean` | No | `sa.true()` | Solo la primera vez (regla A1). |
| `respects_daily_cap` | `sa.Boolean` | No | `sa.true()` | Sujeta a topes diarios blandos. |
| `respects_repeat_multiplier` | `sa.Boolean` | No | `sa.true()` | Sujeta a 1.0 / 0.2 / 0.0. |
| `priority` | `sa.Integer` | No | `100` | Orden de evaluación. |
| `is_active` | `sa.Boolean` | No | `sa.true()` | Activación sin desplegar. |
| `valid_from` | `sa.DateTime(timezone=True)` | No | `func.now()` | Vigencia desde. |
| `valid_to` | `sa.DateTime(timezone=True)` | Sí | — | Vigencia hasta (`null` = vigente). |

Únicos: `uq_reward_rules_code`.
Índices: `ix_reward_rules_event_type_is_active`.

### `game_configs`
Configuración versionada de todo valor de juego. **Ningún número de §5 se escribe en el código.**

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `key` | `sa.String(80)` | No | — | Clave con espacio de nombres (`xp.lesson_completed`). |
| `version` | `sa.Integer` | No | `1` | Versión por clave (incremental). |
| `config_version` | `sa.BigInteger` | No | — | Contador global monótono (`nextval('game_config_version_seq')`); se copia a cada transacción de XP y oro. |
| `value` | `JSONB` | No | — | Escalar, lista o mapa. |
| `value_type` | `sa.String(12)` | No | — | `int`, `decimal`, `bool`, `string`, `list`, `map`. |
| `valid_from` | `sa.DateTime(timezone=True)` | No | `func.now()` | Vigencia desde. |
| `valid_to` | `sa.DateTime(timezone=True)` | Sí | — | Vigencia hasta (`null` = vigente). |
| `is_public` | `sa.Boolean` | No | `sa.false()` | Se expone en `GET /api/v1/config/public`. |
| `description` | `sa.Text` | Sí | — | Para qué sirve. |
| `created_by` | `UUIDc` FK `users.id` SET NULL | Sí | — | Quién la cambió. |

Únicos: `uq_game_configs_key_version`.
Índices: `ix_game_configs_key_valid_from`.
Resolución del valor vigente: fila con `valid_from <= now() < coalesce(valid_to, 'infinity')` y mayor `version`. Caché en memoria del backend con TTL de 60 s.
La secuencia se crea en la migración: `CREATE SEQUENCE game_config_version_seq START 1;`

### `notifications`
Notificaciones in-app y push, con programación y antifatiga.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Destinatario. |
| `notification_type` | `E(NotificationType)` | No | — | Tipo. |
| `channel` | `E(NotificationChannel)` | No | `IN_APP` | Canal. |
| `status` | `E(NotificationStatus)` | No | `PENDING` | Estado. |
| `title` | `sa.String(120)` | No | — | Título (español, tono de recuperación, sin culpa). |
| `body` | `sa.String(400)` | No | — | Cuerpo. |
| `deep_link` | `sa.String(160)` | Sí | — | `home`, `streak`, `missions`, `route/{id}`, `route/{id}/generation`, `review/{topic_id}`. |
| `payload` | `JSONB` | No | `'{}'::jsonb` | Datos extra para el cliente. |
| `scheduled_for` | `sa.DateTime(timezone=True)` | Sí | — | Envío programado (respeta horas de silencio). |
| `sent_at` | `sa.DateTime(timezone=True)` | Sí | — | Envío efectivo. |
| `read_at` | `sa.DateTime(timezone=True)` | Sí | — | Lectura. |
| `dismissed_at` | `sa.DateTime(timezone=True)` | Sí | — | Descarte. |
| `local_date` | `sa.Date` | Sí | — | Fecha local (topes por día). |
| `idempotency_key` | `sa.String(120)` | No | — | Evita duplicados del programador. |

Únicos: `uq_notifications_idempotency_key`.
Índices: `ix_notifications_user_id_status`, `ix_notifications_scheduled_for`,
`ix_notifications_user_id_local_date` (los topes por día se cuentan sobre la fecha
local del usuario).

**Programar no es entregar.** Una fila nace `PENDING` con `scheduled_for` en el
futuro, o `SENT` si es para ahora mismo. El despachador del worker es quien la pasa
a `SENT`; mientras siga `PENDING` **no aparece en la bandeja**. Una que lleve más de
seis horas vencida sin entregarse pasa a `FAILED` en vez de entregarse tarde.
`GET /notifications` solo devuelve `SENT` y `READ`.

---

## 3.6 `app/models/economy.py` — módulo `economy`

### `items`
Catálogo de ítems (globales, plantillas y derivados por usuario/área). **No existe ningún campo de estadística de juego: los ítems son 100 % cosméticos.**

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `code` | `sa.String(64)` | No | — | Slug estable (`espada_del_sql`); en derivados `tpl_capa_maestro__<area_slug>`. |
| `name` | `sa.String(80)` | No | — | Nombre visible. |
| `description` | `sa.Text` | Sí | — | Lore de 1–2 frases. |
| `slot` | `E(ItemSlot)` | No | — | Ranura que ocupa. |
| `rarity` | `E(ItemRarity)` | No | — | Rareza. |
| `origin` | `E(ItemOrigin)` | No | — | Origen principal (etiqueta del "currículum visual"). |
| `requirements` | `JSONB` | No | `'{}'::jsonb` | Árbol DSL `all`/`any` (profundidad máx. 2). Espejo normalizado en `item_requirements`. |
| `requirement_facts` | `JSONB` | No | `'[]'::jsonb` | Familias que referencia: `path`, `mastery`, `assessment`, `streak`, `level`, `achievement`, `lessons`, `time`. |
| `auto_grant` | `sa.Boolean` | No | `sa.false()` | `true`: al cumplirse los requisitos se otorga solo. `false`: solo habilita la compra. |
| `render_manifest` | `JSONB` | No | `'{}'::jsonb` | Capas, offsets, `suppresses_layers`, `two_handed`, `tint`, `icon`. |
| `icon_key` | `sa.String(120)` | Sí | — | Icono dedicado si el recorte no lee bien. |
| `is_template` | `sa.Boolean` | No | `sa.false()` | Plantilla derivable por área (no equipable). |
| `template_code` | `sa.String(48)` | Sí | — | Plantilla de la que deriva. |
| `owner_user_id` | `UUIDc` FK `users.id` CASCADE | Sí | — | Dueño del derivado. |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` SET NULL | Sí | — | Área que tematiza el derivado. |
| `set_code` | `sa.String(48)` | Sí | — | Conjunto (reservado, fase 2). |
| `visibility` | `E(ItemVisibility)` | No | `PUBLIC` | Quién lo ve bloqueado. |
| `tier_required` | `sa.String(16)` | Sí | — | `premium` reservado; **prohibido** si `origin = knowledge`. |
| `is_active` | `sa.Boolean` | No | `sa.true()` | Retirar sin borrar. |
| `available_from` | `sa.DateTime(timezone=True)` | Sí | — | Ventana de evento. |
| `available_to` | `sa.DateTime(timezone=True)` | Sí | — | Ventana de evento. |
| `catalog_version` | `sa.Integer` | No | `1` | Versión del catálogo. |

Únicos: `uq_items_code`; índice único parcial creado en la migración: `CREATE UNIQUE INDEX uq_items_derived ON items (template_code, owner_user_id, knowledge_area_id) WHERE template_code IS NOT NULL;`
Índices: `ix_items_owner_user_id`, `ix_items_is_active_visibility`, `ix_items_origin_rarity`; GIN sobre `requirement_facts` (`op.execute`: `CREATE INDEX ix_items_requirement_facts ON items USING gin (requirement_facts jsonb_path_ops);`).
Checks: `ck_items_knowledge_not_premium` → `tier_required IS NULL OR origin <> 'KNOWLEDGE'`.

### `item_requirements`
Espejo normalizado del DSL, una fila por condición. Permite evaluar y **explicar** el progreso sin recorrer JSON.

Semántica: el ítem se desbloquea si **algún** `group_index` tiene **todas** sus condiciones cumplidas (OR de ANDs).

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `item_id` | `UUIDc` FK `items.id` CASCADE | No | — | Ítem. |
| `group_index` | `sa.Integer` | No | `0` | Grupo OR. |
| `position` | `sa.Integer` | No | `0` | Orden dentro del grupo. |
| `requirement_type` | `E(RequirementType)` | No | — | Tipo de condición. |
| `knowledge_area_id` | `UUIDc` FK `knowledge_areas.id` SET NULL | Sí | — | Área concreta. |
| `area_slug` | `sa.String(64)` | Sí | — | `self` en plantillas, o el slug canónico. |
| `target_value` | `sa.Numeric(10, 2)` | Sí | — | Umbral (dominio, puntaje). |
| `target_count` | `sa.Integer` | Sí | — | Cantidad (áreas dominadas, evaluaciones, lecciones, días). |
| `achievement_code` | `sa.String(48)` | Sí | — | Logro exigido. |
| `streak_kind` | `E(StreakKind)` | Sí | — | `current` o `best` (los ítems de racha usan `best`). |
| `window_from` | `sa.DateTime(timezone=True)` | Sí | — | Ventana temporal. |
| `window_to` | `sa.DateTime(timezone=True)` | Sí | — | Ventana temporal. |
| `label_template` | `sa.String(160)` | Sí | — | Texto explicativo ("Dominio de {area}: {current} / {target} %"). |

Índices: `ix_item_requirements_item_id`, `ix_item_requirements_requirement_type`.

### `user_items`
Instancia poseída. Único por `(user_id, item_id)`: los cosméticos no se acumulan.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Dueño. |
| `item_id` | `UUIDc` FK `items.id` RESTRICT | No | — | Ítem del catálogo. |
| `acquired_at` | `sa.DateTime(timezone=True)` | No | `func.now()` | Fecha de adquisición (brief §15). |
| `origin` | `E(ItemOrigin)` | No | — | Origen **real** de esta instancia. |
| `source_ref` | `JSONB` | No | `'{}'::jsonb` | `{purchase_id}`, `{achievement_code}`, `{streak_days}`, `{trigger_event_id, requirements_snapshot}`. |
| `is_new` | `sa.Boolean` | No | `sa.true()` | Insignia "nuevo" hasta abrir la ficha. |
| `revoked_at` | `sa.DateTime(timezone=True)` | Sí | — | Revocación por soporte o fraude (nunca borrado físico). |
| `revoke_reason` | `sa.String(120)` | Sí | — | Motivo. |

Únicos: `uq_user_items_user_id_item_id`.
Índices: `ix_user_items_user_id_acquired_at`.

### `wallets`
Saldo cacheado por moneda. Se bloquea con `SELECT … FOR UPDATE` en toda compra.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Dueño. |
| `currency` | `E(Currency)` | No | `GOLD` | Moneda (`gems` reservado y desactivado). |
| `balance` | `sa.Integer` | No | `0` | Saldo actual. |
| `lifetime_earned` | `sa.Integer` | No | `0` | Total ganado. |
| `lifetime_spent` | `sa.Integer` | No | `0` | Total gastado. |
| `version` | `sa.Integer` | No | `0` | Contador de versiones (bloqueo optimista). |

Únicos: `uq_wallets_user_id_currency`.
Checks: `ck_wallets_balance_non_negative` → `balance >= 0`.

### `gold_transactions`
**Ledger append-only de oro.** Prohibido `UPDATE` y `DELETE`.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Usuario. |
| `currency` | `E(Currency)` | No | `GOLD` | Moneda. |
| `event_id` | `UUIDc` FK `domain_events.id` SET NULL | Sí | — | Evento que la originó. |
| `direction` | `E(LedgerDirection)` | No | — | `credit` o `debit`. |
| `source` | `E(GoldSource)` | Sí | — | Obligatoria en `credit`. |
| `sink` | `E(GoldSink)` | Sí | — | Obligatoria en `debit`. |
| `source_id` | `UUIDc` | Sí | — | Id de la lección, misión, compra… |
| `amount` | `sa.Integer` | No | — | Importe positivo. |
| `balance_after` | `sa.Integer` | No | — | Saldo tras la transacción. |
| `reason_code` | `sa.String(32)` | No | — | `first_completion`, `daily_softcap_50`, `purchase`, `reversal`, `admin_adjustment`… |
| `config_version` | `sa.Integer` | No | — | Versión de configuración aplicada. |
| `local_date` | `sa.Date` | No | — | Fecha local (topes diarios). |
| `idempotency_key` | `sa.String(120)` | No | — | Clave de idempotencia. |

Append-only (solo `created_at`).
Únicos: `uq_gold_transactions_user_id_idempotency_key`.
Índices: `ix_gold_transactions_user_id_created_at`, `ix_gold_transactions_user_id_local_date`.
Checks: `ck_gold_transactions_amount_positive` → `amount > 0`; `ck_gold_transactions_balance_non_negative` → `balance_after >= 0`; `ck_gold_transactions_direction_dimension` → `(direction = 'CREDIT' AND source IS NOT NULL AND sink IS NULL) OR (direction = 'DEBIT' AND sink IS NOT NULL AND source IS NULL)`.

### `shop_listings`
Precio y disponibilidad de un ítem en la tienda. **El precio no vive en `items`.**

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `item_id` | `UUIDc` FK `items.id` CASCADE | No | — | Ítem ofertado. |
| `currency` | `E(Currency)` | No | `GOLD` | Moneda (solo `gold` activa). |
| `price` | `sa.Integer` | No | — | Precio; por defecto el de la rareza. |
| `min_level` | `sa.Integer` | No | `1` | Nivel mínimo (por rareza; sobreescribible por ítem). |
| `is_featured` | `sa.Boolean` | No | `sa.false()` | Destacado (2–4 a la vez). |
| `featured_order` | `sa.Integer` | Sí | — | Orden entre destacados. |
| `available_from` | `sa.DateTime(timezone=True)` | Sí | — | Ventana. |
| `available_to` | `sa.DateTime(timezone=True)` | Sí | — | Ventana. |
| `is_active` | `sa.Boolean` | No | `sa.true()` | Retirar sin borrar. |

Únicos: índice único parcial en la migración: `CREATE UNIQUE INDEX uq_shop_listings_active ON shop_listings (item_id, currency) WHERE is_active;`
Índices: `ix_shop_listings_is_active_is_featured`.
Checks: `ck_shop_listings_price_positive` → `price > 0`.

### `purchases`
Orden de compra atómica: debita el ledger, crea la instancia y queda auditada.

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `user_id` | `UUIDc` FK `users.id` CASCADE | No | — | Comprador. |
| `listing_id` | `UUIDc` FK `shop_listings.id` RESTRICT | No | — | Listado comprado. |
| `item_id` | `UUIDc` FK `items.id` RESTRICT | No | — | Ítem (desnormalizado). |
| `currency` | `E(Currency)` | No | `GOLD` | Moneda. |
| `price` | `sa.Integer` | No | — | Precio cobrado (el del servidor, no el del cliente). |
| `status` | `E(PurchaseStatus)` | No | `COMPLETED` | `completed` o `reversed`. |
| `gold_transaction_id` | `UUIDc` FK `gold_transactions.id` SET NULL | Sí | — | Débito asociado. |
| `user_item_id` | `UUIDc` FK `user_items.id` SET NULL | Sí | — | Instancia entregada. |
| `reversal_transaction_id` | `UUIDc` FK `gold_transactions.id` SET NULL | Sí | — | Crédito de la reversión. |
| `reversed_at` | `sa.DateTime(timezone=True)` | Sí | — | "Deshacer" dentro de la ventana de 60 s. |
| `idempotency_key` | `sa.String(120)` | No | — | Clave del cliente. |

Únicos: `uq_purchases_user_id_idempotency_key`.
Índices: `ix_purchases_user_id_created_at`.

---

## 3.7 Resumen del catálogo

| Archivo | Tablas |
|---|---|
| `identity.py` | `users`, `refresh_tokens`, `user_settings`, `characters`, `avatar_configs`, `equipped_items` |
| `content.py` | `knowledge_areas`, `territories`, `learning_paths`, `path_modules`, `topics`, `lessons`, `lesson_blocks`, `questions`, `assessments`, `assessment_questions` |
| `ingestion.py` | `knowledge_bases`, `documents`, `document_versions`, `document_chunks`, `generation_jobs`, `prompt_templates`, `content_provenance` |
| `progress.py` | `learning_sessions`, `study_activities`, `question_attempts`, `assessment_attempts`, `user_path_progress`, `user_module_progress`, `user_lesson_progress`, `user_topic_progress`, `user_area_progress` |
| `gamification.py` | `domain_events`, `xp_transactions`, `level_definitions`, `streaks`, `streak_days`, `daily_goals`, `mission_templates`, `user_missions`, `achievements`, `user_achievements`, `reward_rules`, `game_configs`, `notifications` |
| `economy.py` | `items`, `item_requirements`, `user_items`, `wallets`, `gold_transactions`, `shop_listings`, `purchases` |

**Orden de creación en Alembic** (por dependencias de clave foránea): `identity` (`users` primero) → `content` (`knowledge_areas` → resto) → `ingestion` → `progress` → `gamification` → `economy`. Tres referencias cruzan hacia adelante y se resuelven en la misma migración inicial porque Alembic ordena por dependencia dentro de un solo `upgrade()`: `equipped_items.user_item_id → user_items`, `learning_paths.knowledge_base_id → knowledge_bases`, `territories.generated_by_job_id → generation_jobs`, `reward_rules.item_id → items`, `user_missions.reward_item_id → items`. Si Alembic no logra ordenarlas, se crean esas cinco claves foráneas al final del `upgrade()` con `op.create_foreign_key(...)`.
---

# 4. Catálogo de eventos de dominio

## 4.1 Sobre (envelope) común

Todo evento se persiste como una fila de `domain_events` con esta forma lógica. `local_date` la calcula **el servidor** al ingerir, con la zona horaria del usuario, y viaja con el evento para que todos los consumidores usen la misma fecha.

```json
{
  "event_id": "c1f4a4d2-6f9e-4c31-9a0e-1f1d2b3c4d5e",
  "event_type": "LESSON_COMPLETED",
  "version": 1,
  "user_id": "9b7f…",
  "occurred_at": "2026-09-10T02:58:40Z",
  "received_at": "2026-09-10T02:58:41Z",
  "timezone": "America/Santiago",
  "local_date": "2026-09-09",
  "source_module": "progress",
  "correlation_id": "7d2c…",
  "causation_id": null,
  "idempotency_key": "lesson-complete:9b7f…:a1c2…:1",
  "payload": { "…": "…" }
}
```

Reglas del bus (todas obligatorias):

1. **Idempotencia**: `idempotency_key` es única global. Reprocesar un evento no duplica XP, oro, ítems ni progreso.
2. **Orden de consumo** dentro de una acción: `XP/oro` → `agregado diario y objetivo` → `racha` → `misiones` → `logros` → `desbloqueos de ítems`. Los logros van al final porque consumen `DAILY_GOAL_MET`, `STREAK_UPDATED` y `MISSION_COMPLETED`.
3. **Regla anti-bucle**: `XP_AWARDED` con `is_educational = false` (misiones, hitos, logros) **no** vuelve a alimentar el agregado diario ni la racha. Ninguna recompensa de gamificación cuenta como aprendizaje.
4. **Server-authoritative**: los eventos de aprendizaje los emite el servidor a partir de hechos verificados (`A7`), nunca el cliente directamente. El cliente solo emite los tres eventos de analítica (`REWARD_VIEWED`, `PROFILE_VIEWED`, `KNOWLEDGE_VIEWED`).
5. **`counts_for_progress`**: bandera que pone el módulo `progress` en los eventos de aprendizaje. Si es `false` (repetición trivial, respuesta en < 2 s, tiempo implausible), el evento **no** alimenta objetivo diario, racha, misiones ni logros.

## 4.2 Catálogo completo (59 eventos)

Leyenda de consumidores: **XP** = motor de XP/oro · **DIA** = agregado diario y objetivo (`streak_days`, `daily_goals`) · **RAC** = rachas · **MIS** = misiones · **LOG** = logros · **DOM** = dominio · **ITM** = evaluador de desbloqueos de ítems · **NOT** = notificaciones · **ANA** = analítica · **UI** = respuesta al cliente.

### Identidad y onboarding

| Evento | Productor | Payload de ejemplo | Reaccionan |
|---|---|---|---|
| `USER_REGISTERED` | `identity` | `{"email_domain": "gmail.com", "auth_provider": "email"}` | ANA |
| `USER_LOGGED_IN` | `identity` | `{"device": "android"}` | ANA |
| `USER_DELETED` | `identity` | `{"reason": "user_request"}` | ANA |
| `CHARACTER_CREATED` | `identity` | `{"character_id": "…", "archetype": "arcane", "name": "Rodrigo"}` | XP (bolsa de bienvenida 100 🪙), LOG (`ACH_WELCOME`), ITM (kit inicial), ANA |
| `AVATAR_UPDATED` | `identity` | `{"changed": ["hair_style_id", "hair_color"]}` | ANA |
| `SETTINGS_UPDATED` | `identity` | `{"changed": ["reminder_mode"]}` | NOT, ANA |

### Contenido, ingesta y generación

| Evento | Productor | Payload de ejemplo | Reaccionan |
|---|---|---|---|
| `KNOWLEDGE_AREA_CREATED` | `content` | `{"knowledge_area_id": "…", "slug": "apicultura", "short_name": "Apicultura", "category": "science", "is_canonical": false}` | ITM (materializa ítems derivados), ANA |
| `PATH_CREATED` | `content` | `{"path_id": "…", "knowledge_area_id": "…", "source_mode": "con_fuente", "origin": "user", "declared_level": "beginner"}` | MIS (instancia misiones de ruta), LOG (`ACH_FIRST_QUEST`, `ACH_POLYMATH`), ITM, ANA |
| `DOCUMENT_UPLOADED` | `ingestion` | `{"document_id": "…", "document_type": "pdf", "byte_size": 2100000, "page_count": 87}` | ANA |
| `TEXT_PASTED` | `ingestion` | `{"document_id": "…", "word_count": 1240}` | ANA |
| `DOCUMENT_INGESTED` | `ingestion` | `{"document_id": "…", "document_version_id": "…", "chunk_count": 212, "token_count": 96500, "language": "es"}` | `ai` (dispara diseño de ruta), UI, ANA |
| `DOCUMENT_FAILED` | `ingestion` | `{"document_id": "…", "reason": "scanned_pdf_no_text"}` | NOT, UI, ANA |
| `PATH_GENERATED` | `ai` | `{"path_id": "…", "modules": 8, "topics": 34, "coverage_notes": ["Sin material de window functions"], "job_id": "…"}` | UI (pantalla de revisión), NOT (`PATH_READY`), ANA |
| `PATH_CONFIRMED` | `content` | `{"path_id": "…", "modules_kept": 8, "coverage_policy": "model_knowledge"}` | `ai` (encola módulo 1), ANA |
| `MODULE_CONTENT_READY` | `ai` | `{"path_id": "…", "module_id": "…", "module_index": 1, "lessons": 9, "questions": 45}` | NOT (`PATH_READY`), UI, ANA |
| `GENERATION_FAILED` | `ai` | `{"job_id": "…", "job_type": "lesson_generation", "target_id": "…", "reason": "schema_validation"}` | NOT (`GENERATION_FAILED`), UI, ANA |
| `CONTENT_REPORTED` | `content` | `{"content_type": "question", "content_id": "…", "reason": "incorrect", "comment": ""}` | `ai` (regenera), ANA |
| `AI_BUDGET_THRESHOLD` | `ai` | `{"threshold_pct": 80, "spent_usd": 24.1, "budget_usd": 30}` | NOT (equipo), ANA |

### Aprendizaje

| Evento | Productor | Payload de ejemplo | Reaccionan |
|---|---|---|---|
| `TOPIC_STARTED` | `progress` | `{"topic_id": "…", "module_id": "…", "path_id": "…", "knowledge_area_id": "…"}` | MIS (D07), ANA |
| `LESSON_STARTED` | `progress` | `{"lesson_id": "…", "study_activity_id": "…", "topic_id": "…"}` | ANA |
| `LESSON_COMPLETED` | `progress` | `{"lesson_id": "…", "study_activity_id": "…", "topic_id": "…", "module_id": "…", "path_id": "…", "knowledge_area_id": "…", "questions_total": 5, "questions_correct": 4, "accuracy_pct": 80.0, "duration_s": 512, "completion_index": 1, "is_first_completion": true, "is_low_content": false, "counts_for_progress": true}` | XP, DIA, RAC, MIS, LOG, DOM, ITM, UI |
| `QUESTION_ANSWERED` | `progress` | `{"question_id": "…", "topic_id": "…", "knowledge_area_id": "…", "lesson_id": "…", "assessment_attempt_id": null, "context": "lesson", "attempt_no": 1, "is_correct": true, "partial_score": 100.0, "difficulty": "medium", "evaluation_method": "deterministic", "response_ms": 6400, "is_retry_of_failed": false, "counts_for_progress": true}` | XP, DIA, MIS, LOG, DOM, UI |
| `CHALLENGE_COMPLETED` | `progress` | `{"study_activity_id": "…", "topic_id": "…", "path_id": "…", "knowledge_area_id": "…", "passed": true, "accuracy_pct": 100.0, "duration_s": 640}` | XP, DIA, RAC, MIS, LOG, DOM |
| `REVIEW_COMPLETED` | `progress` | `{"study_activity_id": "…", "topic_id": "…", "knowledge_area_id": "…", "questions_total": 6, "questions_correct": 5, "accuracy_pct": 83.3, "topic_was_weak": true, "paid_reviews_today": 1}` | XP, DIA, RAC, MIS, DOM (sube `stability_s`), ITM |
| `ASSESSMENT_STARTED` | `progress` | `{"assessment_id": "…", "attempt_id": "…", "attempt_no": 2, "question_count": 10}` | ANA |
| `ASSESSMENT_COMPLETED` | `progress` | `{"assessment_id": "…", "attempt_id": "…", "module_id": "…", "path_id": "…", "knowledge_area_id": "…", "attempt_no": 1, "score_pct": 90.0, "effective_score_pct": 90.0, "passed": true, "outcome": "passed_distinction", "per_topic_scores": [{"topic_id": "…", "pct": 100.0}], "weak_topic_ids": []}` | XP (300 + bonos), DIA, RAC, MIS, LOG, DOM, ITM, UI |
| `MODULE_COMPLETED` | `progress` | `{"module_id": "…", "module_index": 3, "path_id": "…", "knowledge_area_id": "…"}` | XP (200), DIA, MIS (S01), LOG, DOM, ITM, UI |
| `PATH_COMPLETED` | `progress` | `{"path_id": "…", "knowledge_area_id": "…", "modules": 8, "days_elapsed": 62}` | XP (1000), MIS (S03), LOG, ITM (Espada del SQL), `TERRITORY_UNLOCKED`, UI |
| `STUDY_TIME_TICKED` | `progress` | `{"session_id": "…", "study_activity_id": "…", "activity_type": "lesson", "seconds": 30}` | DIA (objetivo de minutos), MIS (D10), ANA |
| `STUDY_SESSION_ENDED` | `progress` | `{"session_id": "…", "active_seconds": 1180, "end_reason": "idle_timeout"}` | ANA |

### Dominio

| Evento | Productor | Payload de ejemplo | Reaccionan |
|---|---|---|---|
| `MASTERY_UPDATED` | `progress` | `{"topic_id": "…", "module_id": "…", "knowledge_area_id": "…", "topic_before": 63.0, "topic_after": 71.0, "module_after": 74.5, "area_before": 44.0, "area_after": 47.0, "topics_mastered": 6, "areas_mastered": 1}` | MIS (S04, W06), LOG, ITM, UI |
| `TOPIC_MASTERED` | `progress` | `{"topic_id": "…", "knowledge_area_id": "…", "mastery": 81.4}` | LOG (`ACH_TOPIC_DOMINATOR`), UI |
| `MODULE_MASTERED` | `progress` | `{"module_id": "…", "knowledge_area_id": "…", "mastery": 83.5}` | LOG, ITM, UI |
| `AREA_MASTERED` | `progress` | `{"knowledge_area_id": "…", "mastery": 82.0, "areas_mastered_total": 3}` | LOG (`ACH_REALM_MASTER`), ITM (Cetro, Tomo, Corona), UI |
| `WEAKNESS_DETECTED` | `progress` | `{"topic_id": "…", "knowledge_area_id": "…", "rule": "R1", "evidence": {"errors_last_10": 3}}` | MIS (misión de repaso), NOT (`REVIEW_RECOMMENDED`), `ai` (re-explicación), UI |

### Gamificación

| Evento | Productor | Payload de ejemplo | Reaccionan |
|---|---|---|---|
| `XP_AWARDED` | `gamification` | `{"amount": 50, "base_amount": 50, "multiplier": 1.0, "source": "lesson", "is_educational": true, "knowledge_area_id": "…", "reason_code": "first_completion", "balance_after": 12890, "ref_event_id": "…"}` | DIA (solo si `is_educational`), RAC, MIS (D08, W01), LOG, UI |
| `LEVEL_UP` | `gamification` | `{"level_before": 6, "level_after": 7, "rank_title": "Iniciado/a", "rank_changed": false, "scope": "global"}` | XP (bono 50 🪙), LOG (`ACH_VETERAN`), ITM, UI |
| `RANK_UP` | `gamification` | `{"level": 10, "rank_title": "Escriba", "gold_bonus": 100}` | XP, ITM, UI |
| `DAILY_GOAL_MET` | `gamification` | `{"local_date": "2026-09-10", "goal_type": "minutos", "goal_target": 20, "achieved": 22, "local_hour": 21, "streak_after": 8}` | XP/oro (bono de constancia), RAC, MIS (D13, W04), LOG (`ACH_ACHIEVER`), UI |
| `STREAK_UPDATED` | `gamification` | `{"previous_length": 7, "current_length": 8, "best_length": 12, "change": "extended", "day_status": "active"}` | LOG (`ACH_FLAME_KEEPER`), ITM (ítems de racha, usan `best_length`), NOT, UI |
| `STREAK_MILESTONE_REACHED` | `gamification` | `{"length": 7, "first_time": true, "reward": {"xp": 50, "gold": 50, "item_code": "antorcha_constancia"}}` | XP/oro, ITM, LOG, UI |
| `WEEK_PERFECT` | `gamification` | `{"week_start_date": "2026-09-07"}` | LOG (`ACH_PERFECT_WEEK`), UI |
| `MISSION_ASSIGNED` | `gamification` | `{"user_mission_id": "…", "template_code": "D04", "scope": "diaria", "tier": "easy", "assigned_for": "2026-09-10"}` | UI, ANA |
| `MISSION_COMPLETED` | `gamification` | `{"user_mission_id": "…", "template_code": "D04", "scope": "diaria", "tier": "easy", "target": 1, "progress": 1}` | LOG (`ACH_ADVENTURER`), UI, ANA |
| `MISSION_CLAIMED` | `gamification` | `{"user_mission_id": "…", "auto": false, "reward": {"xp": 40, "gold": 10, "item_code": null}}` | XP/oro, ITM, UI |
| `MISSION_EXPIRED` | `gamification` | `{"user_mission_id": "…", "progress": 2, "target": 3}` | ANA |
| `ACHIEVEMENT_UNLOCKED` | `gamification` | `{"achievement_code": "ACH_ORACLE", "tier": "silver", "reward": {"xp": 75, "gold": 60, "title_id": null}}` | XP/oro, ITM, UI |
| `NOTIFICATION_SCHEDULED` | `gamification` | `{"notification_id": "…", "notification_type": "streak_reminder", "scheduled_for": "2026-09-10T22:30:00Z"}` | NOT, ANA |

### Economía, inventario y mundo

| Evento | Productor | Payload de ejemplo | Reaccionan |
|---|---|---|---|
| `GOLD_AWARDED` | `economy` | `{"amount": 20, "source": "lesson", "balance_after": 1245, "reason_code": "first_completion", "ref_event_id": "…"}` | UI, ANA |
| `GOLD_SPENT` | `economy` | `{"amount": 1200, "sink": "purchase", "balance_after": 340, "purchase_id": "…"}` | UI, ANA |
| `ITEM_ACQUIRED` | `economy` | `{"user_item_id": "…", "item_code": "cetro_bigquery", "slot": "weapon", "rarity": "epic", "origin": "knowledge", "items_count": 12, "knowledge_linked": true, "unlock_reason": "Dominio de BigQuery ≥ 80 %", "requirements_snapshot": {"type": "mastery_gte", "area": "bigquery", "value": 80, "observed": 82}}` | LOG (`ACH_COLLECTOR`, `ACH_FORGED_IN_KNOWLEDGE`, `ACH_RARE_TREASURE`), MIS, NOT, UI |
| `ITEM_EQUIPPED` | `economy` | `{"slot": "cape", "user_item_id": "…", "item_code": "capa_plumas_nocturnas", "replaced_user_item_id": "…", "slots_filled": 6, "slots_total": 8}` | LOG (`ACH_FIRST_GEAR`, `ACH_FULL_ARMOR`), MIS, ANA |
| `ITEM_UNEQUIPPED` | `economy` | `{"slot": "cape", "user_item_id": "…"}` | ANA |
| `ITEM_PREVIEWED` | `economy` | `{"item_code": "espada_del_sql", "locked": true}` | ANA |
| `DERIVED_ITEMS_MATERIALIZED` | `economy` | `{"knowledge_area_id": "…", "item_codes": ["tpl_capa_estudiante__apicultura", "tpl_capa_maestro__apicultura"]}` | UI, ANA |
| `TERRITORY_UNLOCKED` | `content` | `{"territory_id": "…", "knowledge_area_id": "…", "territories_unlocked": 3}` | LOG (`ACH_CARTOGRAPHER`), UI, ANA |

### Analítica del cliente (embudo del MVP)

| Evento | Productor | Payload de ejemplo | Reaccionan |
|---|---|---|---|
| `REWARD_VIEWED` | cliente | `{"receipt_id": "…", "event_type": "LESSON_COMPLETED"}` | ANA |
| `PROFILE_VIEWED` | cliente | `{"section": "profile"}` | ANA |
| `KNOWLEDGE_VIEWED` | cliente | `{"knowledge_area_id": "…"}` | ANA |

## 4.3 Reconciliación de nombres (canónico vs. documentos de diseño)

Los documentos 01, 04, 06a, 06b y 06c usaron nombres distintos para el mismo hecho. **Solo el nombre canónico existe en el código**; los alias quedan aquí para trazabilidad y **no** deben aparecer en ningún archivo.

| Nombre canónico | Alias que aparecían en los documentos | Regla de reconciliación |
|---|---|---|
| `PATH_GENERATED` | `ROUTE_GENERATED` (04) | La entidad es `learning_path`; el evento sigue a la entidad. |
| `ASSESSMENT_COMPLETED` | `ASSESSMENT_SUBMITTED`, `ASSESSMENT_PASSED` (06a) | Un solo evento con `passed`, `score_pct` y `outcome` en el payload. Las reglas de recompensa distinguen por `condition`. |
| `QUESTION_ANSWERED` | `QUESTION_ANSWERED_CORRECT` (06a) | Un solo evento con `is_correct`; el acierto no es un evento distinto. |
| `MASTERY_UPDATED` | `AREA_MASTERY_UPDATED` (06c) | Un solo evento que transporta el delta de tema, módulo y área. |
| `AREA_MASTERED` | `KNOWLEDGE_MASTERED` (06a) | La entidad es `knowledge_areas`; se usa "area" en el código y "conocimiento" en la UI. |
| `XP_AWARDED` | `XP_GRANTED` (01) | Verbo único `AWARDED` para XP y oro. |
| `GOLD_AWARDED` | `GOLD_GRANTED` (01) | Ídem. |
| `STREAK_UPDATED` | `STREAK_EXTENDED` (01) | Un solo evento con `change` ∈ `started/extended/grace_used/travel_skip/broken`. |
| `STREAK_MILESTONE_REACHED` | `STREAK_MILESTONE` (06a) | Nombre del documento dueño de la mecánica (06b). |
| `ITEM_ACQUIRED` | `ITEM_UNLOCKED`, `ITEM_PURCHASED` (06c) | Un solo evento con `origin` (`knowledge`, `streak`, `achievement`, `shop`, `mission`, `starter`, `event`). La celebración del cliente se decide por `origin`. |
| `CHARACTER_CREATED` | — | Sin cambios. |
| `GENERATION_FAILED` | `job failed` (04) | Nombre único para cualquier fallo de generación. |
| (eliminado) | `REWARD_GRANTED` (06b) | No existe: la aplicación de recompensas se registra en los ledgers y se devuelve en el `RewardsReceipt`. |
| (eliminado) | `ITEM_GRANT_SKIPPED_DUPLICATE` (06c) | No existe como evento: el otorgamiento es `INSERT … ON CONFLICT DO NOTHING` y el intento duplicado se registra en el log de aplicación. |
| (eliminado) | `event_processed(event_id, consumer)` (06b) | No existe como tabla: el MVP procesa la cascada en una sola transacción y la idempotencia se garantiza por `domain_events.idempotency_key` más las claves únicas de cada ledger y de `user_missions`/`user_achievements`. |
---

# 5. Parámetros de juego (`game_configs`)

Esta es la **tabla única y canónica** de la semilla de `game_configs`. Reglas:

- Ningún valor de esta tabla puede aparecer como literal en el código Python o Dart: se lee siempre de `game_configs` (con caché en memoria de 60 s).
- `Tipo` es el valor de la columna `value_type`; el `value` se guarda como JSONB (un escalar JSON también es JSONB válido).
- `Púb.` = `is_public`: si es sí, la clave se expone en `GET /api/v1/config/public` para que la app dibuje barras, precios y textos. **Las reglas anti-abuso nunca son públicas.**
- `Origen` indica el documento de diseño del que proviene el valor; `§5.1` marca los valores fijados aquí al resolver una discrepancia.

## 5.1 XP (`xp.*`)

| Clave | Valor inicial | Tipo | Púb. | Origen |
|---|---|---|---|---|
| `xp.lesson_completed` | `50` | int | sí | 06a |
| `xp.question_first_try` | `10` | int | sí | 06a |
| `xp.question_second_try` | `4` | int | sí | 06a |
| `xp.question_cap_per_lesson` | `60` | int | no | 06a |
| `xp.challenge_completed` | `200` | int | sí | 06a (§5.9 D1) |
| `xp.assessment_passed` | `300` | int | sí | 06a |
| `xp.assessment_bonus_90` | `100` | int | sí | 06a |
| `xp.assessment_bonus_100` | `200` | int | sí | 06a |
| `xp.module_completed` | `200` | int | sí | 06a (§5.9 D2) |
| `xp.path_completed` | `1000` | int | sí | 06a |
| `xp.review_completed` | `30` | int | sí | 06a |
| `xp.review_per_correct` | `5` | int | no | 06a |
| `xp.review_correct_cap` | `30` | int | no | 06a |
| `xp.review_max_paid_per_day` | `3` | int | no | 06a |
| `xp.first_activity_of_day` | `20` | int | sí | 06a |
| `xp.daily_goal` | `0` | int | sí | §5.9 D3 (el objetivo diario paga oro, no XP) |
| `xp.mission_daily_easy` | `40` | int | sí | 06b |
| `xp.mission_daily_medium` | `100` | int | sí | 06b |
| `xp.mission_daily_hard` | `180` | int | sí | 06b |
| `xp.mission_weekly_medium` | `300` | int | sí | 06b (fase 2) |
| `xp.mission_weekly_hard` | `600` | int | sí | 06b (fase 2) |
| `xp.repeat_multipliers` | `[1.0, 0.2, 0.0]` | list | no | 06a (regla A1) |
| `xp.low_content_multiplier` | `0.5` | decimal | no | 06a (regla A8) |
| `xp.streak_multiplier` | `{"enabled": false}` | map | no | §5.9 D4 (sin multiplicador de XP por racha) |
| `xp.daily_softcap` | `[{"limit": 1500, "mult": 0.5}, {"limit": 3000, "mult": 0.1}]` | list | no | 06a (regla A5) |
| `xp.min_time.lesson` | `{"abs_seconds": 60, "ratio": 0.25}` | map | no | 06a (regla A4) |
| `xp.min_time.challenge` | `{"abs_seconds": 90, "ratio": 0.25}` | map | no | 06a |
| `xp.min_time.assessment_per_question` | `20` | int | no | 06a |
| `xp.min_time.answer_ms` | `2000` | int | no | 06a |
| `xp.attempt_ttl_hours` | `2` | int | no | 06a |

## 5.2 Niveles (`level.*`, `knowledge.*`)

| Clave | Valor inicial | Tipo | Púb. | Origen |
|---|---|---|---|---|
| `level.base` | `80` | int | sí | 06a |
| `level.exponent` | `2.2` | decimal | sí | 06a |
| `level.max` | `50` | int | sí | 06a |
| `level.round_to` | `10` | int | sí | 06a |
| `level.rank_titles` | `{"1": "Aprendiz", "5": "Iniciado/a", "10": "Escriba", "15": "Erudito/a", "20": "Adepto/a", "25": "Guardián/a del Saber", "30": "Sabio/a", "35": "Maestro/a", "40": "Gran Maestro/a", "45": "Archimaestro/a", "50": "Leyenda del Reino"}` | map | sí | 06a |
| `knowledge.level.base` | `50` | int | sí | 06a |
| `knowledge.level.exponent` | `2.2` | decimal | sí | 06a |
| `knowledge.rank_titles` | `{"1": "Novato/a en", "5": "Practicante de", "10": "Competente en", "15": "Avanzado/a en", "20": "Experto/a en", "30": "Maestro/a de"}` | map | sí | 06a |
| `knowledge.master_title_requires_mastery` | `80` | int | sí | 06a (si no, "Veterano/a de") |
| `knowledge.master_title_fallback` | `"Veterano/a de"` | string | sí | 06a |

## 5.3 Oro (`gold.*`)

| Clave | Valor inicial | Tipo | Púb. | Origen |
|---|---|---|---|---|
| `gold.welcome` | `100` | int | sí | 06a |
| `gold.lesson_completed` | `20` | int | sí | 06a |
| `gold.challenge_completed` | `60` | int | sí | 06a |
| `gold.assessment_passed` | `100` | int | sí | 06a |
| `gold.assessment_bonus_90` | `50` | int | sí | 06a |
| `gold.assessment_bonus_100` | `100` | int | sí | 06a |
| `gold.module_completed` | `80` | int | sí | 06a |
| `gold.path_completed` | `500` | int | sí | 06a |
| `gold.review_completed` | `10` | int | sí | 06a |
| `gold.mission_daily_easy` | `10` | int | sí | 06b |
| `gold.mission_daily_medium` | `25` | int | sí | 06b |
| `gold.mission_daily_hard` | `50` | int | sí | 06b |
| `gold.mission_weekly_medium` | `100` | int | sí | 06b (fase 2) |
| `gold.mission_weekly_hard` | `200` | int | sí | 06b (fase 2) |
| `gold.level_up_bonus` | `50` | int | sí | 06a |
| `gold.rank_up_bonus` | `100` | int | sí | 06a |
| `gold.achievement_tiers` | `{"bronze": 20, "silver": 60, "gold": 150, "single": 75}` | map | sí | §5.9 D5 (valores de 06b) |
| `gold.daily_softcap` | `[{"limit": 500, "mult": 0.5}, {"limit": 1000, "mult": 0.1}]` | list | no | 06a |

## 5.4 Tienda e inventario (`shop.*`, `items.*`)

| Clave | Valor inicial | Tipo | Púb. | Origen |
|---|---|---|---|---|
| `shop.price_by_rarity` | `{"common": 150, "uncommon": 500, "rare": 1200, "epic": 3000, "legendary": 8000, "mythic": null}` | map | sí | 06a (§5.9 D6) |
| `shop.min_level_by_rarity` | `{"common": 1, "uncommon": 3, "rare": 8, "epic": 15, "legendary": 25}` | map | sí | 06a (§5.9 D7) |
| `shop.unlock_level` | `3` | int | sí | 06a |
| `shop.featured_max` | `4` | int | sí | 06c |
| `shop.sellable_rarities` | `["common", "uncommon", "rare", "epic"]` | list | sí | 06c (legendario y mítico no se venden en el MVP) |
| `shop.purchase_reversal_seconds` | `60` | int | sí | 06c ("Deshacer") |
| `shop.purchase_rate_limit_per_minute` | `10` | int | no | 06c |
| `shop.streak_protector` | `{"enabled": false, "price": 300, "max_held": 1, "cooldown_days": 7}` | map | no | 06a (fase 2) |
| `items.slots_active` | `["head", "body", "cape", "gloves", "boots", "weapon", "offhand", "accessory"]` | list | sí | 06c (§5.9 D8) |
| `items.slots_reserved` | `["pet", "mount"]` | list | sí | 06c |
| `items.rarity_colors` | `{"common": "#9AA3AE", "uncommon": "#4CAF7D", "rare": "#4A90D9", "epic": "#8E6CC8", "legendary": "#E0A33A", "mythic": "#D9534F"}` | map | sí | 06c (placeholder de UX) |
| `items.derived_templates` | `["tpl_capa_estudiante", "tpl_capa_maestro", "tpl_insignia_perfeccion"]` | list | no | 06c |
| `items.canonical_area_slugs` | `["sql", "bigquery", "data_engineering", "inteligencia_artificial", "gcp", "python", "business_intelligence"]` | list | no | 06c |
| `items.mastered_threshold` | `80` | int | sí | 06a/06c |

## 5.5 Dominio (`mastery.*`)

| Clave | Valor inicial | Tipo | Púb. | Origen |
|---|---|---|---|---|
| `mastery.weight.difficulty` | `{"easy": 1.0, "medium": 1.5, "hard": 2.0}` | map | no | 06a |
| `mastery.weight.context` | `{"lesson": 1.0, "practice": 1.0, "review": 1.0, "challenge": 1.5, "assessment": 2.0}` | map | no | 06a |
| `mastery.weight.retake` | `[1.0, 0.6, 0.3]` | list | no | 06a |
| `mastery.correctness_second_try` | `0.5` | decimal | no | 06a |
| `mastery.recency_half_life_days` | `30` | int | no | 06a |
| `mastery.prior_m` | `3` | decimal | no | 06a |
| `mastery.prior_p0` | `0.5` | decimal | no | 06a |
| `mastery.evidence_window` | `{"max_items": 40, "max_days": 180}` | map | no | 06a |
| `mastery.coverage_floor` | `0.6` | decimal | no | 06a |
| `mastery.decay` | `{"grace_days": 7, "floor": 0.6, "half_life_days": 60, "stability_factor": 1.5, "half_life_max_days": 365}` | map | no | 06a |
| `mastery.module.weight_topics` | `0.70` | decimal | no | 06a |
| `mastery.module.weight_assessment` | `0.30` | decimal | no | 06a |
| `mastery.assessment.pass_score` | `70` | int | sí | 06a |
| `mastery.assessment.distinction_score` | `90` | int | sí | 06a |
| `mastery.assessment.retake_penalty` | `{"per_attempt": 0.05, "max": 0.15}` | map | no | 06a |
| `mastery.assessment.cooldown_hours` | `[4, 24, 48]` | list | sí | 06a |
| `mastery.assessment.max_attempts_per_day` | `2` | int | sí | 06a |
| `mastery.assessment.bank_ratio` | `2.5` | decimal | no | 06a |
| `mastery.assessment.max_overlap` | `0.30` | decimal | no | 06a |
| `mastery.assessment.question_count` | `10` | int | sí | 04/06a |
| `mastery.threshold.mastered` | `80` | int | sí | 06a |
| `mastery.threshold.at_risk` | `70` | int | sí | 06a |
| `mastery.threshold.weak_practice` | `50` | int | no | 06a |
| `mastery.weak_min_evidence` | `5` | int | no | 06a |
| `mastery.review.stability_min_score` | `70` | int | no | 06a |
| `mastery.review.questions` | `{"min": 4, "max": 8}` | map | sí | 06a |
| `mastery.weakness_rules` | `{"R1_errors_in_last_10": 3, "R2_accuracy_lt": 50, "R2_min_attempts": 5, "R3_assessment_topic_lt": 60, "R4_time_multiplier": 2.0, "R4_min_questions": 2, "R5_objective_zero_of": 3}` | map | no | 04 |
| `mastery.area_mastered_requires_completed_path` | `true` | bool | sí | 06a |

## 5.6 Racha y objetivo diario (`streak.*`, `goal.*`, `time.*`)

| Clave | Valor inicial | Tipo | Púb. | Origen |
|---|---|---|---|---|
| `streak.min_daily_educational_xp` | `30` | int | sí | 06b |
| `streak.sync_tolerance_min` | `10` | int | no | 06b |
| `streak.grace_per_month` | `1` | int | sí | 06b |
| `streak.travel_skip_per_30d` | `1` | int | no | 06b |
| `streak.tz_change_min_delta_h` | `3` | int | no | 06b |
| `streak.tz_changes_max_per_24h` | `1` | int | no | 06b |
| `streak.milestones` | `[7, 14, 30, 60, 100, 365]` | list | sí | 06b (§5.9 D9) |
| `streak.repeat_milestone_every` | `50` | int | sí | 06b |
| `streak.milestone_rewards` | `{"7": {"xp": 50, "gold": 50, "item_code": "antorcha_constancia"}, "14": {"xp": 100, "gold": 100, "item_code": "botas_caminante"}, "30": {"xp": 200, "gold": 200, "item_code": "capa_llamas_persistentes"}, "60": {"xp": 300, "gold": 300, "item_code": null}, "100": {"xp": 500, "gold": 500, "item_code": "corona_fuego_eterno"}, "365": {"xp": 1000, "gold": 1000, "item_code": null}, "repeat": {"xp": 250, "gold": 250, "item_code": null}}` | map | sí | 06b + 06c (§5.9 D9) |
| `goal.default` | `{"type": "minutos", "target": 20}` | map | sí | 06b (§5.9 D10) |
| `goal.minutes.options` | `[10, 20, 30, 45]` | list | sí | 06b |
| `goal.activities.options` | `[1, 3, 5, 8]` | list | sí | 06b |
| `goal.xp.options` | `[50, 100, 200, 350]` | list | sí | 06b |
| `goal.change_effective` | `"next_day"` | string | sí | 06b (las subidas son inmediatas) |
| `goal.activity_units` | `{"lesson": 1, "questions_block": 1, "questions_per_block": 5, "review": 1, "challenge": 1, "assessment": 2}` | map | sí | 06b |
| `goal.bonus_gold_base` | `10` | int | sí | 06b |
| `goal.bonus_gold_cap_days` | `20` | int | sí | 06b |
| `goal.adapt.window_days` | `14` | int | no | 06b |
| `goal.adapt.up_rule` | `{"met_days_gte": 12, "ratio_gte": 1.5}` | map | no | 06b |
| `goal.adapt.down_rule` | `{"met_days_lte": 4, "active_days_gte": 8}` | map | no | 06b |
| `goal.adapt.cooldown_days` | `14` | int | no | 06b |
| `goal.adapt.rejected_cooldown_days` | `28` | int | no | 06b |
| `time.heartbeat_s` | `30` | int | sí | 06b |
| `time.max_tick_s` | `60` | int | no | 06b |
| `time.idle_cutoff_s` | `120` | int | no | 06b |
| `time.max_activity_multiplier` | `3` | int | no | 06b |
| `time.session_idle_timeout_min` | `10` | int | no | 01 |

## 5.7 Misiones, logros y notificaciones (`missions.*`, `achievements.*`, `notifications.*`)

| Clave | Valor inicial | Tipo | Púb. | Origen |
|---|---|---|---|---|
| `missions.daily.count` | `3` | int | sí | 06b |
| `missions.daily.tier_mix` | `["easy", "medium", "variety"]` | list | no | 06b |
| `missions.daily.no_repeat_days` | `1` | int | no | 06b |
| `missions.claim.auto_on_expiry` | `true` | bool | sí | 06b |
| `missions.path.per_path` | `3` | int | sí | 06b |
| `missions.path.max_paths_shown` | `5` | int | sí | 06b |
| `missions.weekly.enabled` | `false` | bool | sí | 06b (fase 2) |
| `missions.reroll.per_day` | `0` | int | sí | 06b (fase 2) |
| `achievements.reward.bronze` | `{"xp": 25, "gold": 20}` | map | sí | 06b |
| `achievements.reward.silver` | `{"xp": 75, "gold": 60}` | map | sí | 06b |
| `achievements.reward.gold` | `{"xp": 200, "gold": 150}` | map | sí | 06b |
| `achievements.reward.single` | `{"xp": 100, "gold": 75}` | map | sí | 06b |
| `achievements.near_unlock_pct` | `80` | int | sí | 06b |
| `notifications.reminder.default_hour` | `"19:00"` | string | sí | 06b |
| `notifications.reminder.offset_min` | `45` | int | no | 06b |
| `notifications.reminder.window` | `{"start": "08:00", "end": "21:30"}` | map | no | 06b |
| `notifications.last_call.hour` | `"21:30"` | string | sí | 06b |
| `notifications.last_call.min_streak` | `7` | int | no | 06b |
| `notifications.quiet_hours` | `{"start": "22:00", "end": "08:00"}` | map | sí | 06b |
| `notifications.max_per_day.streak_goal` | `2` | int | no | 06b |
| `notifications.max_per_day.total` | `3` | int | no | 06b |
| `notifications.reactivation_days` | `[3, 7, 30]` | list | no | 07 |

## 5.8 Contenido, ingesta e IA (`content.*`, `ingestion.*`, `ai.*`)

| Clave | Valor inicial | Tipo | Púb. | Origen |
|---|---|---|---|---|
| `content.lesson.target_minutes` | `{"min": 5, "max": 15, "default": 9}` | map | sí | 01/04 |
| `content.module.topics` | `{"min": 2, "max": 6}` | map | no | 04 |
| `content.path.modules` | `{"min": 4, "max": 10}` | map | no | 04 |
| `content.topic.lessons` | `{"min": 1, "max": 3}` | map | no | 01 |
| `content.questions_per_topic` | `5` | int | no | 04 |
| `content.open_questions_per_lesson_max` | `1` | int | no | 01 |
| `content.challenges_per_module_max` | `1` | int | no | 01 |
| `content.difficulty_distribution` | `{"easy": 0.50, "medium": 0.35, "hard": 0.15}` | map | no | 04 |
| `content.mvp_question_types` | `["multiple_choice", "true_false", "fill_blank", "matching", "ordering", "open_short", "sql_exercise"]` | list | sí | 04 |
| `content.seed_paths_target` | `5` | int | no | 01 |
| `ingestion.max_file_mb` | `25` | int | sí | 04 |
| `ingestion.max_pdf_pages` | `300` | int | sí | 04 |
| `ingestion.max_files_per_path` | `10` | int | sí | 04 |
| `ingestion.max_corpus_tokens` | `150000` | int | no | 04 |
| `ingestion.min_words_for_path` | `300` | int | sí | 04 |
| `ingestion.max_ingest_minutes` | `5` | int | no | 04 |
| `ingestion.chunk` | `{"target_tokens": 450, "max_tokens": 800, "min_tokens": 80, "overlap_pct": 0.12}` | map | no | 04 |
| `ingestion.scanned_pdf_min_chars_per_page` | `50` | int | no | 04 |
| `ingestion.purge_after_days` | `30` | int | no | 04 |
| `ai.models` | `{"path_design": "claude-opus-5", "lesson": "claude-sonnet-5", "questions": "claude-sonnet-5", "judge": "claude-haiku-4-5", "judge_escalation": "claude-sonnet-5", "narrative": "claude-haiku-4-5", "groundedness": "claude-haiku-4-5"}` | map | no | 04 |
| `ai.embeddings` | `{"provider": "voyage", "model": "voyage-3-lite", "dimensions": 512, "batch_size": 128}` | map | no | 04 |
| `ai.retrieval` | `{"vector_top_k": 20, "lexical_top_k": 20, "rrf_k": 60, "design_bonus": 0.02, "final_top_k": 10, "reexplain_top_k": 6, "min_score_ratio": 0.4}` | map | no | 04 |
| `ai.judge` | `{"correct_score": 70, "partial_score": 40, "min_confidence": 0.6, "benefit_of_doubt_score": 60, "min_words": 3}` | map | no | 04 |
| `ai.quotas_per_day` | `{"path_designs": 2, "active_paths": 3, "re_explanations": 10, "judged_answers": 50, "content_reports": 10, "upload_mb": 100, "module_regenerations": 2}` | map | sí | 04 |
| `ai.global_budget_usd_per_day` | `30` | int | no | 04 |
| `ai.budget_thresholds` | `[0.8, 1.0]` | list | no | 04 |
| `ai.sql_sandbox` | `{"engine": "duckdb", "timeout_ms": 2000, "memory_limit_mb": 256, "max_rows": 10000, "max_tables": 5, "max_rows_per_table": 200}` | map | no | 04 |
| `ai.generation_targets` | `{"skeleton_seconds": 90, "first_module_seconds": 90}` | map | no | 01/04 |

## 5.9 Discrepancias resueltas

Cuando dos documentos de diseño se contradijeron, este contrato fija el valor canónico. El motivo dominante es **quién es el dueño de la mecánica**.

| # | Discrepancia | Documentos en conflicto | **Valor canónico** | Motivo |
|---|---|---|---|---|
| D1 | XP por desafío | Brief §7 y 06b: 250 · 06a: 200 | **200** | 06a es dueño de XP y baja el desafío para que la evaluación (300) sea el hito mayor del módulo. |
| D2 | XP por módulo | Brief §7 y 06b: 150 · 06a: 200 | **200** | 06a: completar un módulo exige todas las lecciones + evaluación aprobada; debe sentirse como cierre de capítulo. |
| D3 | XP del objetivo diario | 06a: `xp.daily_objective = 100` · 06b: 0 XP, solo bono en oro | **0 XP; oro `10 + min(racha, 20)`** | 06b es dueño del objetivo diario y de la racha. Evita que el XP "meta" supere el 35 % del total. Las 3 misiones diarias (40/100/180) cubren el XP de bonificación. |
| D4 | Multiplicador de XP por racha | 06a: ×1.10 desde 7 días, ×1.20 desde 30 · 06b: sin multiplicador, la constancia se paga en oro | **Sin multiplicador** (`xp.streak_multiplier.enabled = false`) | 06b es dueño de la racha y su argumento es vinculante: dos usuarios que aprenden lo mismo deben tener niveles comparables. La clave queda para reactivarlo sin desplegar. |
| D5 | Recompensa de logros en oro | 06a: `{bronze:50, silver:100, gold:200, epic:300}` · 06b: `{bronze:20, silver:60, gold:150, single:75}` | **Valores de 06b** | 06b es dueño del catálogo de logros y define los tiers reales (no existe tier "epic"). |
| D6 | Precios por rareza | 06a: 150/500/1200/3000/8000 · 06c: 200/500/1200/2500 | **150/500/1200/3000/8000** (06a) | 06a es dueño de la economía y calibró el ratio fuentes/sumideros (≈3,8×). 06c se declaró `[PROVISIONAL-ECO]` y cede. Los precios por ítem del catálogo de 06c se reescalan a estas bandas. |
| D7 | Nivel mínimo por rareza | 06a: raro 8, épico 15 · 06c: raro 5, épico 10 | **06a** (uncommon 3, rare 8, epic 15, legendary 25) | Mismo dueño que los precios. `shop_listings.min_level` permite excepciones por ítem. |
| D8 | Número de slots | 06c: 8 activos + 2 reservados · 07: 6 en la UI del MVP | **8 activos en datos** (`items.slots_active`); la UI decide cuántos muestra | Los datos no pueden perder información que el arte ya produce. |
| D9 | Hitos de racha y sus recompensas | 06a: `[7,14,30,100]` con 50/100/300/1000 XP y 100/200/500/1500 🪙 · 06b: `[7,14,30,60,100,365]` con XP = oro (50/100/200/300/500/1000) | **06b**, con los ítems de racha de 06c | 06b es dueño de la racha; 06a lo declaró explícitamente "a reconciliar". Los ítems de los hitos 7/14/30/100 son los de 06c (`antorcha_constancia`, `botas_caminante`, `capa_llamas_persistentes`, `corona_fuego_eterno`). |
| D10 | Unidad del objetivo diario | 01: recomienda XP · 06b: minutos por defecto, 3 tipos | **06b**: tipo `minutos` por defecto, con `actividades` y `xp` disponibles | En el onboarding solo los minutos son intuitivos para alguien nuevo. |
| D11 | Definición de día activo | 01: "al menos una actividad válida" · 06b: objetivo cumplido **o** ≥ 30 XP educativo | **06b** | El "o" da un piso universal bajo y evita castigar a quien estudió pero no llegó a su meta. |
| D12 | Nombre de la evaluación | Brief §23 y 04: "Desafío del Castillo" · 01: colisiona con la actividad "desafío" | **Entidad `assessment`; nombre visible "Prueba del módulo" / "Prueba del Castillo"**. `challenge` es una actividad distinta. | Evita que usuario y equipo confundan dos mecánicas con recompensas distintas. |
| D13 | Tipos de pregunta | Brief §22: 8 tipos · 04: 7 en el MVP (caso práctico y otros lenguajes fuera) | **7 tipos** (`content.mvp_question_types`) | 04 es dueño del sistema de preguntas; `case_study` y `code_exercise` quedan en el enum como reservados y el validador los rechaza. |
| D14 | Dimensión del embedding | 04: 512 (`voyage-3-lite`) · A1: 1024 `halfvec` | **512**, `Vector(512)`, distancia coseno | Corpus acotado por ruta; menor índice y coste. `document_chunks.embedding_model` y `embedding_dim` permiten reindexar. |
| D15 | Nombres de tablas de diseño | 06a/06b/06c usan `user_day`, `user_daily_goal`, `user_topic_mastery`, `user_knowledge_progress`, `answer_evidence`, `activity_attempt`, `user_wallets`, `user_inventory`, `user_equipment`, `purchase_orders`, `achievement_def`, `item_templates`, `game_config` | **`streak_days`, `daily_goals`, `user_topic_progress`, `user_area_progress`, `question_attempts`, `study_activities`, `wallets`, `user_items`, `equipped_items`, `purchases`, `achievements`, `items.is_template`, `game_configs`** | Nombres en plural y coherentes con §3. Los nombres antiguos no existen en el código. |
| D16 | Ejemplo de perfil del brief §18 | Brief §18 (nivel 18 con 12.840 XP y 87 h) contradice la tabla de XP del propio brief §7 | **Vinculante la tabla de XP**; el ejemplo del perfil es ilustrativo | Registrado en 06a §10.14; ningún agente calibra sobre ese ejemplo. |
| D17 | Rutas semilla y propiedad del contenido | 04: "cada ruta pertenece a un único usuario" · 01: catálogo semilla compartido | **`learning_paths.user_id` nulo = Ruta del Reino compartida**; el progreso vive en `user_*_progress` | Cumple "el contenido generado es reutilizable y se separa del progreso por usuario" sin clonar contenido. |
| D18 | Precio del primer ítem | 07: ejemplo "Capucha 40 de oro" · 06a: común 150 | **150** | El ejemplo de UX es ilustrativo. Con la bolsa de bienvenida (100) más el oro del día 1, la primera compra sigue ocurriendo el día 2. |
| D19 | Bonificadores de XP por equipamiento | Brief (tentación de diseño RPG) · 01 §15.7 y 06c: no | **No existen**; `items` no tiene ningún campo de estadística | Rompería "estudiar es el juego". |
| D20 | Corrección de respuestas abiertas | A1 juez 2: Sonnet siempre · 04: Haiku con escalado a Sonnet | **Haiku 4.5 con escalado a Sonnet 5** si `confidence < 0.6` o hay desacuerdo | 04 es dueño de la capa de IA y el escalado ya cubre el riesgo de calidad. |
---

# 6. Fórmulas exactas

Todas las constantes que aparecen aquí se leen de `game_configs` (§5); los números están escritos para que el agente pueda verificar su implementación contra los ejemplos.

## 6.1 XP → nivel y nivel → XP

Curva potencial con exponente 2,2, redondeada a la decena. Dos escalas: global (`level.base = 80`) y por conocimiento (`knowledge.level.base = 50`, el 62,5 % de la global, porque el XP de conocimiento excluye el XP de bonificación).

```
xp_required(n, base, exponent=2.2) = round_to_10( base * (n - 1) ** exponent )      para n >= 2
xp_required(1, ...)                = 0

level(xp, base) = max{ n en [1, level.max] : xp_required(n, base) <= xp }

progress_pct(xp, n) = 100 * (xp - xp_required(n)) / (xp_required(n + 1) - xp_required(n))
xp_to_next(xp, n)   = xp_required(n + 1) - xp
```

`round_to_10(x)` = redondeo al múltiplo de 10 más cercano (medio hacia arriba).

Valores de control de la curva global (deben coincidir exactamente tras materializar `level_definitions`):

| Nivel | 2 | 3 | 5 | 10 | 15 | 20 | 30 | 40 | 50 |
|---|---|---|---|---|---|---|---|---|---|
| XP acumulado | 80 | 370 | 1.690 | 10.060 | 26.580 | 52.040 | 131.940 | 253.180 | 418.330 |

Curva por conocimiento: nivel 2 = 50, nivel 5 = 1.060, nivel 10 = 6.280, nivel 20 = 32.530, nivel 30 = 82.460.

**Rango y título**: el rango vigente es el mayor `k` de `level.rank_titles` con `k <= nivel`. Cambiar de rango (niveles 5, 10, 15, …) emite `RANK_UP` y paga `gold.rank_up_bonus`. El título del conocimiento usa `knowledge.rank_titles` con la misma regla, **salvo** que el título "Maestro/a de" exige además `mastery >= knowledge.master_title_requires_mastery`; si no se cumple, se muestra `knowledge.master_title_fallback`.

## 6.2 Cálculo de una transacción de XP

```
def compute_xp(event, user, config):
    base = reward_rule(event).xp_amount            # de reward_rules / game_configs

    # A4 — tiempo mínimo plausible (solo actividades)
    if event.is_activity:
        min_seconds = max(cfg.abs_seconds, cfg.ratio * activity.estimated_seconds)
        if activity.elapsed_seconds < min_seconds:
            return 0, reason="time_too_short"      # la actividad se marca completada igual

    # A1 — multiplicador de repetición por número de finalización
    m_repeat = xp.repeat_multipliers[min(completion_index, 3) - 1]     # 1.0 / 0.2 / 0.0
    if m_repeat == 0:
        return 0, reason="repeat_0"

    # A8 — contenido de material insuficiente
    m_content = xp.low_content_multiplier if lesson.is_low_content else 1.0

    # D4 — sin multiplicador por racha en el MVP
    m_streak = 1.0

    # A5 — tope diario blando sobre XP base de actividades del día local
    m_cap = 1.0
    for tramo in xp.daily_softcap:                  # [{1500, 0.5}, {3000, 0.1}]
        if streak_days.today.activity_base_xp > tramo.limit:
            m_cap = tramo.mult

    amount = round(base * m_repeat * m_content * m_streak * m_cap)
    multiplier = m_repeat * m_content * m_streak * m_cap
    return amount, multiplier, reason
```

Cada factor se persiste (`base_amount`, `multiplier`, `amount`, `reason_code`) para que "¿por qué gané 44 XP y no 50?" se responda con una consulta.

Reglas adicionales de XP por pregunta:

- Solo se paga dentro de una `study_activities` abierta (`status = in_progress`, TTL 2 h). Respuesta fuera de intento → HTTP 409.
- 1.er intento correcto: `xp.question_first_try` (10). 2.º intento correcto: `xp.question_second_try` (4). 3.º o más: 0.
- Tope por lección: `xp.question_cap_per_lesson` (60). Superado → `reason_code = "question_cap_reached"`.
- `response_ms < xp.min_time.answer_ms` (2 000) → 0 XP, `reason_code = "answer_too_fast"`, pero **la evidencia sí se registra** para dominio.
- El repaso paga `xp.review_completed + min(aciertos * xp.review_per_correct, xp.review_correct_cap)`, con un máximo de `xp.review_max_paid_per_day` repasos remunerados por día.

## 6.3 Oro

```
gold = base_gold(evento)                              # solo actividades COMPLETADAS, nunca por respuesta
si completion_index > 1: gold = 0                     # el oro no tiene regla del 20 %
aplicar gold.daily_softcap sobre el oro de actividades del día local
bono de constancia al cumplir el objetivo diario:
    gold_bonus = goal.bonus_gold_base + min(streak.current_length, goal.bonus_gold_cap_days)   # 10..30
```

Invariante del ledger: `wallets.balance = SUM(credits) - SUM(debits)` y `balance >= 0` en toda fila (`balance_after`). La compra se ejecuta en **una sola transacción SQL** con `SELECT … FOR UPDATE` sobre la billetera:

```
BEGIN
  wallet := SELECT * FROM wallets WHERE user_id = ? AND currency = 'gold' FOR UPDATE
  listing := SELECT * FROM shop_listings WHERE id = ? AND is_active AND now() dentro de la ventana
  validar: precio del servidor == expected_price, nivel >= listing.min_level,
           requisitos del ítem cumplidos, el usuario no lo posee, wallet.balance >= price
  INSERT gold_transactions (direction='debit', sink='purchase', amount=price,
                            balance_after = wallet.balance - price)
  UPDATE wallets SET balance = balance - price, lifetime_spent = lifetime_spent + price,
                     version = version + 1
  INSERT user_items (origin='shop', source_ref={purchase_id})
  INSERT purchases (status='completed')
  INSERT domain_events (ITEM_ACQUIRED, GOLD_SPENT)
COMMIT
```

## 6.4 Dominio por tema (`M_t`)

Precisión ponderada con prior bayesiano, sobre las evidencias de `question_attempts` del tema (ventana `mastery.evidence_window`: últimas 40 evidencias o 180 días, lo que dé más cobertura):

```
w_dif(d)      = {easy: 1.0, medium: 1.5, hard: 2.0}[d]
w_ctx(ctx)    = {lesson: 1.0, practice: 1.0, review: 1.0, challenge: 1.5, assessment: 2.0}[ctx]
w_rec(edad)   = 0.5 ** (edad_dias / mastery.recency_half_life_days)      # vida media 30 días
w_ret(k)      = mastery.weight.retake[min(k, 3) - 1]                     # 1.0 / 0.6 / 0.3
w_i           = w_dif(d_i) * w_ctx(ctx_i) * w_rec(edad_i) * w_ret(attempt_no_i)

c_i           = 1.0 si acierta al 1.er intento
              = 0.5 si acierta al 2.º intento
              = 0.0 si falla o acierta al 3.er intento o más
                (el crédito parcial "casi" cuenta 0 para dominio; sí puede pagar XP reducido)

P_t = ( Σ w_i * c_i + m * p0 ) / ( Σ w_i + m )        con m = 3 , p0 = 0.5

C_t  = lecciones_completadas_del_tema / lecciones_del_tema        ∈ [0, 1]
g(C) = mastery.coverage_floor + (1 - mastery.coverage_floor) * C  = 0.6 + 0.4 * C

M_t_raw = P_t * g(C_t)
```

`edad_dias` se mide respecto a **la evidencia más reciente del tema**, no respecto a hoy.

## 6.5 Decaimiento (curva de olvido) y recuperación

```
Δ    = días desde last_evidence_at
s    = stability_s (repasos o evaluaciones exitosas posteriores al primer dominio)
h    = min( mastery.decay.half_life_days * (mastery.decay.stability_factor ** s),
            mastery.decay.half_life_max_days )              # min(60 * 1.5^s, 365)

D(Δ) = 1                                                    si Δ <= 7   (grace_days)
D(Δ) = 0.6 + 0.4 * 0.5 ** ((Δ - 7) / h)                     si Δ  > 7

M_t = M_t_raw * D(Δ)
```

El decaimiento **se aplica en lectura**: `mastery` materializada se refresca con un job diario, pero cualquier consulta puede recalcularla al vuelo y obtener el mismo número. Un repaso con `P_repaso >= mastery.review.stability_min_score` (70) incrementa `s` en 1 y resetea `Δ` a 0.

Control: un tema al 90 % cruza el umbral de 80 % a los **36 días** con `s = 0`, **50 días** con `s = 1` y **71 días** con `s = 2`.

## 6.6 Dominio por módulo (`M_mod`)

```
E_mod = max_k ( score_k - mastery.assessment.retake_penalty.per_attempt * (k - 1) )
        con penalización máxima 0.15 ; E_mod = 0 si no hay evaluación rendida

M_mod = mastery.module.weight_topics      * promedio_ponderado_t( M_t , peso = lecciones_del_tema )
      + mastery.module.weight_assessment  * E_mod
      = 0.70 * temas + 0.30 * E_mod

módulo dominado  ⇔  M_mod >= 0.80  Y  existe algún intento con score_k >= 0.70
```

Sin evaluación rendida `M_mod <= 0.70`: **es imposible dominar un módulo sin evaluación**, sin reglas especiales.

## 6.7 Dominio por conocimiento (`M_area`)

```
M_area = Σ_mod ( lecciones_del_modulo * M_mod ) / Σ_mod lecciones_del_modulo
         sobre TODOS los módulos de TODAS las rutas activas (no archivadas) del conocimiento

conocimiento dominado ⇔ M_area >= 0.80
                        Y existe >= 1 ruta del conocimiento completada con todas sus evaluaciones aprobadas
```

Los módulos no iniciados pesan con `M_mod = 0`: el dominio de SQL es "cuánto del SQL que te propusiste aprender dominas". Al añadir una ruta nueva el porcentaje baja; la UI lo comunica como "tu horizonte de SQL se amplió", nunca como pérdida.

**Permanencia**: un ítem otorgado por dominio ≥ 80 % **no se revoca** si el dominio decae.

Explicabilidad obligatoria (`GET /api/v1/knowledge-areas/{id}`): la respuesta incluye `{"practice_pct", "assessment_pct", "modules_mastered", "modules_total", "weak_topics"}` para renderizar "63 % porque aprobaste 5 de 8 módulos con 78 % promedio y tienes 2 temas débiles".

## 6.8 Estados de dominio

| Estado (`KnowledgeAreaStatus`) | Condición |
|---|---|
| `no_evidence` | 0 evidencias y 0 lecciones completadas |
| `in_progress` | `0 < M < 80` y nunca dominado |
| `mastered` | `M >= 80` (+ evaluación aprobada en módulo; + ruta completa en conocimiento) |
| `at_risk` | Fue dominado y ahora `70 <= M < 80` |
| `weakened` | Fue dominado y ahora `M < 70` |
| `is_weak = true` (bandera aparte) | `P_t < 50` con al menos 5 evidencias → dispara aprendizaje adaptativo |

## 6.9 Reglas anti-abuso (todas en servidor, obligatorias)

| # | Regla | Implementación | `reason_code` |
|---|---|---|---|
| A1 | **XP completo solo la primera vez** | `user_lesson_progress.completion_count` → multiplicadores `[1.0, 0.2, 0.0]`. El oro no tiene 20 %: la 2.ª vez ya paga 0. | `first_completion`, `repeat_20`, `repeat_0` |
| A2 | **XP de pregunta solo dentro de una actividad abierta** | Toda respuesta referencia `study_activities.id` con `status = in_progress` (TTL `xp.attempt_ttl_hours`). Respuesta fuera de intento o sobre una pregunta ajena a la actividad → **409**. Cada pregunta se puntúa una sola vez por intento. | `question_first_try`, `question_second_try`, `question_no_attempt` |
| A3 | **Tope de XP por preguntas por lección** | `xp.question_cap_per_lesson = 60`. | `question_cap_reached` |
| A4 | **Tiempo mínimo plausible** | `elapsed = completed_at - started_at` con **relojes del servidor**. Lección: `max(60 s, 0.25 × estimated_seconds)`. Desafío: `max(90 s, 0.25 × est.)`. Evaluación: `20 s × n_preguntas`. Respuesta individual `< 2 000 ms` → sin XP. La actividad se marca completada (no se bloquea el avance) pero no paga ni cuenta como primera finalización pagada. | `time_too_short`, `answer_too_fast` |
| A5 | **Topes diarios blandos (rendimiento decreciente)** | Sobre el XP **base de actividades** del día local (excluye misiones, hitos y logros): ≤ 1.500 → ×1.0; 1.500–3.000 → ×0.5; > 3.000 → ×0.1. Oro: > 500 → ×0.5; > 1.000 → ×0.1. | `daily_softcap_50`, `daily_softcap_10` |
| A6 | **Idempotencia** | `Idempotency-Key` obligatoria en todo POST que otorgue recompensas; `UNIQUE (user_id, idempotency_key)` en los ledgers y en los intentos. Un reintento devuelve el **mismo** `RewardsReceipt`, no uno nuevo. | — |
| A7 | **Finalización verificable** | `LESSON_COMPLETED` solo si todas las preguntas del intento tienen respuesta registrada. `MODULE_COMPLETED` solo si todas las lecciones están completas **y** la evaluación aprobada. `PATH_COMPLETED` solo si todos los módulos están completos. Son **derivados por el servidor**; el cliente no puede emitirlos. | — |
| A8 | **Contenido trivial** | Lecciones con `is_low_content = true` pagan el 50 % de XP y oro. | `low_content_50` |
| A9 | **Ajustes administrativos auditables** | Toda corrección es una transacción con `source = adjustment`, `created_by` y motivo; nunca un `UPDATE` del contador. | `admin_adjustment` |

Además: `counts_for_progress = false` (repetición de una pregunta ya acertada hoy, relectura sin responder, respuesta demasiado rápida) excluye el hecho del objetivo diario, la racha, las misiones y los logros.

## 6.10 Racha

**Día activo.** Una fecha local `D` es activa si y solo si:

```
streak_days[D].goal_met_at IS NOT NULL
OR streak_days[D].educational_xp >= streak.min_daily_educational_xp      # 30
```

Nunca cuentan: abrir la app, ver el mapa, personalizar el avatar, comprar, reclamar misiones, ni el XP de bonificación.

**Actualización (idempotente, con bloqueo de fila sobre `streaks`).**

```
def activar_dia(user, hoy):                     # hoy = fecha local
    s = streaks[user]
    if s.last_active_date == hoy:      return                      # idempotente
    if s.last_active_date == hoy - 1:  s.current_length += 1; change = "extended"
    elif s.last_active_date == hoy - 2:
        perdido = hoy - 1
        if viaje_hacia_el_este(hoy - 2, hoy) and ajuste_viaje_disponible(s):
            streak_days[perdido].day_status = "travel"
            s.travel_skip_used_on = perdido; s.current_length += 1; change = "travel_skip"
        elif gracia_disponible(s, mes(perdido)):
            streak_days[perdido].day_status = "grace"
            s.grace_used_for_month = mes(perdido); s.current_length += 1; change = "grace_used"
        else:
            cerrar_racha(s); s.current_length = 1; change = "started"
    else:
        if s.current_length > 0: cerrar_racha(s)
        s.current_length = 1; change = "started"

    s.last_active_date = hoy
    s.total_active_days += 1
    s.best_length = max(s.best_length, s.current_length)
    emitir STREAK_UPDATED
    if s.current_length in streak.milestones
       or (s.current_length > 100 and s.current_length % streak.repeat_milestone_every == 0):
        emitir STREAK_MILESTONE_REACHED(first_time = nunca_alcanzado_antes)
```

**Estado visible** (solo lectura, no muta): `ACTIVA_HOY` si `last_active_date == hoy`; `PENDIENTE_HOY` si `== hoy - 1`; `PROTEGIDA_POR_GRACIA` si `== hoy - 2` y hay gracia disponible; `ROTA` en cualquier otro caso.

**Reglas fijas.**

- Corte a **medianoche local** del usuario (`users.timezone`, IANA).
- `occurred_at` = marca del cliente si `|cliente − servidor| <= streak.sync_tolerance_min` (10 min); si no, marca del servidor.
- **1 día de gracia por mes calendario**, automático y gratuito, asociado al mes del **día perdido**, no al del regreso.
- **1 ajuste por viaje cada 30 días**, solo si hubo un cambio de zona horaria de ≥ 3 h.
- Máximo 1 cambio efectivo de zona horaria cada 24 h.
- `best_length` **nunca** disminuye; los ítems de racha usan `best` (perder la racha no quita el mérito).
- Los ítems de hito se otorgan **una sola vez** por usuario aunque el hito se repita; XP y oro sí se repiten.

## 6.11 Objetivo diario

```
progreso(D) = { minutos:     streak_days[D].effective_seconds / 60
                actividades: streak_days[D].activity_units
                xp:          streak_days[D].educational_xp }[goal_type_snapshot]

cumplido(D) ⇔ progreso(D) >= goal_target_snapshot        → DAILY_GOAL_MET (una vez por fecha local)
recompensa  = goal.bonus_gold_base + min(streak.current_length, goal.bonus_gold_cap_days)   🪙, 0 XP
```

Unidades de actividad (`goal.activity_units`): lección 1 · cada 5 preguntas de práctica 1 · repaso 1 · desafío 1 · evaluación 2.

Tiempo efectivo: latido cada 30 s mientras hay una actividad educativa en primer plano y hubo interacción en los últimos 120 s; el servidor acepta ≤ 60 s por latido, descarta latidos fuera de una actividad abierta y limita el total por actividad a 3× su duración estimada.

Cambio de objetivo: las **subidas** rigen de inmediato; las **bajadas** al día siguiente (`goal.change_effective = next_day`). El día en curso conserva `goal_type_snapshot` / `goal_target_snapshot`.

Recomendación adaptativa (cada lunes, ventana de 14 días, nunca cambia la meta sola): subir si cumplió ≥ 12/14 días y el logro medio ≥ 150 % de la meta; bajar si cumplió ≤ 4/14 días con ≥ 8 días activos; si hay < 4 días activos, no se recomienda un número sino el tipo `actividades = 1`.

## 6.12 Recuperación híbrida (RAG)

```
1. Vectorial:  ORDER BY embedding <=> query_embedding  (cosine), filtro por knowledge_base_id, top 20
2. Léxica:     ts_rank_cd(search_vector, query) con configuración 'spanish' y 'simple', top 20
3. Fusión RRF: score(f) = Σ_listas 1 / (60 + rango_en_la_lista)
4. Refuerzo:   + ai.retrieval.design_bonus (0.02) a los fragmentos asignados al tema en la Fase A
5. Selección:  top 10 para lección y pool de preguntas (mismo prefijo cacheado); top 6 para re-explicación
               descartando los que puntúen < 40 % del mejor
6. Vecindad:   si un fragmento es 'code' o 'table', se adjunta el anterior si no está ya incluido
```

## 6.13 Evaluación de requisitos de desbloqueo

```
desbloqueado(item, user) ⇔ ∃ group_index g : ∀ fila r de item_requirements con group_index = g : cumple(r, user)

cumple(r, u) según r.requirement_type:
  path_completed        → ∃ ruta del área con user_path_progress.status = ProgressState.COMPLETED
  mastery_gte           → user_area_progress.mastery >= r.target_value
  areas_mastered_gte    → count(user_area_progress.status = KnowledgeAreaStatus.MASTERED) >= r.target_count
  assessment_score_gte  → count(assessment_attempts.score >= r.target_value del área) >= coalesce(r.target_count, 1)
  streak_gte            → (streaks.current_length | streaks.best_length según r.streak_kind) >= r.target_count
  level_gte             → characters.level >= r.target_count
  achievement_unlocked  → ∃ user_achievements del logro r.achievement_code
  lessons_completed_gte → count(user_lesson_progress completadas [del área]) >= r.target_count
  within_window         → now() entre r.window_from y r.window_to
```

Reglas del evaluador (una sola implementación para tres usos: otorgar, gatear compra y **explicar**):

- Se dispara por evento, filtrando candidatos por `items.requirement_facts` (`PATH_COMPLETED` → `path`; `MASTERY_UPDATED`/`AREA_MASTERED` → `mastery`; `ASSESSMENT_COMPLETED` → `assessment`; `STREAK_UPDATED` → `streak`; `LEVEL_UP` → `level`; `ACHIEVEMENT_UNLOCKED` → `achievement`; `LESSON_COMPLETED` → `lessons`).
- Otorgar es `INSERT … ON CONFLICT DO NOTHING` sobre `user_items`; un job nocturno reevalúa a los usuarios activos de los últimos 7 días y corrige eventos perdidos (permite añadir ítems al catálogo con efecto retroactivo).
- `auto_grant = true` otorga; `auto_grant = false` solo habilita la compra.
- **Regla de integridad educativa**: un ítem con `origin = knowledge` debe tener al menos una condición de desempeño (`path_completed`, `mastery_gte`, `areas_mastered_gte`, `assessment_score_gte`). El validador de catálogo rechaza lo contrario. Tiempo de estudio y número de lecciones no bastan.
- Modo `explain`: por cada condición devuelve `{met, current, target, label, cta}` usando `label_template`.
---

# 7. Mapa de rutas de la API v1

Prefijo obligatorio: **`/api/v1`**. Todas las rutas son `snake_case` en los campos JSON y `kebab-case` en los segmentos de ruta. Autenticación: `Bearer <access_token>` salvo donde se indique **No**.

Convenciones de la columna "Respuesta": los nombres en `PascalCase` son esquemas Pydantic v2 definidos en `app/schemas/`; `Page<X>` es el sobre de paginación de §8.2; `RewardsReceipt` es el objeto canónico de §7.10.

## 7.1 Autenticación y cuenta (`identity`)

| Método | Ruta | Auth | Descripción | Respuesta |
|---|---|---|---|---|
| POST | `/api/v1/auth/register` | No | Crea la cuenta con correo y contraseña. No pide nombre (se define en el personaje). | `AuthTokens` `{access_token, refresh_token, token_type, expires_in, user: UserOut}` |
| POST | `/api/v1/auth/login` | No | Inicia sesión. | `AuthTokens` |
| POST | `/api/v1/auth/refresh` | No (usa refresh) | Rota el refresh token y emite un nuevo par. Detecta reuso y revoca la cadena. | `AuthTokens` |
| POST | `/api/v1/auth/logout` | Sí | Revoca el refresh token recibido. | `204` |
| GET | `/api/v1/auth/me` | Sí | Usuario, personaje y estado de onboarding. | `MeOut` `{user, character, has_character, has_path, settings}` |
| POST | `/api/v1/auth/password` | Sí | Cambia la contraseña (revoca todos los refresh tokens). | `204` |
| DELETE | `/api/v1/auth/account` | Sí | Borrado lógico de la cuenta y de sus documentos. | `204` |
| GET | `/api/v1/settings` | Sí | Preferencias del usuario (P21). | `SettingsOut` |
| PUT | `/api/v1/settings` | Sí | Actualiza tema, notificaciones, idioma, zona horaria. | `SettingsOut` |

## 7.2 Personaje, avatar e inventario (`identity` + `economy`)

| Método | Ruta | Auth | Descripción | Respuesta |
|---|---|---|---|---|
| POST | `/api/v1/characters` | Sí | Crea el personaje (P03): nombre, arquetipo y rasgos. Otorga la bolsa de bienvenida y el kit inicial. | `CharacterOut` + `RewardsReceipt` en `rewards` |
| GET | `/api/v1/characters/me` | Sí | Personaje con nivel, XP, rango y contadores. | `CharacterOut` |
| PATCH | `/api/v1/characters/me` | Sí | Renombra el personaje o cambia el arquetipo (gratis en el MVP). | `CharacterOut` |
| GET | `/api/v1/avatar` | Sí | Rasgos, arquetipo, equipo y **manifiesto de capas ya resuelto y ordenado por z**. Cada capa: `{slot, item_code, key, z, src, x, y, w, h, tint}`, donde `key` es el nombre de la capa en la pila de dibujado (06c §2.3) —no el código del ítem—, `src` el archivo de la capa dentro del juego de piezas de una familia (`<code>_<capa>.webp`, plano y sin versión; la carpeta de la familia la antepone el cliente, que es quien sabe qué figura eligió el aprendiz) y `x/y/w/h` su rectángulo dentro del lienzo maestro de 1024×1024. | `AvatarOut` `{traits, archetype, equipment, layers[], etag}` |
| PUT | `/api/v1/avatar/traits` | Sí | Cambia piel, rostro, orejas, cabello, color y forma de tratamiento. | `AvatarOut` |
| PUT | `/api/v1/avatar/equipment` | Sí | Mapa atómico `{"weapon": "<user_item_id>", "cape": null}`; valida propiedad, slot y compatibilidad. | `AvatarOut` |
| GET | `/api/v1/inventory` | Sí | Poseídos + bloqueados visibles, con progreso de requisitos (P16). Filtros `slot`, `rarity`, `state`, `origin`. | `Page<InventoryItemOut>` con `{item, owned, is_new, equipped, requirements[]}` |
| GET | `/api/v1/items/{item_id}` | Sí | Ficha del ítem: lore, rareza, origen, manifiesto y `explain` de requisitos. | `ItemDetailOut` |
| POST | `/api/v1/items/{item_id}/preview` | Sí | Registra `ITEM_PREVIEWED` (analítica de "Probar"). | `204` |

## 7.3 Tienda (`economy`)

| Método | Ruta | Auth | Descripción | Respuesta |
|---|---|---|---|---|
| GET | `/api/v1/shop` | Sí | Catálogo activo, destacados, saldo y sección "Se ganan aprendiendo" (P15). | `ShopOut` `{balance, featured[], listings[], knowledge_items[]}` |
| POST | `/api/v1/shop/purchase` | Sí (**Idempotency-Key**) | Compra atómica: `{listing_id, expected_price}`. | `PurchaseOut` `{purchase, user_item, balance_after, avatar_layers}` |
| POST | `/api/v1/shop/purchases/{purchase_id}/reverse` | Sí | "Deshacer" dentro de `shop.purchase_reversal_seconds`. | `PurchaseOut` |
| GET | `/api/v1/wallet` | Sí | Saldo y últimos movimientos. | `WalletOut` `{balance, lifetime_earned, lifetime_spent, transactions: Page<GoldTransactionOut>}` |

## 7.4 Conocimientos y mundo (`content` + `progress`)

| Método | Ruta | Auth | Descripción | Respuesta |
|---|---|---|---|---|
| GET | `/api/v1/knowledge-areas` | Sí | Catálogo canónico + áreas del usuario, con su dominio si existe. | `Page<KnowledgeAreaOut>` |
| GET | `/api/v1/knowledge-areas/{area_id}` | Sí | Detalle del conocimiento: nivel, XP, dominio **con su explicación**, tiempo, módulos y temas débiles. | `KnowledgeAreaDetailOut` |
| GET | `/api/v1/me/knowledge` | Sí | Perfil de conocimiento del usuario (lista con nivel, XP, dominio, tiempo, estado). | `Page<UserKnowledgeOut>` |
| GET | `/api/v1/territories` | Sí | Mapa simplificado (P22): territorios con estado y zonas desbloqueadas. | `Page<TerritoryOut>` |

## 7.5 Rutas de aprendizaje y material (`content` + `ingestion` + `ai`)

| Método | Ruta | Auth | Descripción | Respuesta |
|---|---|---|---|---|
| GET | `/api/v1/paths` | Sí | Mis rutas + Rutas del Reino (P22). Filtro `scope=mine|seed|all`. | `Page<PathSummaryOut>` |
| POST | `/api/v1/paths` | Sí (**Idempotency-Key**) | Crea la ruta (P05): `{goal_text, declared_level, document_ids[], source_mode, knowledge_area_hint}`. Encola la Fase A. | `PathCreatedOut` `{path, job: JobOut}` |
| GET | `/api/v1/paths/{path_id}` | Sí | Mapa de la ruta (P07): módulos, temas, lecciones y estado de bloqueo por usuario. Cada módulo lleva además su desafío en `assessment` —`null` mientras el módulo no tenga evaluación creada—: `{assessment_id, module_id, title, question_count, pass_score, max_attempts_per_day, content_status, attempts_used, best_score, passed, can_start, cooldown_until}`. `can_start` mira **solo** las reglas del desafío —enfriamiento y tope diario (§5.5, §8.6)—; que el módulo esté bloqueado lo dice `status` del nodo, y mezclarlos dejaría al mapa sin poder distinguir «bloqueado» de «hoy ya no te quedan intentos». | `PathDetailOut` |
| POST | `/api/v1/paths/{path_id}/confirm` | Sí | Confirma el esquema revisado: reordenar, renombrar, eliminar temas y fijar `coverage_policy`. Encola el módulo 1. | `PathDetailOut` |
| PATCH | `/api/v1/paths/{path_id}` | Sí | Renombra o archiva. | `PathDetailOut` |
| DELETE | `/api/v1/paths/{path_id}` | Sí | Elimina la ruta del usuario y cancela sus misiones de ruta. | `204` |
| POST | `/api/v1/paths/{path_id}/adopt` | Sí | Adopta una Ruta del Reino: crea el progreso del usuario sin duplicar contenido. | `PathDetailOut` |
| GET | `/api/v1/paths/{path_id}/generation` | Sí | Estado agregado de la generación (P06): etapas, porcentaje y si el módulo 1 ya está listo. | `GenerationStatusOut` `{status, stage, progress_pct, first_module_ready, eta_seconds, jobs[]}` |
| GET | `/api/v1/paths/{path_id}/sources` | Sí | Documentos que respaldan la ruta. | `Page<DocumentOut>` |
| POST | `/api/v1/documents` | Sí (multipart) | Sube un archivo (PDF, DOCX, MD, TXT) y encola la ingesta. | `DocumentOut` + `job` |
| POST | `/api/v1/documents/paste` | Sí | Pega texto como material (`{title, text}`). | `DocumentOut` + `job` |
| GET | `/api/v1/documents` | Sí | Mis documentos (P21 → Datos). | `Page<DocumentOut>` |
| GET | `/api/v1/documents/{document_id}` | Sí | Detalle y estado de procesamiento. | `DocumentOut` |
| DELETE | `/api/v1/documents/{document_id}` | Sí | Borrado lógico + purga diferida. | `204` |
| GET | `/api/v1/jobs/{job_id}` | Sí | Estado de un trabajo (polling cada 2–3 s). | `JobOut` `{id, job_type, status, progress_pct, progress_label, error}` |
| GET | `/api/v1/chunks/{chunk_id}` | Sí | Fragmento original para la hoja "Fuente" (documento, páginas, texto). | `ChunkOut` |

## 7.6 Lección, respuestas y recompensas (`progress` + `ai`)

| Método | Ruta | Auth | Descripción | Respuesta |
|---|---|---|---|---|
| GET | `/api/v1/lessons/{lesson_id}` | Sí | Lección completa con bloques y procedencia. **Nunca** incluye `answer_key`. | `LessonOut` `{lesson, blocks[], provenance[], questions_preview[]}` |
| POST | `/api/v1/lessons/{lesson_id}/start` | Sí (**Idempotency-Key**) | Abre la actividad (`study_activities`) y devuelve las preguntas sin claves. | `ActivityOut` `{activity_id, questions[], expires_at}` |
| POST | `/api/v1/activities/{activity_id}/answers` | Sí (**Idempotency-Key**) | Envía una respuesta; corrige (determinista, sandbox o juez) y devuelve retroalimentación. | `AnswerResultOut` `{result, is_correct, partial_score, xp_awarded, explanation, correct_answer, provenance, evaluation_method}` |
| POST | `/api/v1/activities/{activity_id}/heartbeat` | Sí | Latido de tiempo efectivo (`{seconds}` ≤ 60). | `{"active_seconds": 320}` |
| POST | `/api/v1/activities/{activity_id}/complete` | Sí (**Idempotency-Key**) | Cierra la actividad, dispara el motor de gamificación y devuelve las recompensas (P10). | **`RewardsReceipt`** |
| POST | `/api/v1/activities/{activity_id}/abandon` | Sí | Marca la actividad como abandonada (sin recompensa). | `204` |
| GET | `/api/v1/reviews/recommended` | Sí | Repasos recomendados (temas en riesgo o débiles) con duración estimada. | `Page<ReviewSuggestionOut>` |
| POST | `/api/v1/reviews/start` | Sí (**Idempotency-Key**) | Abre un repaso de 4–8 preguntas sobre `{topic_id}`. | `ActivityOut` |
| POST | `/api/v1/topics/{topic_id}/explain` | Sí | Re-explicación alternativa generada por IA (enfoque rotativo, con citas). | `ExplanationOut` `{approach, body, citations[]}` |
| POST | `/api/v1/content/report` | Sí | Reporta un bloque o pregunta (`{content_type, content_id, reason, comment}`). | `204` |

## 7.7 Evaluación de módulo (`progress`)

| Método | Ruta | Auth | Descripción | Respuesta |
|---|---|---|---|---|
| GET | `/api/v1/modules/{module_id}/assessment` | Sí | Pantalla de entrada (P11): reglas, recompensa, intentos usados y enfriamiento. | `AssessmentInfoOut` `{assessment, attempts_used, cooldown_until, can_start, reward_preview}` |
| POST | `/api/v1/assessments/{assessment_id}/start` | Sí (**Idempotency-Key**) | Crea el intento y muestrea el banco (solapamiento ≤ 30 %). | `AssessmentAttemptOut` `{attempt_id, questions[], question_count}` |
| POST | `/api/v1/assessment-attempts/{attempt_id}/answers` | Sí (**Idempotency-Key**) | Registra una respuesta (feedback mínimo: correcto/incorrecto, sin explicación). | `{"recorded": true, "index": 3, "total": 10}` |
| POST | `/api/v1/assessment-attempts/{attempt_id}/submit` | Sí (**Idempotency-Key**) | Cierra el intento, calcula puntaje y dominio (P12). | **`RewardsReceipt`** con `assessment_result` `{score_pct, outcome, per_topic[], weak_topics[], cooldown_until, review_suggestions[]}` |
| GET | `/api/v1/assessment-attempts/{attempt_id}` | Sí | Revisión de respuestas con explicación y fuente. | `AssessmentReviewOut` |

## 7.8 Panel principal, perfil y estadísticas (`gamification` + `progress`)

| Método | Ruta | Auth | Descripción | Respuesta |
|---|---|---|---|---|
| GET | `/api/v1/dashboard` | Sí | Todo lo que P04 necesita en una sola llamada. | `DashboardOut` `{greeting_key, character{level, rank_title, xp_total, xp_to_next, progress_pct}, gold_balance, streak{current, best, status, day_status}, daily_goal{type, target, progress, met, bonus_gold}, continue_action{type, path_id, module_id, lesson_id, topic_id, title, breadcrumb, reward_preview}, knowledge_summary[], missions_summary[], week_stats{active_seconds, lessons, achievements}, generation_banner, unread_notifications}` |
| GET | `/api/v1/profile` | Sí | Perfil de videojuego (P17). | `ProfileOut` `{character, avatar_layers, stats{xp_total, streak_current, study_seconds, areas_mastered, achievements_unlocked, items_owned}, knowledge[], last_7_days[]}` |
| GET | `/api/v1/profile/stats` | Sí | Estadísticas ampliadas con rango de fechas (`from`, `to`). | `StatsOut` `{daily[], totals, accuracy_pct, lessons, assessments}` |
| GET | `/api/v1/streak` | Sí | Racha actual, mejor, estado, próximo hito y su recompensa (P18). | `StreakOut` `{current, best, status, total_active_days, grace_available, next_milestone{days, remaining, reward}}` |
| GET | `/api/v1/streak/calendar` | Sí | Calendario mensual (`month=2026-09`). | `StreakCalendarOut` `{month, days[{date, day_status, goal_met, educational_xp, minutes, activities}], active_days, best_length}` |
| GET | `/api/v1/daily-goal` | Sí | Objetivo vigente, progreso de hoy y recomendación pendiente. | `DailyGoalOut` |
| PUT | `/api/v1/daily-goal` | Sí | Cambia tipo y meta (subidas inmediatas, bajadas al día siguiente). | `DailyGoalOut` |
| POST | `/api/v1/daily-goal/recommendation/accept` | Sí | Acepta la recomendación adaptativa. | `DailyGoalOut` |
| POST | `/api/v1/daily-goal/recommendation/dismiss` | Sí | La rechaza (no se repite en 28 días). | `204` |

## 7.9 Misiones, logros y notificaciones (`gamification`)

| Método | Ruta | Auth | Descripción | Respuesta |
|---|---|---|---|---|
| GET | `/api/v1/missions` | Sí | Misiones diarias y especiales (P19); genera las del día de forma perezosa y determinista. | `MissionsOut` `{daily[], special[], weekly[], resets_in_seconds}` |
| POST | `/api/v1/missions/{user_mission_id}/claim` | Sí (**Idempotency-Key**) | Reclama la recompensa de una misión completada. | **`RewardsReceipt`** |
| GET | `/api/v1/achievements` | Sí | Sala de trofeos (P20) con progreso por nivel y filtros (`state=all|unlocked|in_progress`). | `Page<AchievementOut>` `{code, name, category, visibility, highest_tier, tiers[], progress_pct, unlocked_at}` |
| GET | `/api/v1/notifications` | Sí | Bandeja in-app: solo lo ya entregado (`SENT`, `READ`), de lo más reciente a lo más antiguo. Pagina con `limit` y `cursor` sobre `sent_at`. | `Page<NotificationOut>` `{id, notification_type, channel, status, title, body, deep_link, payload, scheduled_for, sent_at, read_at, dismissed_at, created_at}` |
| POST | `/api/v1/notifications/{notification_id}/read` | Sí | Marca como leída. | `204` |
| POST | `/api/v1/notifications/read-all` | Sí | Marca todas como leídas. | `204` |
| POST | `/api/v1/devices/push-token` | Sí | Registra o actualiza el token de push. | `204` |
| GET | `/api/v1/config/public` | No | Claves de `game_configs` con `is_public = true` + tabla de niveles + colores de rareza. | `PublicConfigOut` `{config_version, values{}, levels[], knowledge_levels[]}` |
| GET | `/api/v1/health` | No | Salud del servicio y de la base de datos. | `{"status": "ok", "database": "ok", "version": "1.0.0"}` |

## 7.10 `RewardsReceipt` — objeto canónico de recompensas

Lo devuelven **todas** las acciones que otorgan recompensas: `POST /characters`, `.../activities/{id}/complete`, `.../assessment-attempts/{id}/submit`, `.../missions/{id}/claim`. Es lo **único** que el cliente usa para animar: la app nunca calcula XP, oro, nivel ni dominio.

```json
{
  "receipt_id": "3f2a…",
  "event_type": "LESSON_COMPLETED",
  "occurred_at": "2026-09-10T02:58:41Z",
  "config_version": 17,
  "xp": {
    "amount": 80,
    "base_amount": 50,
    "activity_xp": 50,
    "question_xp": 30,
    "multiplier": 1.0,
    "reason_code": "first_completion",
    "is_educational": true,
    "total_after": 12890
  },
  "gold": { "amount": 20, "balance_after": 1245, "reason_code": "first_completion" },
  "level": {
    "before": 6, "after": 7, "leveled_up": true,
    "rank_title_before": "Iniciado/a", "rank_title_after": "Iniciado/a", "rank_changed": false,
    "xp_to_next": 1360, "progress_pct": 4.2, "gold_bonus": 50,
    "unlocked_shop_rarities": []
  },
  "knowledge": {
    "knowledge_area_id": "…", "name": "SQL",
    "xp_after": 9861, "level_before": 11, "level_after": 12, "rank_title_after": "Competente en",
    "mastery_before": 44.00, "mastery_after": 47.00, "status": "in_progress"
  },
  "mastery_deltas": [
    { "scope": "topic", "id": "…", "name": "JOINs", "before": 63.00, "after": 71.00, "status": "in_progress" },
    { "scope": "module", "id": "…", "name": "Consultas relacionales", "before": 70.10, "after": 74.50, "status": "in_progress" }
  ],
  "streak": {
    "current": 8, "best": 12, "change": "extended", "day_status": "active",
    "is_first_activity_of_day": true,
    "milestone": null
  },
  "daily_goal": {
    "type": "minutos", "target": 20, "progress": 22, "met": true, "just_met": true, "bonus_gold": 18
  },
  "missions": [
    { "user_mission_id": "…", "template_code": "D01", "title": "Completa 2 lecciones",
      "progress": 2, "target": 2, "status": "completed", "auto_claimed": false,
      "reward": { "xp": 100, "gold": 25 } }
  ],
  "achievements": [
    { "code": "ACH_ORACLE", "name": "Oráculo", "tier": "silver",
      "reward": { "xp": 75, "gold": 60, "title_id": null } }
  ],
  "items": [
    { "user_item_id": "…", "item_code": "pluma_primer_paso", "name": "Pluma del Primer Paso",
      "slot": "accessory", "rarity": "common", "origin": "achievement",
      "unlock_reason": "Completaste tu primera lección", "can_equip": true }
  ],
  "unlocks": [
    { "type": "module", "id": "…", "name": "Agregaciones" },
    { "type": "territory", "id": "…", "name": "Castillo de las Consultas" },
    { "type": "assessment", "id": "…", "name": "Prueba del módulo" }
  ],
  "assessment_result": null,
  "presentation_order": ["xp", "gold", "mastery", "streak", "level_up", "item", "achievement", "mission"],
  "pending_sync": false
}
```

**Reglas del objeto** (vinculantes para servidor y cliente):

1. Todas las secciones existen siempre; las vacías van como `null` (objetos) o `[]` (listas). El cliente nunca infiere: si `level.leveled_up` es `false`, no hay animación de nivel.
2. **`presentation_order` es autoritativo**: el cliente anima estrictamente en ese orden. El orden canónico es el de la cola de celebraciones del documento de UX:
   1. `xp` — desglose de XP en la pantalla de resumen.
   2. `gold` — contador de oro.
   3. `mastery` — delta de dominio del tema y del conocimiento.
   4. `streak` — overlay de racha (**solo** si `is_first_activity_of_day`).
   5. `level_up` — overlay de subida de nivel.
   6. `item` — overlay "Nuevo equipamiento" con "Equipar ahora".
   7. `achievement` — chip o tarjeta de logro.
   8. `mission` — chip de misión completada.
   Máximo **3 overlays** (posiciones 4–6); el resto se muestra como chips en la pantalla de resumen. La racha va primero porque es la mecánica principal; el ítem va después del nivel porque subir de nivel puede habilitarlo.
3. Los importes ya vienen calculados y aplicados: `total_after`, `balance_after` y `mastery_after` son el estado **posterior** persistido.
4. Idempotencia: repetir la petición con la misma `Idempotency-Key` devuelve el **mismo** `receipt_id` y el mismo contenido, sin volver a otorgar nada.
5. `pending_sync = true` solo si alguna recompensa quedó en reintento en segundo plano; el cliente la muestra como "pendiente de confirmar".
6. `assessment_result` se rellena únicamente en `POST /assessment-attempts/{id}/submit`.
---

# 8. Convenciones transversales

## 8.1 Formato de error de la API

**Todas** las respuestas de error usan exactamente esta forma. El mensaje va en español, dirigido a la persona; los detalles técnicos van en `details`.

```json
{
  "error": {
    "code": "INSUFFICIENT_GOLD",
    "message": "No te alcanza el oro para esta compra.",
    "details": { "required": 1200, "balance": 860, "missing": 340 },
    "request_id": "01J9X4K2M7Q8R…",
    "field_errors": []
  }
}
```

En errores de validación (`422`), `field_errors` lleva `[{"field": "goal_text", "message": "El objetivo no puede estar vacío."}]` y `code = "VALIDATION_ERROR"`.

**Catálogo de códigos** (cerrado; añadir uno nuevo exige actualizar este contrato):

| Código | HTTP | Cuándo |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Cuerpo o parámetros inválidos. |
| `UNAUTHORIZED` | 401 | Falta el token, está vencido o es inválido. |
| `INVALID_CREDENTIALS` | 401 | Correo o contraseña incorrectos. |
| `TOKEN_REUSE_DETECTED` | 401 | Refresh token ya rotado; se revoca la cadena. |
| `FORBIDDEN` | 403 | El recurso no pertenece al usuario o falta el rol. |
| `NOT_FOUND` | 404 | El recurso no existe (o no es visible para el usuario). |
| `EMAIL_ALREADY_EXISTS` | 409 | Registro con un correo ya usado. |
| `CHARACTER_ALREADY_EXISTS` | 409 | El usuario ya creó su personaje. |
| `ALREADY_OWNED` | 409 | El usuario ya posee el ítem. |
| `REQUIREMENTS_NOT_MET` | 409 | No cumple los requisitos de desbloqueo o el nivel mínimo. |
| `PRICE_CHANGED` | 409 | `expected_price` no coincide con el precio vigente. |
| `UNAVAILABLE` | 409 | El listado no está activo o está fuera de ventana. |
| `INSUFFICIENT_GOLD` | 409 | Saldo insuficiente. |
| `ATTEMPT_NOT_OPEN` | 409 | Respuesta fuera de una actividad abierta o vencida (regla A2). |
| `ALREADY_ANSWERED` | 409 | La pregunta ya se puntuó en este intento. |
| `MODULE_LOCKED` | 409 | El módulo aún no está desbloqueado. |
| `ASSESSMENT_COOLDOWN` | 409 | Enfriamiento activo; `details.cooldown_until` y `details.can_waive_with_review`. |
| `ASSESSMENT_ATTEMPT_LIMIT` | 409 | Se alcanzó `mastery.assessment.max_attempts_per_day`. |
| `CONTENT_NOT_READY` | 409 | El contenido aún se está generando; `details.job_id`. |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | Falta la cabecera en una operación que otorga recompensas. |
| `IDEMPOTENCY_KEY_CONFLICT` | 409 | La misma clave se usó con un cuerpo distinto. |
| `QUOTA_EXCEEDED` | 429 | Cuota diaria de IA agotada (`details.quota`, `details.resets_at`). |
| `RATE_LIMITED` | 429 | Demasiadas peticiones; cabecera `Retry-After`. |
| `AI_BUDGET_EXCEEDED` | 503 | Freno global de presupuesto; la evaluación determinista sigue funcionando. |
| `FILE_TOO_LARGE` | 413 | Supera `ingestion.max_file_mb`. |
| `UNSUPPORTED_FILE_TYPE` | 415 | Formato no admitido en el MVP. |
| `DOCUMENT_UNREADABLE` | 422 | PDF escaneado o material insuficiente (`details.min_words`). |
| `GENERATION_FAILED` | 502 | Fallo de generación tras los reintentos. |
| `INTERNAL_ERROR` | 500 | Error no controlado; nunca expone traza ni SQL. |

Nunca se devuelve un mensaje técnico al usuario: el `message` es el texto que la app puede mostrar tal cual.

## 8.2 Paginación

Paginación por **cursor opaco**, estable y barata en PostgreSQL:

```
GET /api/v1/inventory?limit=30&cursor=eyJpZCI6…
```

```json
{
  "items": [ … ],
  "page": { "limit": 30, "next_cursor": "eyJpZCI6…", "has_more": true, "total": 46 }
}
```

- `limit` por defecto 20, máximo 100.
- `next_cursor` es `base64(json)` con la última clave de orden (`{"created_at": "...", "id": "..."}`); nunca un `OFFSET`.
- `total` es opcional y solo se calcula donde es barato (inventario, logros); en listas grandes se devuelve `null`.
- El orden por defecto siempre es determinista y termina en `id` para evitar duplicados entre páginas.

## 8.3 Idempotencia

- Cabecera **`Idempotency-Key`** (UUID v4) **obligatoria** en: `POST /paths`, `POST /documents`, `POST /documents/paste`, `POST /lessons/{id}/start`, `POST /activities/{id}/answers`, `POST /activities/{id}/complete`, `POST /reviews/start`, `POST /assessments/{id}/start`, `POST /assessment-attempts/{id}/answers`, `POST /assessment-attempts/{id}/submit`, `POST /missions/{id}/claim`, `POST /shop/purchase`, `POST /characters`. Sin ella → `400 IDEMPOTENCY_KEY_REQUIRED`.
- La clave se persiste en la tabla del recurso (`idempotency_key`, único por usuario). Un reintento con la misma clave y el mismo cuerpo devuelve **la misma respuesta** con `200` (no `201`) y sin efectos nuevos. Con un cuerpo distinto → `409 IDEMPOTENCY_KEY_CONFLICT`.
- Los eventos derivados que el servidor genera dentro de una cascada construyen su clave de forma determinista: `"<evento>:<user_id>:<entidad_id>:<n>"` (por ejemplo `"lesson-complete:9b7f…:a1c2…:1"`), de modo que reprocesar no duplica.
- Las claves se conservan al menos 30 días.

## 8.4 Cabeceras

| Cabecera | Dirección | Obligatoria | Uso |
|---|---|---|---|
| `Authorization: Bearer <jwt>` | petición | sí (salvo rutas públicas) | Access token, TTL `JWT_ACCESS_TTL_MIN` (30 min). |
| `Idempotency-Key` | petición | en las rutas de §8.3 | UUID v4. |
| `X-Request-Id` | ambas | no | Si el cliente no la envía, el servidor genera una; siempre vuelve en la respuesta y en `error.request_id`. |
| `X-Client-Version` | petición | recomendada | `app/1.4.2 (android 14)`; permite bloquear versiones incompatibles. |
| `X-Timezone` | petición | recomendada | Zona IANA del dispositivo; si difiere de `users.timezone` se actualiza con el límite de 1 cambio cada 24 h. |
| `Accept-Language` | petición | no | `es-CL` por defecto. |
| `Retry-After` | respuesta | en 429/503 | Segundos hasta reintentar. |
| `X-Config-Version` | respuesta | sí | Versión vigente de `game_configs`; si el cliente ve una mayor, recarga `/config/public`. |

## 8.5 Versionado

- Prefijo `/api/v1` en todas las rutas. Un cambio **incompatible** (quitar o renombrar un campo, cambiar un tipo, cambiar la semántica de un valor de enum) exige `/api/v2`.
- Cambios **aditivos** (nuevo campo opcional, nuevo valor de enum documentado, nueva ruta) no cambian la versión, pero se anotan en el registro de cambios de este contrato.
- Un endpoint en retirada responde con la cabecera `Deprecation: true` y `Sunset: <fecha RFC 7231>` durante al menos 60 días.
- `EventType`, `game_configs` y los esquemas de `payload` de eventos también están versionados: `domain_events.version` sube cuando cambia la forma del payload.

## 8.6 Zona horaria del usuario y fechas

- **Todo timestamp** de la base de datos y de la API es UTC, en ISO 8601 con `Z` (`2026-09-10T02:58:41Z`). Los `DateTime` de SQLAlchemy son `timezone=True`.
- `users.timezone` es una zona **IANA** (`America/Santiago`), capturada del dispositivo en el registro.
- `local_date` la calcula **siempre el servidor** convirtiendo `occurred_at` a `users.timezone`; viaja en el evento y se persiste en `streak_days`, `study_activities`, `question_attempts`, `xp_transactions` y `gold_transactions`. Ningún consumidor la recalcula.
- Corte del día: **medianoche local**. Tolerancia de sincronización: 10 minutos entre la marca del cliente y la del servidor; fuera de ella manda el servidor.
- Cambios de zona horaria: máximo 1 efectivo cada 24 h (`users.timezone_changed_at`, `users.previous_timezone`); un salto de ≥ 3 h habilita el ajuste por viaje de la racha.
- Los campos que representan un día calendario (`local_date`, `assigned_for`, `effective_from`) son `sa.Date`, nunca `DateTime`.

## 8.7 Seguridad y límites

- Contraseñas con `bcrypt` (`passlib`), coste 12. Nunca se registran ni se devuelven.
- Access token JWT (`pyjwt`, HS256, `JWT_SECRET`) con `sub`, `role`, `exp`, `iat`, `jti`. Refresh token opaco de 256 bits, guardado solo como SHA-256, rotatorio y con detección de reuso.
- **Aislamiento por usuario obligatorio**: toda consulta a `documents`, `document_chunks`, `learning_paths` propias, `user_*` y `wallets` filtra por `user_id`. Está prohibido exponer un endpoint que reciba un id sin comprobar la propiedad → `404` (no `403`) para no filtrar existencia.
- **Nunca** se serializan al cliente: `questions.answer_key`, `password_hash`, `refresh_tokens.token_hash`, `prompt_templates.body`, ni las claves de `game_configs` con `is_public = false`.
- Rate limiting con `slowapi`: 60 req/min por usuario en general; 10/min en `POST /shop/purchase`; 5/min en `POST /paths`; 20/min en `POST /activities/{id}/answers`.
- Validación de subidas: extensión, tipo MIME, **magic bytes**, tamaño y número de páginas antes de encolar.
- El material del usuario es **entrada no confiable**: nunca va en el `system` del prompt, siempre en bloques delimitados del mensaje de usuario; las llamadas de generación no llevan herramientas; toda salida se valida contra su esquema antes de persistir. XP y oro los asigna solo el motor de gamificación a partir de eventos del servidor, jamás a partir de texto generado.

## 8.8 Serialización

- JSON con `orjson`; claves en `snake_case`; UUID como cadena; `Numeric(5,2)` se serializa como número con 2 decimales (`47.00`); enteros nunca como cadena.
- Los enums se serializan por su **valor** (`"con_fuente"`, `"epic"`, `"LESSON_COMPLETED"`).
- Los esquemas Pydantic de salida terminan en `Out`, los de entrada en `In` o `Create`/`Update`. Un esquema de salida jamás hereda de un modelo SQLAlchemy: se construye con `model_config = ConfigDict(from_attributes=True)`.
- Ninguna respuesta expone identificadores internos de otros usuarios.

## 8.9 Estructura de carpetas del backend y dueño de cada archivo

Ocho agentes, ocho ámbitos disjuntos. **Ningún agente toca un archivo que no sea suyo.** Los nombres A1…A8 designan el ámbito, no a una persona.

| Agente | Ámbito | Archivos que le pertenecen |
|---|---|---|
| **A1** | Núcleo e infraestructura | `app/core/config.py`, `app/core/db.py`, `app/core/security.py`, `app/core/errors.py`, `app/core/pagination.py`, `app/core/idempotency.py`, `app/core/logging.py`, `app/core/deps.py`, `app/models/enums.py`, `app/main.py`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `tests/conftest.py` |
| **A2** | `identity` | `app/models/identity.py`, `app/modules/identity/**`, `app/schemas/identity.py`, `app/api/v1/auth.py`, `app/api/v1/characters.py`, `app/api/v1/settings.py`, `tests/test_identity.py` |
| **A3** | `content` | `app/models/content.py`, `app/modules/content/**`, `app/schemas/content.py`, `app/api/v1/paths.py`, `app/api/v1/knowledge_areas.py`, `app/api/v1/lessons.py`, `tests/test_content.py` |
| **A4** | `ingestion` + `ai` | `app/models/ingestion.py`, `app/modules/ingestion/**`, `app/modules/ai/**`, `app/schemas/ingestion.py`, `app/api/v1/documents.py`, `app/api/v1/jobs.py`, `app/prompts/**`, `app/worker/**`, `tests/test_ingestion.py`, `tests/test_ai.py` |
| **A5** | `progress` | `app/models/progress.py`, `app/modules/progress/**`, `app/schemas/progress.py`, `app/api/v1/activities.py`, `app/api/v1/assessments.py`, `app/api/v1/reviews.py`, `tests/test_progress.py` |
| **A6** | `gamification` | `app/models/gamification.py`, `app/modules/gamification/**`, `app/schemas/gamification.py`, `app/api/v1/dashboard.py`, `app/api/v1/streak.py`, `app/api/v1/missions.py`, `app/api/v1/achievements.py`, `app/api/v1/notifications.py`, `app/api/v1/config.py`, `tests/test_gamification.py` |
| **A7** | `economy` | `app/models/economy.py`, `app/modules/economy/**`, `app/schemas/economy.py`, `app/api/v1/shop.py`, `app/api/v1/inventory.py`, `app/api/v1/avatar.py`, `tests/test_economy.py` |
| **A8** | Integración | `app/models/__init__.py`, `app/api/v1/__init__.py` (router raíz), `app/schemas/__init__.py`, `app/seeds/**`, `alembic/versions/*`, `tests/test_api_smoke.py`, `tests/test_contract.py` |

Árbol resultante:

```
backend/
├── CONTRACT.md                     # este documento (arquitecto)
├── alembic.ini                     # A1
├── alembic/
│   ├── env.py                      # A1  (importa app.models para el autogenerate)
│   ├── script.py.mako              # A1
│   └── versions/                   # A8  (migración inicial única del MVP)
├── app/
│   ├── main.py                     # A1  (crea la app, monta el router de A8, middlewares)
│   ├── core/
│   │   ├── config.py               # A1  (Settings de Pydantic desde .env)
│   │   ├── db.py                   # A1  (Base, mixins, engine y Session síncronos)
│   │   ├── security.py             # A1  (bcrypt, JWT, dependencias de autorización)
│   │   ├── errors.py               # A1  (AppError, catálogo de códigos, handlers)
│   │   ├── pagination.py           # A1  (cursor y sobre Page)
│   │   ├── idempotency.py          # A1  (lectura y validación de Idempotency-Key)
│   │   ├── logging.py              # A1  (structlog en JSON con request_id)
│   │   └── deps.py                 # A1  (get_db, get_current_user, get_config)
│   ├── models/
│   │   ├── __init__.py             # A8  (importa los 6 módulos para Base.metadata)
│   │   ├── enums.py                # A1
│   │   ├── identity.py             # A2
│   │   ├── content.py              # A3
│   │   ├── ingestion.py            # A4
│   │   ├── progress.py             # A5
│   │   ├── gamification.py         # A6
│   │   └── economy.py              # A7
│   ├── modules/
│   │   ├── identity/               # A2
│   │   ├── content/                # A3
│   │   ├── ingestion/              # A4
│   │   ├── ai/                     # A4
│   │   ├── progress/               # A5
│   │   ├── gamification/           # A6
│   │   └── economy/                # A7
│   ├── api/v1/                     # un archivo por área, dueño según la tabla
│   ├── schemas/                    # un archivo por módulo, dueño según la tabla
│   ├── prompts/                    # A4
│   ├── seeds/                      # A8  (game_configs, level_definitions, mission_templates,
│   │                               #      achievements, items, shop_listings, knowledge_areas)
│   └── worker/                     # A4  (bucle de generation_jobs y tareas periódicas)
└── tests/                          # dueño según la tabla
```

Cada paquete de `app/modules/<módulo>/` sigue la misma forma interna: `service.py` (casos de uso), `repository.py` (consultas SQLAlchemy), `rules.py` (fórmulas puras y sin base de datos, cuando aplique) y `events.py` (emisión y consumo de eventos de dominio).

## 8.10 Reglas de trabajo y verificación obligatoria

1. Antes de escribir, lee **solo** este contrato y tus propios archivos. No leas los documentos de `docs/`.
2. No inventes tablas, columnas, enums, claves de configuración, eventos ni rutas que no estén aquí. Si algo falta, deja un `TODO` en el docstring y repórtalo en tu salida; **no improvises un nombre**.
3. Ejecuta y deja pasando, desde `backend/`:

```bash
python -c "import app.models.enums as e; print(len([x for x in dir(e) if x[0].isupper()]))"
python -c "from app.models import Base; print(len(Base.metadata.tables))"
python -m compileall -q app
pytest -q
```

4. El agente A8 verifica además que la migración crea el esquema completo contra la base real:

```bash
alembic upgrade head
python -c "import sqlalchemy as sa; e=sa.create_engine('postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea'); print(sorted(sa.inspect(e).get_table_names()))"
alembic downgrade base
```

5. Reglas que un revisor rechazará sin discusión: `relationship()` entre archivos de modelos distintos; `import` de un archivo de `app/models/` desde otro (salvo `enums` y `core.db`); `async def` en la capa de datos; un número de §5 escrito como literal en el código; `answer_key` en una respuesta de la API; un `UPDATE` sobre `xp_transactions` o `gold_transactions`; una tabla sin `id` UUID; una fecha sin `timezone=True`; un `CheckConstraint`, `server_default` o SQL crudo que compare una columna de enum con su valor en minúsculas en lugar del nombre del miembro (§1.4, regla 6).

---

## Registro de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | 2026-09-10 | Contrato inicial. Reconcilia brief, 01, 04, 06a, 06b, 06c, 07 y A1. Fija 65 enums, 52 tablas, 59 eventos, 177 claves de `game_configs`, las fórmulas de XP, niveles y dominio, 75 rutas de API y el objeto `RewardsReceipt`. |

---

# 9. Fuentes normativas para las semillas (addendum del arquitecto)

> Añadido tras cerrar §1–§8. El contrato fija la **estructura** de las tablas de catálogo y los **códigos** que otras secciones referencian, pero no transcribe fila por fila los catálogos. El agente que escriba `app/seeds/` **debe** tomar esos datos de los documentos de diseño indicados abajo, que son normativos a este efecto, y traducirlos a los nombres de columna y valores de enum de §2 y §3. No inventes ítems, logros ni misiones que no estén en estas fuentes; si falta un dato concreto (por ejemplo un precio), tómalo de la tabla de precios por rareza de §5.4 de este contrato.

| Semilla | Fuente normativa | Sección y línea aproximada |
|---|---|---|
| Catálogo de ítems (46: 9 iniciales, 21 de tienda, 9 de conocimiento, 4 de racha, 3 de logro) | `docs/auditoria/06c-inventario-equipamiento-tienda.md` | §8 «Catálogo inicial del MVP», línea 705 y siguientes (§8.1 a §8.6) |
| Requisitos de desbloqueo de los ítems de conocimiento y sus plantillas | `docs/auditoria/06c-inventario-equipamiento-tienda.md` | §5.2 DSL de requisitos (línea 419), §5.3 ejemplos JSON (línea 444), §5.6 y §5.7 plantillas para rutas del usuario (línea 556) |
| Pila de capas del avatar, anclajes y compatibilidad entre piezas | `docs/auditoria/06c-inventario-equipamiento-tienda.md` | §2.3 (línea 101), §2.4 (línea 129), §2.5 (línea 151), §2.7 manifiesto JSON (línea 182) |
| Arquetipos del MVP | `docs/auditoria/06c-inventario-equipamiento-tienda.md` | §3.2 (línea 283) |
| Plantillas de misión (23: D01–D13 diarias, S01–S04 especiales, W01–W06 semanales desactivadas en el MVP) | `docs/auditoria/06b-rachas-objetivos-misiones-logros.md` | §4.2 plantillas parametrizadas (línea 360), §4.6 catálogo inicial (línea 479) |
| Catálogo de logros (32) con sus condiciones declarativas | `docs/auditoria/06b-rachas-objetivos-misiones-logros.md` | §5.2 reglas declarativas (línea 541), §5.4 catálogo inicial (línea 624) |
| Hitos de racha y sus recompensas | `docs/auditoria/06b-rachas-objetivos-misiones-logros.md` | §2.6 (línea 187) |
| Objetivos diarios y sus equivalencias | `docs/auditoria/06b-rachas-objetivos-misiones-logros.md` | §3.1 (línea 279), §3.2 (línea 293) |
| Tabla de niveles y títulos de rango | `docs/auditoria/06a-economia-xp-niveles-oro-dominio.md` | sección de niveles; los valores de la curva ya están en §5.2 y §6.1 de este contrato y **mandan** sobre el documento |
| Ruta del Reino de SQL (contenido semilla real) | No existe fuente previa: **se escribe nueva**, con calidad pedagógica real | Ver §5.8 `content.*` para los límites de tamaño |

Regla de precedencia: ante cualquier discrepancia entre un documento de diseño y este contrato, **manda el contrato** (nombres de tabla y columna, enums, claves de configuración y valores numéricos de §5). Los documentos aportan el contenido; el contrato aporta la forma.
