"""Punto de entrada único de los modelos ORM de Atenea.

Importar este paquete carga los seis archivos de modelos (`identity`, `content`,
`ingestion`, `progress`, `gamification`, `economy`) y deja `Base.metadata` completa
con las **52 tablas** del contrato. Es lo que hace `alembic/env.py` antes de
autogenerar una migración y lo que hacen las semillas y las pruebas.

Este archivo **no define modelos**: solo importa y reexporta. El orden de importación
respeta la dirección de dependencias del contrato §1.3
(`identity` ← `content` ← `ingestion` … `progress` → `gamification` → `economy`),
aunque, al estar prohibido `relationship()` entre archivos y declararse todas las
claves foráneas por texto, el orden no es funcionalmente crítico: Alembic ordena la
creación de tablas por dependencia dentro de un mismo `upgrade()`.
"""

from __future__ import annotations

from app.core.db import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.content import (
    Assessment,
    AssessmentQuestion,
    KnowledgeArea,
    LearningPath,
    Lesson,
    LessonBlock,
    PathModule,
    Question,
    Territory,
    Topic,
)
from app.models.economy import (
    GoldTransaction,
    Item,
    ItemRequirement,
    Purchase,
    ShopListing,
    UserItem,
    Wallet,
)
from app.models.gamification import (
    Achievement,
    DailyGoal,
    DomainEvent,
    GameConfig,
    LevelDefinition,
    MissionTemplate,
    Notification,
    RewardRule,
    Streak,
    StreakDay,
    UserAchievement,
    UserMission,
    XPTransaction,
)
from app.models.identity import (
    AvatarConfig,
    Character,
    EquippedItem,
    RefreshToken,
    User,
    UserSettings,
)
from app.models.ingestion import (
    ContentProvenance,
    Document,
    DocumentChunk,
    DocumentVersion,
    GenerationJob,
    KnowledgeBase,
    PromptTemplate,
)
from app.models.progress import (
    AssessmentAttempt,
    LearningSession,
    QuestionAttempt,
    StudyActivity,
    UserAreaProgress,
    UserLessonProgress,
    UserModuleProgress,
    UserPathProgress,
    UserTopicProgress,
)

#: Número de tablas que el contrato v1.0 declara. Las pruebas de contrato lo comprueban
#: contra `len(Base.metadata.tables)` para detectar tablas perdidas o de más.
EXPECTED_TABLE_COUNT: int = 52

__all__ = [
    "EXPECTED_TABLE_COUNT",
    # Base declarativa y mixins (reexportados por comodidad)
    "Base",
    "CreatedAtMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    # identity
    "AvatarConfig",
    "Character",
    "EquippedItem",
    "RefreshToken",
    "User",
    "UserSettings",
    # content
    "Assessment",
    "AssessmentQuestion",
    "KnowledgeArea",
    "LearningPath",
    "Lesson",
    "LessonBlock",
    "PathModule",
    "Question",
    "Territory",
    "Topic",
    # ingestion
    "ContentProvenance",
    "Document",
    "DocumentChunk",
    "DocumentVersion",
    "GenerationJob",
    "KnowledgeBase",
    "PromptTemplate",
    # progress
    "AssessmentAttempt",
    "LearningSession",
    "QuestionAttempt",
    "StudyActivity",
    "UserAreaProgress",
    "UserLessonProgress",
    "UserModuleProgress",
    "UserPathProgress",
    "UserTopicProgress",
    # gamification
    "Achievement",
    "DailyGoal",
    "DomainEvent",
    "GameConfig",
    "LevelDefinition",
    "MissionTemplate",
    "Notification",
    "RewardRule",
    "Streak",
    "StreakDay",
    "UserAchievement",
    "UserMission",
    "XPTransaction",
    # economy
    "GoldTransaction",
    "Item",
    "ItemRequirement",
    "Purchase",
    "ShopListing",
    "UserItem",
    "Wallet",
]
