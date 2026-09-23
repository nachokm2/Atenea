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


class WorldWeaponClass(StrEnum):
    """Clase visual de lo empuñado, para la figura simplificada del mundo
    caminable (`docs/planes/mundo-caminable.md`, Parte B).

    Ese personaje no tiene fidelidad por ítem — el arma es un prop estático
    compuesto en la mano, no parte del fotograma — así que 46 ítems del
    catálogo se reducen a estas seis siluetas. Un ítem `WEAPON`/`OFFHAND` sin
    clase asignada no emite ninguna: el cliente no dibuja ningún prop en esa
    mano en vez de inventar uno. Nunca un valor por defecto silencioso.
    """

    BLADE = "blade"      # espadas
    BOW = "bow"          # arcos
    STAFF = "staff"      # bastón, cetro, báculo
    TORCH = "torch"      # antorcha
    SHIELD = "shield"    # escudos redondos
    TOME = "tome"        # el tomo del erudito — no es un escudo


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
