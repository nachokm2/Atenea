"""Interfaz del proveedor de IA, enrutamiento por tarea y contabilidad de coste.

Este módulo define el **contrato** que cumplen los dos proveedores de Atenea:

- `app.modules.ai.claude.ProveedorClaude` — el real, contra la API de Anthropic.
- `app.modules.ai.simulado.ProveedorSimulado` — determinista, sin red ni coste, el que
  se usa por defecto en desarrollo y en **todas** las pruebas.

Reglas del contrato que se aplican aquí:

- Los identificadores de modelo viven en `game_configs` (`ai.models`, CONTRACT.md §5.8),
  nunca en el código. `settings` solo es el respaldo cuando la configuración de juego
  todavía no está cargada (base vacía, arranque, pruebas unitarias sin base).
- El material del usuario es **entrada no confiable** (§8.7): nunca viaja en el `system`,
  siempre en bloques delimitados del mensaje de usuario.
- Las llamadas de generación no llevan herramientas.
- Toda llamada contabiliza tokens y coste; el coste se persiste en
  `generation_jobs.cost_usd` (`app.modules.ai.costos`).
"""

from __future__ import annotations

import hashlib
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT, settings
from app.models.enums import JobType
from app.models.ingestion import PromptTemplate
from app.modules.gamification.servicio_config import ServicioConfig

# ---------------------------------------------------------------------------
# Tareas de IA: las claves literales del mapa `ai.models` de CONTRACT.md §5.8
# ---------------------------------------------------------------------------

TAREA_PATH_DESIGN: Final[str] = "path_design"
TAREA_LESSON: Final[str] = "lesson"
TAREA_QUESTIONS: Final[str] = "questions"
TAREA_JUDGE: Final[str] = "judge"
TAREA_JUDGE_ESCALATION: Final[str] = "judge_escalation"
TAREA_NARRATIVE: Final[str] = "narrative"
TAREA_GROUNDEDNESS: Final[str] = "groundedness"

#: La re-explicación no tiene clave propia en `ai.models`: §1.2 la asigna al mismo
#: modelo que las lecciones (`claude-sonnet-5`). Se resuelve por respaldo.
TAREA_REEXPLICACION: Final[str] = "re_explanation"

#: Respaldo de modelo cuando la tarea no tiene clave propia en `ai.models`.
_TAREA_RESPALDO: Final[dict[str, str]] = {
    TAREA_REEXPLICACION: TAREA_LESSON,
    TAREA_JUDGE_ESCALATION: TAREA_LESSON,
}

#: Plantilla de prompt (`prompt_templates.task_type`) que cubre cada tarea.
TAREA_A_JOB_TYPE: Final[dict[str, JobType]] = {
    TAREA_PATH_DESIGN: JobType.PATH_DESIGN,
    TAREA_LESSON: JobType.LESSON_GENERATION,
    TAREA_QUESTIONS: JobType.QUESTION_GENERATION,
    TAREA_JUDGE: JobType.ANSWER_JUDGEMENT,
    TAREA_JUDGE_ESCALATION: JobType.ANSWER_JUDGEMENT,
    TAREA_REEXPLICACION: JobType.RE_EXPLANATION,
    TAREA_NARRATIVE: JobType.NARRATIVE_GENERATION,
    TAREA_GROUNDEDNESS: JobType.GROUNDEDNESS_CHECK,
}

#: Respaldo de `ai.models` cuando `game_configs` aún no está sembrada.
_MODELOS_RESPALDO: Final[dict[str, str]] = {
    TAREA_PATH_DESIGN: settings.ai_model_architect,
    TAREA_LESSON: settings.ai_model_author,
    TAREA_QUESTIONS: settings.ai_model_author,
    TAREA_JUDGE: settings.ai_model_judge,
    TAREA_JUDGE_ESCALATION: settings.ai_model_author,
    TAREA_NARRATIVE: settings.ai_model_judge,
    TAREA_GROUNDEDNESS: settings.ai_model_judge,
}

# ---------------------------------------------------------------------------
# Tarifas del proveedor (infraestructura, no parámetro de juego)
# ---------------------------------------------------------------------------

#: Precio en USD por millón de tokens: (entrada, escritura de caché, lectura de caché,
#: salida). No es un parámetro de juego (§5 no define ninguna clave de precios): es la
#: lista de tarifas del proveedor, necesaria para calcular `generation_jobs.cost_usd`.
#: TODO(contrato): si en el futuro se quiere cambiar sin desplegar, el arquitecto debe
#: añadir una clave `ai.pricing` a CONTRACT.md §5.8; hasta entonces no se inventa.
PRECIOS_USD_POR_MTOK: Final[dict[str, tuple[str, str, str, str]]] = {
    "claude-opus-5": ("5.00", "6.25", "0.50", "25.00"),
    "claude-sonnet-5": ("2.00", "2.50", "0.20", "10.00"),
    "claude-haiku-4-5": ("1.00", "1.25", "0.10", "5.00"),
}

#: Tarifa aplicada a un modelo desconocido: la más cara, para no subestimar el gasto.
PRECIO_POR_DEFECTO: Final[tuple[str, str, str, str]] = PRECIOS_USD_POR_MTOK["claude-opus-5"]

_MILLON: Final[Decimal] = Decimal(1_000_000)


def precio_de_modelo(model_id: str) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Devuelve las cuatro tarifas del modelo en USD por millón de tokens."""
    entrada, escritura, lectura, salida = PRECIOS_USD_POR_MTOK.get(model_id, PRECIO_POR_DEFECTO)
    return Decimal(entrada), Decimal(escritura), Decimal(lectura), Decimal(salida)


def calcular_coste(
    model_id: str,
    *,
    input_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
) -> Decimal:
    """Coste en USD de una llamada, con 6 decimales (`generation_jobs.cost_usd`)."""
    p_in, p_cache_w, p_cache_r, p_out = precio_de_modelo(model_id)
    total = (
        Decimal(input_tokens) * p_in
        + Decimal(cache_creation_tokens) * p_cache_w
        + Decimal(cached_input_tokens) * p_cache_r
        + Decimal(output_tokens) * p_out
    ) / _MILLON
    return total.quantize(Decimal("0.000001"))


# ---------------------------------------------------------------------------
# Contabilidad de una llamada
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UsoIA:
    """Tokens y coste de **una** llamada al proveedor.

    `input_tokens` incluye la escritura de caché, porque `generation_jobs` solo tiene
    tres columnas de tokens (§3.3); `cache_creation_tokens` se conserva aparte para que
    el coste se calcule con su tarifa real (×1.25).
    """

    model_id: str
    provider: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: Decimal = Decimal("0")

    @property
    def total_tokens(self) -> int:
        """Tokens totales de la llamada (entrada + caché leída + salida)."""
        return self.input_tokens + self.cached_input_tokens + self.output_tokens

    def __add__(self, otro: UsoIA) -> UsoIA:
        """Suma dos usos; conserva el modelo del primero y el proveedor común."""
        return UsoIA(
            model_id=self.model_id or otro.model_id,
            provider=self.provider or otro.provider,
            input_tokens=self.input_tokens + otro.input_tokens,
            cached_input_tokens=self.cached_input_tokens + otro.cached_input_tokens,
            output_tokens=self.output_tokens + otro.output_tokens,
            cache_creation_tokens=self.cache_creation_tokens + otro.cache_creation_tokens,
            cost_usd=self.cost_usd + otro.cost_usd,
        )


def uso_vacio(model_id: str = "", provider: str = "") -> UsoIA:
    """Uso neutro: el acumulador inicial de una suma de llamadas."""
    return UsoIA(model_id=model_id, provider=provider)


@dataclass(frozen=True, slots=True)
class RespuestaIA:
    """Salida del proveedor: contenido ya parseado, más la contabilidad de la llamada."""

    contenido: Any
    uso: UsoIA
    tarea: str
    reintentos: int = 0
    texto_bruto: str = ""


@dataclass(slots=True)
class ContadorUso:
    """Acumulador de tokens y coste de todas las llamadas de un proveedor."""

    llamadas: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    por_tarea: dict[str, int] = field(default_factory=dict)

    def registrar(self, uso: UsoIA, tarea: str = "") -> None:
        """Suma una llamada al acumulado."""
        self.llamadas += 1
        self.input_tokens += uso.input_tokens
        self.cached_input_tokens += uso.cached_input_tokens
        self.output_tokens += uso.output_tokens
        self.cache_creation_tokens += uso.cache_creation_tokens
        self.cost_usd += uso.cost_usd
        if tarea:
            self.por_tarea[tarea] = self.por_tarea.get(tarea, 0) + 1

    def como_dict(self) -> dict[str, Any]:
        """Representación serializable (para `generation_jobs.result`)."""
        return {
            "calls": self.llamadas,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": str(self.cost_usd),
            "by_task": dict(self.por_tarea),
        }


# ---------------------------------------------------------------------------
# Contexto y solicitud
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FragmentoContexto:
    """Fragmento recuperado del material del usuario, con su trazabilidad.

    Es la unidad que respalda cada pieza generada: viaja al prompt como bloque
    delimitado y se persiste en `content_provenance`.
    """

    chunk_id: uuid.UUID
    text: str
    document_id: uuid.UUID | None = None
    document_version_id: uuid.UUID | None = None
    document_title: str = ""
    heading_path: tuple[str, ...] = ()
    page_start: int | None = None
    page_end: int | None = None
    chunk_type: str = "prose"
    rank: int = 0
    score: float = 0.0

    @property
    def etiqueta(self) -> str:
        """Identificador corto y estable que la IA cita en `source_chunk_ids`."""
        return str(self.chunk_id)

    def como_bloque(self) -> str:
        """Renderiza el fragmento como bloque delimitado del mensaje de usuario."""
        ruta = " > ".join(self.heading_path) if self.heading_path else ""
        cabecera = f"[fragmento: {self.etiqueta}]"
        if self.document_title:
            cabecera += f" [documento: {self.document_title}]"
        if ruta:
            cabecera += f" [sección: {ruta}]"
        if self.page_start is not None:
            fin = self.page_end if self.page_end is not None else self.page_start
            cabecera += f" [páginas: {self.page_start}-{fin}]"
        return f"{cabecera}\n{self.text.strip()}"


def bloque_material(fragmentos: list[FragmentoContexto]) -> str:
    """Envuelve los fragmentos en `<material>` (entrada no confiable, §8.7)."""
    if not fragmentos:
        return "<material>\n(sin material: apóyate en tu propio conocimiento)\n</material>"
    cuerpo = "\n\n".join(fragmento.como_bloque() for fragmento in fragmentos)
    return f"<material>\n{cuerpo}\n</material>"


@dataclass(slots=True)
class SolicitudIA:
    """Encargo completo de una llamada al proveedor.

    `sistema` es el cuerpo de la plantilla de prompt: contenido **estable**, apto para
    la caché de prefijo. `instruccion` y `fragmentos` son lo variable y viajan en el
    mensaje de usuario.
    """

    tarea: str
    sistema: str
    instruccion: str
    fragmentos: list[FragmentoContexto] = field(default_factory=list)
    datos: dict[str, Any] = field(default_factory=dict)
    esquema: dict[str, Any] | None = None
    modelo: str = ""
    max_tokens: int = 8_000
    esfuerzo: str | None = None
    plantilla_id: uuid.UUID | None = None
    semilla: str = ""

    def mensaje_usuario(self) -> str:
        """Mensaje de usuario: instrucción + material delimitado."""
        partes = [self.instruccion.strip(), bloque_material(self.fragmentos)]
        return "\n\n".join(parte for parte in partes if parte)

    def huella(self) -> str:
        """Huella determinista de la solicitud (semilla del proveedor simulado)."""
        crudo = "|".join(
            [
                self.tarea,
                self.semilla,
                self.instruccion,
                repr(sorted(self.datos.items(), key=lambda par: par[0])),
                ",".join(fragmento.etiqueta for fragmento in self.fragmentos),
            ]
        )
        return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------


class ProveedorIA(ABC):
    """Contrato común de los proveedores de IA de Atenea."""

    #: Nombre corto que se persiste en `generation_jobs.provider`.
    nombre: str = "desconocido"

    def __init__(self) -> None:
        self.contador = ContadorUso()

    @abstractmethod
    def generar_estructurado(self, solicitud: SolicitudIA) -> RespuestaIA:
        """Genera una salida JSON validada contra `solicitud.esquema`.

        `RespuestaIA.contenido` es un `dict` ya parseado. El proveedor **no** valida
        contra el esquema Pydantic: de eso se encarga `esquemas_salida.generar_validado`,
        que reintenta de forma acotada cuando la salida no valida.
        """

    @abstractmethod
    def generar_texto(self, solicitud: SolicitudIA) -> RespuestaIA:
        """Genera texto libre. `RespuestaIA.contenido` es un `str`."""

    # -- contabilidad ----------------------------------------------------
    def _anotar(self, uso: UsoIA, tarea: str) -> UsoIA:
        """Registra el uso de una llamada en el contador del proveedor."""
        self.contador.registrar(uso, tarea)
        return uso

    @property
    def uso_acumulado(self) -> ContadorUso:
        """Contabilidad acumulada de todas las llamadas hechas por este proveedor."""
        return self.contador

    def reiniciar_contador(self) -> None:
        """Vacía el acumulado (útil entre trabajos de generación distintos)."""
        self.contador = ContadorUso()


# ---------------------------------------------------------------------------
# Enrutamiento por configuración
# ---------------------------------------------------------------------------


def modelo_para_tarea(cfg: ServicioConfig | None, tarea: str) -> str:
    """Resuelve el identificador de modelo de una tarea desde `ai.models` (§5.8)."""
    mapa: dict[str, Any] = {}
    if cfg is not None:
        mapa = cfg.obtener_json("ai.models", {}) or {}
    clave = tarea if tarea in mapa else _TAREA_RESPALDO.get(tarea, tarea)
    modelo = mapa.get(clave)
    if isinstance(modelo, str) and modelo:
        return modelo
    respaldo = _MODELOS_RESPALDO.get(clave) or _MODELOS_RESPALDO.get(tarea)
    return respaldo or settings.ai_model_author


# ---------------------------------------------------------------------------
# Plantillas de prompt (`app/prompts/` + tabla `prompt_templates`)
# ---------------------------------------------------------------------------

DIRECTORIO_PROMPTS: Final[Path] = BACKEND_ROOT / "app" / "prompts"


@dataclass(frozen=True, slots=True)
class PlantillaPrompt:
    """Plantilla de prompt cargada de disco o de `prompt_templates`."""

    task_type: JobType
    version: str
    body: str
    content_hash: str
    id: uuid.UUID | None = None
    default_model: str = ""
    max_tokens: int | None = None
    effort: str | None = None


def _hash_cuerpo(cuerpo: str) -> str:
    """SHA-256 del cuerpo del prompt (detecta ediciones no versionadas)."""
    return hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()


@lru_cache(maxsize=32)
def cargar_plantilla_archivo(task_type: JobType, version: str | None = None) -> PlantillaPrompt:
    """Carga `app/prompts/<task_type>.<version>.md` (la mayor versión si no se indica)."""
    patron = f"{task_type.value}.*.md"
    candidatos = sorted(DIRECTORIO_PROMPTS.glob(patron))
    if not candidatos:
        raise FileNotFoundError(
            f"No hay plantilla de prompt para {task_type.value} en {DIRECTORIO_PROMPTS}"
        )
    elegido = candidatos[-1]
    if version:
        for ruta in candidatos:
            if ruta.name == f"{task_type.value}.{version}.md":
                elegido = ruta
                break
        else:  # pragma: no cover - versión inexistente en disco
            raise FileNotFoundError(f"No existe la versión {version} de {task_type.value}")
    cuerpo = elegido.read_text(encoding="utf-8")
    # "lesson_generation.v1.md" -> "v1"
    version_archivo = elegido.name[len(task_type.value) + 1 : -len(".md")]
    return PlantillaPrompt(
        task_type=task_type,
        version=version_archivo,
        body=cuerpo,
        content_hash=_hash_cuerpo(cuerpo),
    )


def catalogo_de_plantillas() -> list[PlantillaPrompt]:
    """Todas las plantillas versionadas de `app/prompts/`, con su `content_hash`.

    Es lo que necesita el agente de semillas para poblar `prompt_templates` en el
    despliegue sin duplicar la lógica de carga ni recalcular el hash a mano.
    """
    plantillas: list[PlantillaPrompt] = []
    for ruta in sorted(DIRECTORIO_PROMPTS.glob("*.*.md")):
        nombre_tarea = ruta.name.split(".", 1)[0]
        try:
            task_type = JobType(nombre_tarea)
        except ValueError:  # pragma: no cover - archivo ajeno al catálogo
            continue
        cuerpo = ruta.read_text(encoding="utf-8")
        plantillas.append(
            PlantillaPrompt(
                task_type=task_type,
                version=ruta.name[len(nombre_tarea) + 1 : -len(".md")],
                body=cuerpo,
                content_hash=_hash_cuerpo(cuerpo),
            )
        )
    return plantillas


def plantilla_para_tarea(
    db: Session | None, tarea: str, *, version: str | None = None
) -> PlantillaPrompt:
    """Plantilla activa de la tarea: primero `prompt_templates`, si no el archivo.

    La tabla manda en producción (es lo que permite auditar y reproducir); el archivo es
    la fuente de verdad del repositorio y el respaldo cuando la semilla no está cargada.
    """
    task_type = TAREA_A_JOB_TYPE.get(tarea, JobType.LESSON_GENERATION)
    if db is not None:
        consulta = sa.select(PromptTemplate).where(
            PromptTemplate.task_type == task_type,
            PromptTemplate.is_active.is_(True),
        )
        if version:
            consulta = consulta.where(PromptTemplate.version == version)
        fila = db.execute(consulta.order_by(PromptTemplate.version.desc()).limit(1)).scalar_one_or_none()
        if fila is not None:
            return PlantillaPrompt(
                task_type=task_type,
                version=fila.version,
                body=fila.body,
                content_hash=fila.content_hash,
                id=fila.id,
                default_model=fila.default_model,
                max_tokens=fila.max_tokens,
                effort=fila.effort,
            )
    return cargar_plantilla_archivo(task_type, version)


# ---------------------------------------------------------------------------
# Fábrica
# ---------------------------------------------------------------------------


def crear_proveedor(nombre: str | None = None, *, cfg: ServicioConfig | None = None) -> ProveedorIA:
    """Fábrica de proveedores.

    Sin argumentos usa `settings.ai_provider` (`mock` por defecto en desarrollo y en
    todas las pruebas). El proveedor real solo se construye si hay clave de API.
    """
    elegido = (nombre or settings.ai_provider or "mock").lower()
    if elegido in ("mock", "simulado", "fake"):
        from app.modules.ai.simulado import ProveedorSimulado

        return ProveedorSimulado(cfg=cfg)
    if elegido in ("claude", "anthropic"):
        from app.modules.ai.claude import ProveedorClaude

        return ProveedorClaude(cfg=cfg)
    raise ValueError(f"Proveedor de IA desconocido: {nombre!r}")


__all__ = [
    "DIRECTORIO_PROMPTS",
    "PRECIOS_USD_POR_MTOK",
    "TAREA_A_JOB_TYPE",
    "TAREA_GROUNDEDNESS",
    "TAREA_JUDGE",
    "TAREA_JUDGE_ESCALATION",
    "TAREA_LESSON",
    "TAREA_NARRATIVE",
    "TAREA_PATH_DESIGN",
    "TAREA_QUESTIONS",
    "TAREA_REEXPLICACION",
    "ContadorUso",
    "FragmentoContexto",
    "PlantillaPrompt",
    "ProveedorIA",
    "RespuestaIA",
    "SolicitudIA",
    "UsoIA",
    "bloque_material",
    "calcular_coste",
    "cargar_plantilla_archivo",
    "catalogo_de_plantillas",
    "crear_proveedor",
    "modelo_para_tarea",
    "plantilla_para_tarea",
    "precio_de_modelo",
    "uso_vacio",
]
