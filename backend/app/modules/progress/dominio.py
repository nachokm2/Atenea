"""Dominio (🧠 `mastery`): la fórmula exacta del contrato §6.4–§6.8.

**El dominio no se gana con el tiempo.** Sale exclusivamente de las evidencias de
desempeño (`question_attempts`) y del resultado de las evaluaciones de módulo
(`assessment_attempts`). Acumular horas de estudio no mueve ni un punto de dominio.

Resumen de la fórmula (todas las constantes salen de `game_configs`, §5.5):

```
w_dif(d)    = mastery.weight.difficulty[d]          # easy 1.0 · medium 1.5 · hard 2.0
w_ctx(ctx)  = mastery.weight.context[ctx]           # lección/práctica/repaso 1.0 · desafío 1.5 · evaluación 2.0
w_rec(edad) = 0.5 ** (edad_dias / mastery.recency_half_life_days)
w_ret(k)    = mastery.weight.retake[min(k, 3) - 1]  # 1.0 / 0.6 / 0.3
w_i         = w_dif * w_ctx * w_rec * w_ret

c_i         = 1.0 acierto al 1.er intento · 0.5 al 2.º · 0.0 en cualquier otro caso

P_t         = (Σ w_i·c_i + m·p0) / (Σ w_i + m)      # m = 3 · p0 = 0.5
C_t         = lecciones_completadas / lecciones_del_tema
g(C)        = coverage_floor + (1 - coverage_floor)·C
M_t_raw     = P_t · g(C_t)

Δ           = días desde la última evidencia
h           = min(decay.half_life_days · decay.stability_factor**s, decay.half_life_max_days)
D(Δ)        = 1                                          si Δ <= decay.grace_days
D(Δ)        = floor + (1 - floor)·0.5**((Δ - grace)/h)   si Δ >  decay.grace_days
M_t         = M_t_raw · D(Δ)

E_mod       = max_k(score_k - retake_penalty.per_attempt·(k-1)), penalización tope `max`
M_mod       = weight_topics · promedio_ponderado(M_t, peso = lecciones del tema)
            + weight_assessment · E_mod
M_area      = Σ_mod(lecciones_del_módulo · M_mod) / Σ_mod lecciones_del_módulo
```

**Escalas.** Las funciones puras de este archivo trabajan en la escala **0–100**, que
es la de las columnas `Numeric(5, 2)` de `user_topic_progress`, `user_module_progress`
y `user_area_progress`. Los pesos y factores (`w_*`, `g`, `D`) son adimensionales.

**Protección contra repetir la evaluación hasta aprobar** (§6.4 y §6.6): el peso de
reintento `w_ret` degrada la evidencia repetida (1.0 → 0.6 → 0.3), el puntaje efectivo
`E_mod` descuenta `retake_penalty.per_attempt` por cada intento previo (con tope), el
enfriamiento entre intentos vive en `assessment_attempts.cooldown_until` y el banco
rotativo limita el solapamiento entre intentos consecutivos.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utcnow
from app.models.content import LearningPath, Lesson, PathModule, Topic
from app.models.enums import (
    ActivityContext,
    AttemptStatus,
    DifficultyLevel,
    EventType,
    KnowledgeAreaStatus,
    ModuleStatus,
    PathStatus,
    ProgressState,
)
from app.models.gamification import DomainEvent
from app.models.progress import (
    AssessmentAttempt,
    QuestionAttempt,
    UserAreaProgress,
    UserLessonProgress,
    UserModuleProgress,
    UserPathProgress,
    UserTopicProgress,
)
from app.modules.progress import LectorConfiguracion, a_decimal_2, a_float

SEGUNDOS_POR_DIA = 86_400.0

#: Claves de `game_configs` que necesita el cálculo de dominio (§5.5).
CLAVES_DOMINIO: tuple[str, ...] = (
    "mastery.weight.difficulty",
    "mastery.weight.context",
    "mastery.weight.retake",
    "mastery.correctness_second_try",
    "mastery.recency_half_life_days",
    "mastery.prior_m",
    "mastery.prior_p0",
    "mastery.evidence_window",
    "mastery.coverage_floor",
    "mastery.decay",
    "mastery.module.weight_topics",
    "mastery.module.weight_assessment",
    "mastery.assessment.pass_score",
    "mastery.assessment.retake_penalty",
    "mastery.threshold.mastered",
    "mastery.threshold.at_risk",
    "mastery.threshold.weak_practice",
    "mastery.weak_min_evidence",
    "mastery.review.stability_min_score",
    "mastery.area_mastered_requires_completed_path",
)


# ---------------------------------------------------------------------------
# Configuración de dominio
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigDominio:
    """Instantánea inmutable de las claves `mastery.*` de `game_configs` (§5.5).

    Se construye con `desde_lector()` en producción y a mano en las pruebas puras:
    así ninguna constante de balance aparece como literal en el código de la app.
    """

    pesos_dificultad: dict[str, float]
    pesos_contexto: dict[str, float]
    pesos_reintento: tuple[float, ...]
    acierto_segundo_intento: float
    media_vida_recencia_dias: float
    prior_m: float
    prior_p0: float
    ventana_max_items: int
    ventana_max_dias: int
    piso_cobertura: float
    decaimiento_gracia_dias: float
    decaimiento_piso: float
    decaimiento_media_vida_dias: float
    decaimiento_factor_estabilidad: float
    decaimiento_media_vida_max_dias: float
    peso_modulo_temas: float
    peso_modulo_evaluacion: float
    puntaje_aprobacion: float
    penalizacion_reintento_por_intento: float
    penalizacion_reintento_max: float
    umbral_dominado: float
    umbral_en_riesgo: float
    umbral_practica_debil: float
    evidencias_minimas_debilidad: int
    repaso_puntaje_min_estabilidad: float
    area_exige_ruta_completa: bool

    @classmethod
    def desde_lector(cls, cfg: LectorConfiguracion) -> ConfigDominio:
        """Carga la configuración de dominio en **una sola** consulta a `game_configs`."""
        valores = cfg.muchas(CLAVES_DOMINIO)
        decay = valores["mastery.decay"]
        ventana = valores["mastery.evidence_window"]
        penalizacion = valores["mastery.assessment.retake_penalty"]
        return cls(
            pesos_dificultad={str(k): float(v) for k, v in valores["mastery.weight.difficulty"].items()},
            pesos_contexto={str(k): float(v) for k, v in valores["mastery.weight.context"].items()},
            pesos_reintento=tuple(float(v) for v in valores["mastery.weight.retake"]),
            acierto_segundo_intento=float(valores["mastery.correctness_second_try"]),
            media_vida_recencia_dias=float(valores["mastery.recency_half_life_days"]),
            prior_m=float(valores["mastery.prior_m"]),
            prior_p0=float(valores["mastery.prior_p0"]),
            ventana_max_items=int(ventana["max_items"]),
            ventana_max_dias=int(ventana["max_days"]),
            piso_cobertura=float(valores["mastery.coverage_floor"]),
            decaimiento_gracia_dias=float(decay["grace_days"]),
            decaimiento_piso=float(decay["floor"]),
            decaimiento_media_vida_dias=float(decay["half_life_days"]),
            decaimiento_factor_estabilidad=float(decay["stability_factor"]),
            decaimiento_media_vida_max_dias=float(decay["half_life_max_days"]),
            peso_modulo_temas=float(valores["mastery.module.weight_topics"]),
            peso_modulo_evaluacion=float(valores["mastery.module.weight_assessment"]),
            puntaje_aprobacion=float(valores["mastery.assessment.pass_score"]),
            penalizacion_reintento_por_intento=float(penalizacion["per_attempt"]),
            penalizacion_reintento_max=float(penalizacion["max"]),
            umbral_dominado=float(valores["mastery.threshold.mastered"]),
            umbral_en_riesgo=float(valores["mastery.threshold.at_risk"]),
            umbral_practica_debil=float(valores["mastery.threshold.weak_practice"]),
            evidencias_minimas_debilidad=int(valores["mastery.weak_min_evidence"]),
            repaso_puntaje_min_estabilidad=float(valores["mastery.review.stability_min_score"]),
            area_exige_ruta_completa=bool(valores["mastery.area_mastered_requires_completed_path"]),
        )


# ---------------------------------------------------------------------------
# Estructuras de datos puras
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Evidencia:
    """Una respuesta que cuenta para dominio (fila de `question_attempts`)."""

    answered_at: datetime
    difficulty: DifficultyLevel | str
    context: ActivityContext | str
    attempt_no: int
    #: `c_i` de la fórmula: 1.00 / 0.50 / 0.00 (columna `correctness_weight`).
    correctness_weight: float
    counts_for_mastery: bool = True

    @classmethod
    def desde_intento(cls, intento: QuestionAttempt) -> Evidencia:
        """Construye la evidencia desde una fila de `question_attempts`."""
        return cls(
            answered_at=ensure_utc(intento.answered_at),
            difficulty=intento.difficulty,
            context=intento.context,
            attempt_no=int(intento.attempt_no),
            correctness_weight=a_float(intento.correctness_weight),
            counts_for_mastery=bool(intento.counts_for_mastery),
        )


@dataclass(frozen=True, slots=True)
class DominioTema:
    """Resultado del cálculo de dominio de un tema (`M_t`), en escala 0–100."""

    practice_score: float
    coverage: float
    mastery_raw: float
    mastery: float
    evidence_count: int
    last_evidence_at: datetime | None
    dias_desde_evidencia: float
    factor_decaimiento: float
    is_weak: bool


@dataclass(frozen=True, slots=True)
class TemaPonderado:
    """Un tema con su dominio y su peso (número de lecciones) dentro del módulo."""

    topic_id: uuid.UUID | None
    mastery: float
    lecciones: int


@dataclass(frozen=True, slots=True)
class ModuloPonderado:
    """Un módulo con su dominio y su peso (número de lecciones) dentro del área."""

    module_id: uuid.UUID | None
    mastery: float
    lecciones: int


@dataclass(frozen=True, slots=True)
class DominioModulo:
    """Resultado del cálculo de dominio de un módulo (`M_mod`), en escala 0–100."""

    mastery: float
    media_temas: float
    puntaje_efectivo: float
    mejor_puntaje: float | None
    intentos: int
    aprobado: bool
    dominado: bool


# ---------------------------------------------------------------------------
# Pesos (§6.4)
# ---------------------------------------------------------------------------


def _clave(valor: object) -> str:
    """Normaliza un enum o cadena al valor `snake_case` que usan las claves de §5."""
    return str(getattr(valor, "value", valor))


def peso_dificultad(dificultad: DifficultyLevel | str, cfg: ConfigDominio) -> float:
    """`w_dif(d)`: cuánto vale una pregunta según su dificultad."""
    return float(cfg.pesos_dificultad[_clave(dificultad)])


def peso_contexto(contexto: ActivityContext | str, cfg: ConfigDominio) -> float:
    """`w_ctx(ctx)`: cuánto vale la evidencia según dónde se produjo."""
    return float(cfg.pesos_contexto[_clave(contexto)])


def peso_recencia(edad_dias: float, cfg: ConfigDominio) -> float:
    """`w_rec(edad)`: decaimiento exponencial con media vida `recency_half_life_days`."""
    if edad_dias <= 0:
        return 1.0
    return 0.5 ** (edad_dias / cfg.media_vida_recencia_dias)


def peso_reintento(attempt_no: int, cfg: ConfigDominio) -> float:
    """`w_ret(k)`: la evidencia repetida sobre la misma pregunta pesa menos.

    Es una de las tres protecciones contra «repetir hasta aprobar» (§6.4).
    """
    indice = min(max(int(attempt_no), 1), len(cfg.pesos_reintento)) - 1
    return float(cfg.pesos_reintento[indice])


def peso_de_acierto(is_correct: bool, attempt_no: int, cfg: ConfigDominio) -> float:
    """`c_i`: 1.0 si acierta al 1.er intento, 0.5 al 2.º, 0.0 en cualquier otro caso.

    El crédito parcial («casi») cuenta **0** para dominio aunque pague XP reducido.
    """
    if not is_correct:
        return 0.0
    if attempt_no <= 1:
        return 1.0
    if attempt_no == 2:
        return float(cfg.acierto_segundo_intento)
    return 0.0


# ---------------------------------------------------------------------------
# Ventana de evidencias, precisión y cobertura (§6.4)
# ---------------------------------------------------------------------------


def seleccionar_evidencias(
    evidencias: Iterable[Evidencia], cfg: ConfigDominio
) -> list[Evidencia]:
    """Aplica `mastery.evidence_window`: últimas N evidencias **o** los últimos D días,
    «lo que dé más cobertura» (§6.4). Descarta lo que no cuenta para dominio.

    La antigüedad se mide respecto a la **evidencia más reciente del tema**, igual que
    `w_rec`, no respecto a hoy.
    """
    validas = [e for e in evidencias if e.counts_for_mastery]
    if not validas:
        return []
    validas.sort(key=lambda e: ensure_utc(e.answered_at), reverse=True)
    referencia = ensure_utc(validas[0].answered_at)

    por_cantidad = validas[: cfg.ventana_max_items]
    limite = referencia - timedelta(days=cfg.ventana_max_dias)
    por_dias = [e for e in validas if ensure_utc(e.answered_at) >= limite]
    return por_dias if len(por_dias) > len(por_cantidad) else por_cantidad


def precision_ponderada(evidencias: Sequence[Evidencia], cfg: ConfigDominio) -> float:
    """`P_t` en escala 0–100: precisión ponderada con prior bayesiano `m·p0`.

    Sin evidencias devuelve el prior (`p0`), que es el valor por defecto de la
    columna `user_topic_progress.practice_score`.
    """
    if not evidencias:
        return cfg.prior_p0 * 100.0
    referencia = max(ensure_utc(e.answered_at) for e in evidencias)

    suma_pesos = 0.0
    suma_aciertos = 0.0
    for e in evidencias:
        edad = (referencia - ensure_utc(e.answered_at)).total_seconds() / SEGUNDOS_POR_DIA
        w = (
            peso_dificultad(e.difficulty, cfg)
            * peso_contexto(e.context, cfg)
            * peso_recencia(edad, cfg)
            * peso_reintento(e.attempt_no, cfg)
        )
        suma_pesos += w
        suma_aciertos += w * float(e.correctness_weight)

    p_t = (suma_aciertos + cfg.prior_m * cfg.prior_p0) / (suma_pesos + cfg.prior_m)
    return p_t * 100.0


def cobertura(lecciones_completadas: int, lecciones_totales: int) -> float:
    """`C_t` en escala 0–100: lecciones completadas del tema sobre sus lecciones."""
    if lecciones_totales <= 0:
        return 0.0
    return min(1.0, max(0.0, lecciones_completadas / lecciones_totales)) * 100.0


def factor_cobertura(cobertura_pct: float, cfg: ConfigDominio) -> float:
    """`g(C) = coverage_floor + (1 - coverage_floor)·C`, adimensional en [floor, 1]."""
    c = min(1.0, max(0.0, cobertura_pct / 100.0))
    return cfg.piso_cobertura + (1.0 - cfg.piso_cobertura) * c


def media_vida_decaimiento(stability_s: int, cfg: ConfigDominio) -> float:
    """`h = min(half_life_days · stability_factor**s, half_life_max_days)` (§6.5)."""
    h = cfg.decaimiento_media_vida_dias * (cfg.decaimiento_factor_estabilidad ** max(0, int(stability_s)))
    return min(h, cfg.decaimiento_media_vida_max_dias)


def factor_decaimiento(dias: float, stability_s: int, cfg: ConfigDominio) -> float:
    """`D(Δ)` de la curva de olvido (§6.5), adimensional en [floor, 1].

    Dentro de los días de gracia no hay pérdida. Después, el dominio cae hacia el
    piso `decay.floor` con media vida `h`, que se alarga con cada repaso exitoso.
    """
    if dias <= cfg.decaimiento_gracia_dias:
        return 1.0
    h = media_vida_decaimiento(stability_s, cfg)
    exceso = dias - cfg.decaimiento_gracia_dias
    piso = cfg.decaimiento_piso
    return piso + (1.0 - piso) * 0.5 ** (exceso / h)


def calcular_dominio_tema(
    evidencias: Iterable[Evidencia],
    *,
    lecciones_completadas: int,
    lecciones_totales: int,
    stability_s: int = 0,
    cfg: ConfigDominio,
    ahora: datetime | None = None,
) -> DominioTema:
    """Calcula `M_t` completo para un tema: precisión, cobertura y decaimiento.

    Función **pura**: no toca la base de datos. El tiempo de estudio no es un
    argumento porque no interviene en la fórmula (§1.1).
    """
    momento = ensure_utc(ahora) if ahora is not None else utcnow()
    seleccionadas = seleccionar_evidencias(evidencias, cfg)

    p_t = precision_ponderada(seleccionadas, cfg)
    c_t = cobertura(lecciones_completadas, lecciones_totales)
    m_raw = p_t * factor_cobertura(c_t, cfg)

    if seleccionadas:
        ultima = max(ensure_utc(e.answered_at) for e in seleccionadas)
        dias = max(0.0, (momento - ultima).total_seconds() / SEGUNDOS_POR_DIA)
    else:
        ultima = None
        dias = 0.0

    d = factor_decaimiento(dias, stability_s, cfg) if ultima is not None else 1.0

    return DominioTema(
        practice_score=round(p_t, 2),
        coverage=round(c_t, 2),
        mastery_raw=round(m_raw, 2),
        mastery=round(m_raw * d, 2),
        evidence_count=len(seleccionadas),
        last_evidence_at=ultima,
        dias_desde_evidencia=dias,
        factor_decaimiento=d,
        is_weak=es_tema_debil(p_t, len(seleccionadas), cfg),
    )


def es_tema_debil(practice_score: float, evidencias: int, cfg: ConfigDominio) -> bool:
    """Bandera `is_weak` (§6.8): `P_t < weak_practice` con al menos N evidencias."""
    return evidencias >= cfg.evidencias_minimas_debilidad and practice_score < cfg.umbral_practica_debil


def es_tema_dominado(
    mastery: float, *, evaluacion_aprobada: bool, cfg: ConfigDominio
) -> bool:
    """Un tema está **dominado** solo si supera el umbral **y** su módulo tiene la
    evaluación aprobada (§6.8: «`mastered` ⇔ `M >= 80` + evaluación aprobada en módulo»).

    Sin evaluación aprobada el tema puede llegar a un dominio alto, pero nunca se
    marca como dominado: es la protección contra «practicar sin demostrarlo».
    """
    return mastery >= cfg.umbral_dominado and bool(evaluacion_aprobada)


def estado_dominio(
    mastery: float,
    *,
    ever_mastered: bool,
    evidencias: int,
    lecciones_completadas: int,
    requisito_cumplido: bool,
    cfg: ConfigDominio,
) -> KnowledgeAreaStatus:
    """Estado de dominio de tema, módulo o conocimiento según la tabla de §6.8."""
    if evidencias <= 0 and lecciones_completadas <= 0:
        return KnowledgeAreaStatus.NO_EVIDENCE
    if mastery >= cfg.umbral_dominado and requisito_cumplido:
        return KnowledgeAreaStatus.MASTERED
    if ever_mastered:
        if mastery >= cfg.umbral_en_riesgo:
            return KnowledgeAreaStatus.AT_RISK
        return KnowledgeAreaStatus.WEAKENED
    return KnowledgeAreaStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# Módulo (§6.6) y conocimiento (§6.7)
# ---------------------------------------------------------------------------


def puntaje_efectivo_evaluacion(
    puntajes_por_intento: Sequence[tuple[int, float]], cfg: ConfigDominio
) -> float:
    """`E_mod = max_k(score_k − per_attempt·(k−1))`, con penalización tope `max` (§6.6).

    `puntajes_por_intento` es `[(attempt_no, score_pct)]` en escala 0–100. La
    penalización de §5.5 viene en escala 0–1, por eso se multiplica por 100.
    Sin evaluación rendida devuelve 0: **es imposible dominar un módulo sin evaluación**.
    """
    if not puntajes_por_intento:
        return 0.0
    por_intento = cfg.penalizacion_reintento_por_intento * 100.0
    tope = cfg.penalizacion_reintento_max * 100.0
    mejor = 0.0
    for attempt_no, score in puntajes_por_intento:
        penalizacion = min(por_intento * max(0, int(attempt_no) - 1), tope)
        mejor = max(mejor, float(score) - penalizacion)
    return round(max(0.0, mejor), 2)


def promedio_ponderado_temas(temas: Sequence[TemaPonderado]) -> float:
    """Promedio de `M_t` ponderado por el número de lecciones de cada tema."""
    if not temas:
        return 0.0
    peso_total = sum(max(0, t.lecciones) for t in temas)
    if peso_total <= 0:
        return round(sum(t.mastery for t in temas) / len(temas), 2)
    return round(sum(t.mastery * max(0, t.lecciones) for t in temas) / peso_total, 2)


def calcular_dominio_modulo(
    temas: Sequence[TemaPonderado],
    puntajes_por_intento: Sequence[tuple[int, float]],
    cfg: ConfigDominio,
) -> DominioModulo:
    """`M_mod = weight_topics·temas + weight_assessment·E_mod` (§6.6).

    Un módulo está dominado si `M_mod >= mastered` **y** existe algún intento con
    `score_k >= pass_score`. Sin evaluación rendida `M_mod <= weight_topics·100`.
    """
    media = promedio_ponderado_temas(temas)
    e_mod = puntaje_efectivo_evaluacion(puntajes_por_intento, cfg)
    m_mod = cfg.peso_modulo_temas * media + cfg.peso_modulo_evaluacion * e_mod
    mejor = max((float(s) for _k, s in puntajes_por_intento), default=None)
    aprobado = mejor is not None and mejor >= cfg.puntaje_aprobacion
    m_mod = round(m_mod, 2)
    return DominioModulo(
        mastery=m_mod,
        media_temas=media,
        puntaje_efectivo=e_mod,
        mejor_puntaje=None if mejor is None else round(mejor, 2),
        intentos=len(puntajes_por_intento),
        aprobado=aprobado,
        dominado=m_mod >= cfg.umbral_dominado and aprobado,
    )


def agregar_dominio_area(modulos: Sequence[ModuloPonderado]) -> float:
    """`M_area = Σ(lecciones_del_módulo · M_mod) / Σ lecciones_del_módulo` (§6.7).

    Entran **todos** los módulos de **todas** las rutas activas del conocimiento; los
    no iniciados pesan con `M_mod = 0`. Añadir una ruta nueva baja el porcentaje: es
    deliberado, «tu horizonte se amplió».
    """
    if not modulos:
        return 0.0
    peso_total = sum(max(0, m.lecciones) for m in modulos)
    if peso_total <= 0:
        return round(sum(m.mastery for m in modulos) / len(modulos), 2)
    return round(sum(m.mastery * max(0, m.lecciones) for m in modulos) / peso_total, 2)


def es_area_dominada(
    mastery: float, *, tiene_ruta_completada: bool, cfg: ConfigDominio
) -> bool:
    """Conocimiento dominado ⇔ `M_area >= mastered` **y** ≥ 1 ruta completada (§6.7)."""
    if mastery < cfg.umbral_dominado:
        return False
    return tiene_ruta_completada or not cfg.area_exige_ruta_completa


# ---------------------------------------------------------------------------
# Servicio: recálculo por evento y materialización
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ResultadoRecalculo:
    """Deltas del recálculo, tal como los necesita `mastery_deltas` del `RewardsReceipt`."""

    topic_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    knowledge_area_id: uuid.UUID | None = None
    topic_before: float = 0.0
    topic_after: float = 0.0
    module_before: float = 0.0
    module_after: float = 0.0
    area_before: float = 0.0
    area_after: float = 0.0
    topic_status: KnowledgeAreaStatus | None = None
    module_status: ModuleStatus | None = None
    area_status: KnowledgeAreaStatus | None = None
    topics_mastered: int = 0
    #: Áreas de conocimiento dominadas, de toda la cuenta (no solo la de este
    #: recálculo). Alimenta `ACH_REALM_MASTER`, que compara este número contra
    #: sus tres niveles — sin esto la condición nunca podía cumplirse.
    areas_mastered: int = 0
    #: El tema acaba de cruzar el umbral de debilidad en **este** recálculo. Es la
    #: transición, no el estado: un tema que ya estaba débil no la vuelve a
    #: levantar, o el aprendiz recibiría el mismo aviso de repaso en cada
    #: respuesta que diera.
    weakness_detected: bool = False
    eventos: list[EventType] = field(default_factory=list)


class ServicioDominio:
    """Recalcula y materializa el dominio a partir de las evidencias en base de datos.

    Se invoca **por evento** (respuesta registrada, evaluación enviada, lección
    completada, repaso terminado) y también desde el job diario que refresca el
    decaimiento. El decaimiento se aplica en lectura, así que recalcular sin nuevas
    evidencias es idempotente salvo por el paso del tiempo.
    """

    def __init__(self, db: Session, cfg: ConfigDominio | None = None, *, lector: LectorConfiguracion | None = None) -> None:
        self.db = db
        self.lector = lector or LectorConfiguracion(db)
        self.cfg = cfg or ConfigDominio.desde_lector(self.lector)

    # -- lecturas auxiliares ---------------------------------------------

    def _evidencias_del_tema(self, user_id: uuid.UUID, topic_id: uuid.UUID) -> list[Evidencia]:
        """Evidencias de dominio del tema, de la más reciente a la más antigua.

        Índice usado: `ix_question_attempts_user_id_topic_id_answered_at`.
        """
        limite = max(self.cfg.ventana_max_items, 1)
        stmt = (
            sa.select(QuestionAttempt)
            .where(
                QuestionAttempt.user_id == user_id,
                QuestionAttempt.topic_id == topic_id,
                QuestionAttempt.counts_for_mastery.is_(True),
            )
            .order_by(QuestionAttempt.answered_at.desc())
            .limit(limite * 4)
        )
        return [Evidencia.desde_intento(fila) for fila in self.db.execute(stmt).scalars()]

    def _cobertura_del_tema(self, user_id: uuid.UUID, topic_id: uuid.UUID) -> tuple[int, int]:
        """Devuelve `(lecciones_completadas, lecciones_del_tema)`."""
        totales = self.db.execute(
            sa.select(sa.func.count(Lesson.id)).where(Lesson.topic_id == topic_id)
        ).scalar_one()
        completadas = self.db.execute(
            sa.select(sa.func.count(UserLessonProgress.id)).where(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.topic_id == topic_id,
                UserLessonProgress.status == ProgressState.COMPLETED,
            )
        ).scalar_one()
        return int(completadas), int(totales)

    def _puntajes_del_modulo(
        self, user_id: uuid.UUID, module_id: uuid.UUID
    ) -> list[tuple[int, float]]:
        """`[(attempt_no, score_pct)]` de los intentos enviados de la evaluación del módulo."""
        stmt = (
            sa.select(AssessmentAttempt.attempt_no, AssessmentAttempt.score)
            .where(
                AssessmentAttempt.user_id == user_id,
                AssessmentAttempt.module_id == module_id,
                AssessmentAttempt.status == AttemptStatus.SUBMITTED,
                AssessmentAttempt.score.is_not(None),
            )
            .order_by(AssessmentAttempt.attempt_no)
        )
        return [(int(n), a_float(s)) for n, s in self.db.execute(stmt)]

    def _fila_tema(
        self, user_id: uuid.UUID, topic: Topic, area_id: uuid.UUID
    ) -> UserTopicProgress:
        fila = self.db.execute(
            sa.select(UserTopicProgress).where(
                UserTopicProgress.user_id == user_id,
                UserTopicProgress.topic_id == topic.id,
            )
        ).scalar_one_or_none()
        if fila is None:
            fila = UserTopicProgress(
                user_id=user_id,
                topic_id=topic.id,
                knowledge_area_id=area_id,
                module_id=topic.module_id,
            )
            self.db.add(fila)
            self.db.flush()
        return fila

    # -- recálculo --------------------------------------------------------

    def recalcular_tema(
        self,
        user_id: uuid.UUID,
        topic_id: uuid.UUID,
        *,
        ahora: datetime | None = None,
    ) -> tuple[UserTopicProgress, float, float, bool]:
        """Recalcula `user_topic_progress` de un tema.

        Devuelve `(fila, antes, después, debilidad_nueva)`. El último valor es la
        **transición** a débil, no el estado: solo es cierto en el recálculo que
        cruza el umbral, que es cuando `WEAKNESS_DETECTED` tiene algo que contar.
        """
        topic = self.db.get(Topic, topic_id)
        if topic is None:
            raise LookupError(f"El tema {topic_id} no existe.")
        area_id = self._area_de_modulo(topic.module_id)
        fila = self._fila_tema(user_id, topic, area_id)
        antes = a_float(fila.mastery)

        evidencias = self._evidencias_del_tema(user_id, topic_id)
        completadas, totales = self._cobertura_del_tema(user_id, topic_id)
        resultado = calcular_dominio_tema(
            evidencias,
            lecciones_completadas=completadas,
            lecciones_totales=totales,
            stability_s=int(fila.stability_s),
            cfg=self.cfg,
            ahora=ahora,
        )

        aprobada = self._modulo_tiene_evaluacion_aprobada(user_id, topic.module_id)
        fila.practice_score = a_decimal_2(resultado.practice_score)
        fila.coverage = a_decimal_2(resultado.coverage)
        fila.mastery_raw = a_decimal_2(resultado.mastery_raw)
        fila.mastery = a_decimal_2(resultado.mastery)
        fila.evidence_count = resultado.evidence_count
        fila.last_evidence_at = resultado.last_evidence_at
        fila.knowledge_area_id = area_id
        fila.module_id = topic.module_id

        dominado = es_tema_dominado(resultado.mastery, evaluacion_aprobada=aprobada, cfg=self.cfg)
        if dominado and fila.ever_mastered_at is None:
            fila.ever_mastered_at = ensure_utc(ahora) if ahora else utcnow()
        fila.status = estado_dominio(
            resultado.mastery,
            ever_mastered=fila.ever_mastered_at is not None,
            evidencias=resultado.evidence_count,
            lecciones_completadas=completadas,
            requisito_cumplido=aprobada,
            cfg=self.cfg,
        )
        debilidad_nueva = bool(resultado.is_weak) and not bool(fila.is_weak)
        if debilidad_nueva:
            fila.weak_detected_at = ensure_utc(ahora) if ahora else utcnow()
            fila.weak_rule = "R2"
        fila.is_weak = resultado.is_weak
        self.db.flush()
        return fila, antes, resultado.mastery, debilidad_nueva

    def recalcular_modulo(
        self, user_id: uuid.UUID, module_id: uuid.UUID, *, ahora: datetime | None = None
    ) -> tuple[UserModuleProgress, float, float]:
        """Recalcula `user_module_progress.mastery` (`M_mod`). Devuelve `(fila, antes, después)`."""
        modulo = self.db.get(PathModule, module_id)
        if modulo is None:
            raise LookupError(f"El módulo {module_id} no existe.")

        # Temas del módulo con su dominio materializado y su peso en lecciones.
        stmt = (
            sa.select(
                Topic.id,
                sa.func.coalesce(UserTopicProgress.mastery, 0),
                sa.func.count(Lesson.id),
            )
            .select_from(Topic)
            .outerjoin(
                UserTopicProgress,
                sa.and_(
                    UserTopicProgress.topic_id == Topic.id,
                    UserTopicProgress.user_id == user_id,
                ),
            )
            .outerjoin(Lesson, Lesson.topic_id == Topic.id)
            .where(Topic.module_id == module_id)
            .group_by(Topic.id, UserTopicProgress.mastery)
        )
        temas = [
            TemaPonderado(topic_id=tid, mastery=a_float(m), lecciones=int(n))
            for tid, m, n in self.db.execute(stmt)
        ]
        puntajes = self._puntajes_del_modulo(user_id, module_id)
        dominio = calcular_dominio_modulo(temas, puntajes, self.cfg)

        fila = self._fila_modulo(user_id, modulo)
        antes = a_float(fila.mastery)
        fila.mean_topic_mastery = a_decimal_2(dominio.media_temas)
        fila.mastery = a_decimal_2(dominio.mastery)
        fila.assessment_attempts = dominio.intentos
        if dominio.mejor_puntaje is not None:
            fila.assessment_best_score = a_decimal_2(dominio.mejor_puntaje)
            fila.assessment_best_effective = a_decimal_2(dominio.puntaje_efectivo)
        if dominio.aprobado and fila.assessment_passed_at is None:
            fila.assessment_passed_at = ensure_utc(ahora) if ahora else utcnow()
        if dominio.dominado:
            if fila.mastered_at is None:
                fila.mastered_at = ensure_utc(ahora) if ahora else utcnow()
            fila.status = ModuleStatus.MASTERED
        elif fila.status == ModuleStatus.MASTERED:
            fila.status = ModuleStatus.COMPLETED
        self.db.flush()
        return fila, antes, dominio.mastery

    def recalcular_area(
        self, user_id: uuid.UUID, knowledge_area_id: uuid.UUID, *, ahora: datetime | None = None
    ) -> tuple[UserAreaProgress, float, float]:
        """Recalcula `user_area_progress.mastery` (`M_area`) sobre todas las rutas activas."""
        stmt = (
            sa.select(
                PathModule.id,
                sa.func.coalesce(UserModuleProgress.mastery, 0),
                sa.func.coalesce(PathModule.lesson_count, 0),
            )
            .select_from(PathModule)
            .join(LearningPath, LearningPath.id == PathModule.learning_path_id)
            .outerjoin(
                UserModuleProgress,
                sa.and_(
                    UserModuleProgress.module_id == PathModule.id,
                    UserModuleProgress.user_id == user_id,
                ),
            )
            .where(
                LearningPath.knowledge_area_id == knowledge_area_id,
                LearningPath.status != PathStatus.ARCHIVED,
                sa.or_(LearningPath.user_id == user_id, LearningPath.user_id.is_(None)),
            )
        )
        modulos = [
            ModuloPonderado(module_id=mid, mastery=a_float(m), lecciones=int(n))
            for mid, m, n in self.db.execute(stmt)
        ]
        m_area = agregar_dominio_area(modulos)

        fila = self._fila_area(user_id, knowledge_area_id)
        antes = a_float(fila.mastery)

        rutas_completadas = self.db.execute(
            sa.select(sa.func.count(UserPathProgress.id))
            .join(LearningPath, LearningPath.id == UserPathProgress.learning_path_id)
            .where(
                UserPathProgress.user_id == user_id,
                UserPathProgress.status == ProgressState.COMPLETED,
                LearningPath.knowledge_area_id == knowledge_area_id,
            )
        ).scalar_one()

        temas_dominados = self.db.execute(
            sa.select(sa.func.count(UserTopicProgress.id)).where(
                UserTopicProgress.user_id == user_id,
                UserTopicProgress.knowledge_area_id == knowledge_area_id,
                UserTopicProgress.status == KnowledgeAreaStatus.MASTERED,
            )
        ).scalar_one()

        modulos_dominados = sum(1 for m in modulos if m.mastery >= self.cfg.umbral_dominado)
        dominada = es_area_dominada(
            m_area, tiene_ruta_completada=int(rutas_completadas) > 0, cfg=self.cfg
        )

        fila.mastery = a_decimal_2(m_area)
        fila.modules_total = len(modulos)
        fila.modules_mastered = modulos_dominados
        fila.topics_mastered = int(temas_dominados)
        fila.paths_completed = int(rutas_completadas)
        if dominada and fila.mastered_at is None:
            fila.mastered_at = ensure_utc(ahora) if ahora else utcnow()
        fila.status = estado_dominio(
            m_area,
            ever_mastered=fila.mastered_at is not None,
            evidencias=int(temas_dominados) + len(modulos),
            lecciones_completadas=1 if m_area > 0 else 0,
            requisito_cumplido=dominada,
            cfg=self.cfg,
        )
        self.db.flush()
        return fila, antes, m_area

    def recalcular_cascada(
        self,
        user_id: uuid.UUID,
        *,
        topic_id: uuid.UUID | None = None,
        module_id: uuid.UUID | None = None,
        knowledge_area_id: uuid.UUID | None = None,
        ahora: datetime | None = None,
        emitir_eventos: bool = True,
        correlation_id: uuid.UUID | None = None,
        timezone_name: str | None = None,
    ) -> ResultadoRecalculo:
        """Recalcula tema → módulo → conocimiento y emite los eventos de dominio (§4).

        Es la entrada que usan los productores de evidencias: responder una pregunta,
        completar una lección, enviar una evaluación o terminar un repaso.
        """
        resultado = ResultadoRecalculo()
        momento = ensure_utc(ahora) if ahora else utcnow()

        if topic_id is not None:
            tema = self.db.get(Topic, topic_id)
            if tema is not None:
                module_id = module_id or tema.module_id
            fila_tema, antes, despues, debil = self.recalcular_tema(
                user_id, topic_id, ahora=momento
            )
            resultado.weakness_detected = debil
            resultado.topic_id = topic_id
            resultado.topic_before = antes
            resultado.topic_after = despues
            resultado.topic_status = fila_tema.status
            knowledge_area_id = knowledge_area_id or fila_tema.knowledge_area_id

        if module_id is not None:
            fila_mod, antes, despues = self.recalcular_modulo(user_id, module_id, ahora=momento)
            resultado.module_id = module_id
            resultado.module_before = antes
            resultado.module_after = despues
            resultado.module_status = fila_mod.status
            knowledge_area_id = knowledge_area_id or self._area_de_modulo(module_id)

        if knowledge_area_id is not None:
            fila_area, antes, despues = self.recalcular_area(user_id, knowledge_area_id, ahora=momento)
            resultado.knowledge_area_id = knowledge_area_id
            resultado.area_before = antes
            resultado.area_after = despues
            resultado.area_status = fila_area.status
            resultado.topics_mastered = int(fila_area.topics_mastered)
            resultado.areas_mastered = int(
                self.db.execute(
                    sa.select(sa.func.count(UserAreaProgress.id)).where(
                        UserAreaProgress.user_id == user_id,
                        UserAreaProgress.status == KnowledgeAreaStatus.MASTERED,
                    )
                ).scalar_one()
            )

        if emitir_eventos:
            self._emitir_eventos_dominio(
                user_id,
                resultado,
                momento=momento,
                correlation_id=correlation_id,
                timezone_name=timezone_name,
            )
        return resultado

    def registrar_repaso(
        self,
        user_id: uuid.UUID,
        topic_id: uuid.UUID,
        puntaje_repaso: float,
        *,
        ahora: datetime | None = None,
    ) -> UserTopicProgress:
        """Aplica la recuperación por repaso (§6.5).

        Un repaso con `P_repaso >= mastery.review.stability_min_score` incrementa
        `stability_s` (alarga la media vida del olvido) y, al haber evidencia nueva,
        `Δ` vuelve a 0 en el siguiente recálculo.
        """
        fila = self.db.execute(
            sa.select(UserTopicProgress).where(
                UserTopicProgress.user_id == user_id,
                UserTopicProgress.topic_id == topic_id,
            )
        ).scalar_one_or_none()
        if fila is None:
            tema = self.db.get(Topic, topic_id)
            if tema is None:
                raise LookupError(f"El tema {topic_id} no existe.")
            fila = self._fila_tema(user_id, tema, self._area_de_modulo(tema.module_id))
        if puntaje_repaso >= self.cfg.repaso_puntaje_min_estabilidad:
            fila.stability_s = int(fila.stability_s) + 1
        fila.last_evidence_at = ensure_utc(ahora) if ahora else utcnow()
        self.db.flush()
        return fila

    # -- utilidades internas ---------------------------------------------

    def _area_de_modulo(self, module_id: uuid.UUID | None) -> uuid.UUID | None:
        if module_id is None:
            return None
        return self.db.execute(
            sa.select(LearningPath.knowledge_area_id)
            .join(PathModule, PathModule.learning_path_id == LearningPath.id)
            .where(PathModule.id == module_id)
        ).scalar_one_or_none()

    def _modulo_tiene_evaluacion_aprobada(
        self, user_id: uuid.UUID, module_id: uuid.UUID | None
    ) -> bool:
        if module_id is None:
            return False
        mejor = self.db.execute(
            sa.select(sa.func.max(AssessmentAttempt.score)).where(
                AssessmentAttempt.user_id == user_id,
                AssessmentAttempt.module_id == module_id,
                AssessmentAttempt.status == AttemptStatus.SUBMITTED,
            )
        ).scalar_one_or_none()
        return mejor is not None and a_float(mejor) >= self.cfg.puntaje_aprobacion

    def _fila_modulo(self, user_id: uuid.UUID, modulo: PathModule) -> UserModuleProgress:
        fila = self.db.execute(
            sa.select(UserModuleProgress).where(
                UserModuleProgress.user_id == user_id,
                UserModuleProgress.module_id == modulo.id,
            )
        ).scalar_one_or_none()
        if fila is None:
            fila = UserModuleProgress(
                user_id=user_id,
                module_id=modulo.id,
                learning_path_id=modulo.learning_path_id,
                lessons_total=int(modulo.lesson_count or 0),
            )
            self.db.add(fila)
            self.db.flush()
        return fila

    def _fila_area(self, user_id: uuid.UUID, knowledge_area_id: uuid.UUID) -> UserAreaProgress:
        fila = self.db.execute(
            sa.select(UserAreaProgress).where(
                UserAreaProgress.user_id == user_id,
                UserAreaProgress.knowledge_area_id == knowledge_area_id,
            )
        ).scalar_one_or_none()
        if fila is None:
            fila = UserAreaProgress(user_id=user_id, knowledge_area_id=knowledge_area_id)
            self.db.add(fila)
            self.db.flush()
        return fila

    def _emitir_eventos_dominio(
        self,
        user_id: uuid.UUID,
        resultado: ResultadoRecalculo,
        *,
        momento: datetime,
        correlation_id: uuid.UUID | None,
        timezone_name: str | None,
    ) -> None:
        """Inserta `MASTERY_UPDATED` y, si procede, los eventos de hito (§4.2)."""
        marca = int(momento.timestamp())
        payload = {
            "topic_id": str(resultado.topic_id) if resultado.topic_id else None,
            "module_id": str(resultado.module_id) if resultado.module_id else None,
            "knowledge_area_id": (
                str(resultado.knowledge_area_id) if resultado.knowledge_area_id else None
            ),
            "topic_before": resultado.topic_before,
            "topic_after": resultado.topic_after,
            "module_after": resultado.module_after,
            "area_before": resultado.area_before,
            "area_after": resultado.area_after,
            "topics_mastered": resultado.topics_mastered,
            "areas_mastered": resultado.areas_mastered,
        }
        self._insertar_evento(
            EventType.MASTERY_UPDATED,
            user_id,
            payload,
            clave=f"mastery-updated:{user_id}:{resultado.topic_id or resultado.module_id}:{marca}",
            momento=momento,
            correlation_id=correlation_id,
            timezone_name=timezone_name,
        )
        resultado.eventos.append(EventType.MASTERY_UPDATED)

        if resultado.topic_status == KnowledgeAreaStatus.MASTERED and resultado.topic_id:
            self._insertar_evento(
                EventType.TOPIC_MASTERED,
                user_id,
                {
                    "topic_id": str(resultado.topic_id),
                    "knowledge_area_id": (
                        str(resultado.knowledge_area_id) if resultado.knowledge_area_id else None
                    ),
                    "mastery": resultado.topic_after,
                },
                clave=f"topic-mastered:{user_id}:{resultado.topic_id}:1",
                momento=momento,
                correlation_id=correlation_id,
                timezone_name=timezone_name,
                permitir_duplicado=True,
            )
            resultado.eventos.append(EventType.TOPIC_MASTERED)

        if resultado.module_status == ModuleStatus.MASTERED and resultado.module_id:
            self._insertar_evento(
                EventType.MODULE_MASTERED,
                user_id,
                {
                    "module_id": str(resultado.module_id),
                    "knowledge_area_id": (
                        str(resultado.knowledge_area_id) if resultado.knowledge_area_id else None
                    ),
                    "mastery": resultado.module_after,
                },
                clave=f"module-mastered:{user_id}:{resultado.module_id}:1",
                momento=momento,
                correlation_id=correlation_id,
                timezone_name=timezone_name,
                permitir_duplicado=True,
            )
            resultado.eventos.append(EventType.MODULE_MASTERED)

        if resultado.area_status == KnowledgeAreaStatus.MASTERED and resultado.knowledge_area_id:
            self._insertar_evento(
                EventType.AREA_MASTERED,
                user_id,
                {
                    "knowledge_area_id": str(resultado.knowledge_area_id),
                    "mastery": resultado.area_after,
                },
                clave=f"area-mastered:{user_id}:{resultado.knowledge_area_id}:1",
                momento=momento,
                correlation_id=correlation_id,
                timezone_name=timezone_name,
                permitir_duplicado=True,
            )
            resultado.eventos.append(EventType.AREA_MASTERED)

        # El territorio del mapa sale de la niebla la primera vez que el aprendiz
        # gana dominio en ese conocimiento: es la misma condición que usa
        # `estado_territorio` para pasar de FOGGED a DISCOVERED. `TERRITORY_UNLOCKED`
        # estaba en el catálogo de eventos y había un logro contándolo, pero no lo
        # emitía nadie: ese logro no podía desbloquearse jamás.
        if (
            resultado.knowledge_area_id
            and resultado.area_after > 0
            and resultado.area_before <= 0
        ):
            self._insertar_evento(
                EventType.TERRITORY_UNLOCKED,
                user_id,
                {
                    "knowledge_area_id": str(resultado.knowledge_area_id),
                    "territory_id": self._territorio_de(resultado.knowledge_area_id),
                    "mastery": resultado.area_after,
                },
                # Una sola vez por conocimiento y aprendiz, para siempre: un
                # dominio que baje a cero y vuelva a subir no redescubre el mapa.
                clave=f"territory-unlocked:{user_id}:{resultado.knowledge_area_id}:1",
                momento=momento,
                correlation_id=correlation_id,
                timezone_name=timezone_name,
                permitir_duplicado=True,
            )
            resultado.eventos.append(EventType.TERRITORY_UNLOCKED)

        if resultado.weakness_detected and resultado.topic_id:
            self._insertar_evento(
                EventType.WEAKNESS_DETECTED,
                user_id,
                {
                    "topic_id": str(resultado.topic_id),
                    "knowledge_area_id": (
                        str(resultado.knowledge_area_id) if resultado.knowledge_area_id else None
                    ),
                    "rule": "R2",
                    "evidence": {"mastery": resultado.topic_after},
                },
                clave=f"weakness-detected:{user_id}:{resultado.topic_id}:{marca}",
                momento=momento,
                correlation_id=correlation_id,
                timezone_name=timezone_name,
            )
            resultado.eventos.append(EventType.WEAKNESS_DETECTED)
            self._proponer_repaso(user_id, resultado.topic_id, marca)

    def _territorio_de(self, knowledge_area_id: uuid.UUID) -> str | None:
        """Territorio del mapa que representa a ese conocimiento (1:1)."""
        from app.models.content import Territory  # noqa: PLC0415 - evita el ciclo

        encontrado = self.db.execute(
            sa.select(Territory.id).where(Territory.knowledge_area_id == knowledge_area_id)
        ).scalar_one_or_none()
        return str(encontrado) if encontrado else None

    def _proponer_repaso(self, user_id: uuid.UUID, topic_id: uuid.UUID, marca: int) -> None:
        """Aviso de repaso del tema que acaba de marcarse débil (§4.2).

        Es la puerta que le faltaba al repaso espaciado: hasta ahora las
        sugerencias solo existían en la pantalla de resultado de una evaluación,
        y quien no llegaba hasta ahí no las veía jamás.
        """
        from app.modules.gamification import avisos  # noqa: PLC0415 - evita el ciclo de importación

        tema = self.db.get(Topic, topic_id)
        if tema is None:
            return
        avisos.al_detectar_debilidad(
            db=self.db,
            usuario_id=user_id,
            topic_id=topic_id,
            titulo=tema.title,
            marca=marca,
        )

    def _insertar_evento(
        self,
        event_type: EventType,
        user_id: uuid.UUID,
        payload: dict,
        *,
        clave: str,
        momento: datetime,
        correlation_id: uuid.UUID | None = None,
        timezone_name: str | None = None,
        permitir_duplicado: bool = False,
    ) -> None:
        """Inserta una fila de `domain_events` respetando la unicidad de la clave (§8.3)."""
        if permitir_duplicado:
            existe = self.db.execute(
                sa.select(sa.literal(1))
                .select_from(DomainEvent)
                .where(DomainEvent.idempotency_key == clave)
                .limit(1)
            ).scalar_one_or_none()
            if existe:
                return
        self.db.add(
            DomainEvent(
                event_type=event_type,
                user_id=user_id,
                occurred_at=momento,
                timezone=timezone_name,
                source_module="progress",
                payload=payload,
                correlation_id=correlation_id,
                idempotency_key=clave,
            )
        )
        self.db.flush()

__all__ = [
    "CLAVES_DOMINIO",
    "ConfigDominio",
    "DominioModulo",
    "DominioTema",
    "Evidencia",
    "ModuloPonderado",
    "ResultadoRecalculo",
    "ServicioDominio",
    "TemaPonderado",
    "agregar_dominio_area",
    "calcular_dominio_modulo",
    "calcular_dominio_tema",
    "cobertura",
    "es_area_dominada",
    "es_tema_debil",
    "es_tema_dominado",
    "estado_dominio",
    "factor_cobertura",
    "factor_decaimiento",
    "media_vida_decaimiento",
    "peso_contexto",
    "peso_de_acierto",
    "peso_dificultad",
    "peso_recencia",
    "peso_reintento",
    "precision_ponderada",
    "promedio_ponderado_temas",
    "puntaje_efectivo_evaluacion",
    "seleccionar_evidencias",
]
