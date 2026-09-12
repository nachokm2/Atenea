"""Proveedor de IA simulado: determinista, sin red y sin coste.

Es el proveedor **por defecto** en desarrollo y en **todas** las pruebas
(`settings.ai_provider = "mock"`). No inventa contenido de la nada: construye la salida
a partir de los fragmentos recuperados del material y de los datos estructurados que le
pasa cada módulo (`SolicitudIA.datos`), de modo que:

- la misma solicitud produce siempre exactamente la misma salida (no hay azar);
- la salida cumple el esquema estricto de la tarea, así que las pruebas ejercitan el
  mismo camino de validación y persistencia que el proveedor real;
- el juez puntúa de verdad (compara la respuesta con la rúbrica), no devuelve un
  veredicto fijo.

Contabiliza tokens estimados para que la contabilidad de coste se pueda probar, pero el
coste es siempre 0: no hay llamada externa.
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal
from typing import Any

from app.models.enums import CoverageLevel, DifficultyLevel, LessonBlockType, QuestionType
from app.modules.ai.proveedor import (
    ProveedorIA,
    RespuestaIA,
    SolicitudIA,
    UsoIA,
    modelo_para_tarea,
)
from app.modules.gamification.servicio_config import ServicioConfig

_TIPOS_POR_DEFECTO: tuple[str, ...] = (
    QuestionType.MULTIPLE_CHOICE.value,
    QuestionType.TRUE_FALSE.value,
    QuestionType.FILL_BLANK.value,
    QuestionType.MATCHING.value,
    QuestionType.ORDERING.value,
)


def _normalizar(texto: str) -> str:
    """Minúsculas sin acentos, para comparar de forma robusta."""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(caracter for caracter in descompuesto if unicodedata.category(caracter) != "Mn")


def _tokens_estimados(texto: str) -> int:
    """Estimación grosera de tokens (≈ 4 caracteres por token)."""
    return max(1, len(texto) // 4)


def _frases(texto: str, maximo: int = 3) -> list[str]:
    """Primeras frases útiles de un fragmento, ya limpias."""
    limpio = " ".join(texto.split())
    trozos = [parte.strip() for parte in limpio.replace("\n", " ").split(".") if parte.strip()]
    return trozos[:maximo]


class ProveedorSimulado(ProveedorIA):
    """Proveedor determinista que no toca la red ni gasta un céntimo."""

    nombre = "mock"

    def __init__(self, *, cfg: ServicioConfig | None = None) -> None:
        super().__init__()
        self.cfg = cfg

    # ------------------------------------------------------------------
    # Interfaz
    # ------------------------------------------------------------------
    def generar_estructurado(self, solicitud: SolicitudIA) -> RespuestaIA:
        """Construye la salida estructurada de la tarea a partir del contexto."""
        constructor = {
            "path_design": self._ruta,
            "lesson": self._leccion,
            "questions": self._preguntas,
            "judge": self._veredicto,
            "judge_escalation": self._veredicto,
            "re_explanation": self._explicacion,
        }.get(solicitud.tarea, self._generico)
        contenido = constructor(solicitud)
        uso = self._uso(solicitud, contenido)
        return RespuestaIA(
            contenido=contenido,
            uso=self._anotar(uso, solicitud.tarea),
            tarea=solicitud.tarea,
            texto_bruto="",
        )

    def generar_texto(self, solicitud: SolicitudIA) -> RespuestaIA:
        """Devuelve un texto determinista construido con los fragmentos."""
        base = solicitud.datos.get("title") or solicitud.datos.get("topic_title") or "el tema"
        apoyo = _frases(solicitud.fragmentos[0].text)[0] if solicitud.fragmentos else ""
        cuerpo = f"Sobre {base}. {apoyo}".strip()
        uso = self._uso(solicitud, cuerpo)
        return RespuestaIA(
            contenido=cuerpo,
            uso=self._anotar(uso, solicitud.tarea),
            tarea=solicitud.tarea,
            texto_bruto=cuerpo,
        )

    # ------------------------------------------------------------------
    # Contabilidad
    # ------------------------------------------------------------------
    def _uso(self, solicitud: SolicitudIA, contenido: Any) -> UsoIA:
        """Tokens estimados de la llamada; coste siempre 0 (no hay proveedor externo)."""
        entrada = _tokens_estimados(solicitud.sistema) + _tokens_estimados(solicitud.mensaje_usuario())
        salida = _tokens_estimados(repr(contenido))
        return UsoIA(
            model_id=solicitud.modelo or modelo_para_tarea(self.cfg, solicitud.tarea),
            provider=self.nombre,
            input_tokens=entrada,
            output_tokens=salida,
            cost_usd=Decimal("0"),
        )

    # ------------------------------------------------------------------
    # Fase A: esquema de ruta
    # ------------------------------------------------------------------
    def _titulos_de_fragmentos(self, solicitud: SolicitudIA) -> list[tuple[str, list[str]]]:
        """Agrupa los fragmentos por su primer encabezado: la espina del temario."""
        grupos: dict[str, list[str]] = {}
        for fragmento in solicitud.fragmentos:
            clave = fragmento.heading_path[0] if fragmento.heading_path else (
                _frases(fragmento.text, 1)[0][:60] if fragmento.text.strip() else "Fundamentos"
            )
            grupos.setdefault(clave, []).append(fragmento.etiqueta)
        return list(grupos.items())

    def _ruta(self, solicitud: SolicitudIA) -> dict[str, Any]:
        """Esquema de ruta con módulos, temas, objetivos y fragmentos de respaldo."""
        datos = solicitud.datos
        minimo = int(datos.get("modules_min", 4))
        maximo = int(datos.get("modules_max", 10))
        temas_min = int(datos.get("topics_min", 2))
        temas_max = int(datos.get("topics_max", 6))
        minutos = int(datos.get("lesson_minutes", 9))
        tipos = [str(t) for t in datos.get("question_types", _TIPOS_POR_DEFECTO)]
        area = str(datos.get("area_name") or datos.get("goal_text") or "tu material")

        grupos = self._titulos_de_fragmentos(solicitud)
        if not grupos:
            grupos = [(f"Fundamentos de {area}", [])]
        total_modulos = max(minimo, min(maximo, len(grupos)))

        modulos: list[dict[str, Any]] = []
        for indice in range(total_modulos):
            titulo_grupo, ids = grupos[indice % len(grupos)]
            titulo = titulo_grupo.strip()[:110] or f"Bloque {indice + 1} de {area}"
            n_temas = max(temas_min, min(temas_max, max(1, len(ids)) if ids else temas_min))
            temas: list[dict[str, Any]] = []
            for posicion in range(1, n_temas + 1):
                asignados = (ids[posicion - 1 :: n_temas] if ids else [])[:20]
                cobertura = CoverageLevel.FULL.value if asignados else CoverageLevel.INSUFFICIENT.value
                temas.append(
                    {
                        "position": posicion,
                        "title": f"{titulo} · parte {posicion}"[:140],
                        "learning_objectives": [
                            f"Explicar con tus palabras {titulo.lower()} (parte {posicion}).",
                            f"Aplicar {titulo.lower()} a un caso concreto.",
                        ],
                        "coverage": cobertura,
                        "difficulty": [
                            DifficultyLevel.EASY.value,
                            DifficultyLevel.MEDIUM.value,
                            DifficultyLevel.HARD.value,
                        ][min(2, indice // max(1, total_modulos // 3 or 1))],
                        "estimated_minutes": minutos,
                        "suggested_question_types": tipos[: 2 + (posicion % 2)],
                        "source_chunk_ids": asignados,
                    }
                )
            modulos.append(
                {
                    "position": indice + 1,
                    "title": titulo[:120],
                    "flavor_name": f"Zona {indice + 1}: {titulo[:100]}",
                    "summary": f"Qué aprenderás en {titulo}: los conceptos clave y su uso práctico.",
                    "difficulty": DifficultyLevel.MEDIUM.value,
                    "estimated_minutes": minutos * len(temas),
                    "topics": temas,
                }
            )

        notas = [
            f"El material no cubre «{modulo['title']}»; se completará con conocimiento del modelo."
            for modulo in modulos
            if all(not tema["source_chunk_ids"] for tema in modulo["topics"])
        ]
        return {
            "title": f"Ruta de {area}"[:120],
            "summary": f"Ruta generada a partir de tu material sobre {area}.",
            "modules": modulos,
            "coverage_notes": notas,
        }

    # ------------------------------------------------------------------
    # Fase B: lección
    # ------------------------------------------------------------------
    def _leccion(self, solicitud: SolicitudIA) -> dict[str, Any]:
        """Lección con bloques de explicación, ejemplo y resumen."""
        datos = solicitud.datos
        tema = str(datos.get("topic_title", "el tema"))
        objetivos = [str(o) for o in datos.get("objectives", [])] or [f"Comprender {tema}."]
        minutos = int(datos.get("lesson_minutes", 9))
        fragmentos = solicitud.fragmentos
        ids = [fragmento.etiqueta for fragmento in fragmentos]
        origen = "source" if ids else "model_knowledge"

        apoyo = _frases(fragmentos[0].text, 2) if fragmentos else []
        explicacion = (
            f"**{tema}** es la pieza que necesitas dominar aquí. "
            + (" ".join(f"{frase}." for frase in apoyo) if apoyo else
               "Partimos de lo esencial y avanzamos hasta el uso práctico.")
        )
        ejemplo_fuente = _frases(fragmentos[1].text, 1) if len(fragmentos) > 1 else apoyo[:1]
        ejemplo = (
            "Caso concreto: "
            + (ejemplo_fuente[0] + "." if ejemplo_fuente else f"aplica {tema} paso a paso.")
        )

        bloques = [
            {
                "position": 1,
                "block_type": LessonBlockType.EXPLANATION.value,
                "body": explicacion,
                "payload": {},
                "origin": origen,
                "source_chunk_ids": ids[:3],
            },
            {
                "position": 2,
                "block_type": LessonBlockType.EXAMPLE.value,
                "body": ejemplo,
                "payload": {},
                "origin": origen,
                "source_chunk_ids": ids[1:4],
            },
            {
                "position": 3,
                "block_type": LessonBlockType.SUMMARY.value,
                "body": "Para retener:\n"
                + "\n".join(f"- {objetivo}" for objetivo in objetivos[:4]),
                "payload": {},
                "origin": origen,
                "source_chunk_ids": ids[:1],
            },
        ]
        estado = CoverageLevel.FULL.value if ids else CoverageLevel.INSUFFICIENT.value
        return {
            "title": f"{tema}"[:140],
            "summary": f"Lección sobre {tema}: {objetivos[0]}",
            "estimated_seconds": max(60, minutos * 60),
            "blocks": bloques,
            "coverage_report": [
                {"objective": objetivo, "status": estado} for objetivo in objetivos[:6]
            ],
        }

    # ------------------------------------------------------------------
    # Fase B: preguntas
    # ------------------------------------------------------------------
    def _preguntas(self, solicitud: SolicitudIA) -> dict[str, Any]:
        """Lote de preguntas con clave de corrección y explicación, una por tipo."""
        datos = solicitud.datos
        tema = str(datos.get("topic_title", "el tema"))
        objetivos = [str(o) for o in datos.get("objectives", [])] or [f"Comprender {tema}."]
        tipos = [str(t) for t in datos.get("types", _TIPOS_POR_DEFECTO)] or list(_TIPOS_POR_DEFECTO)
        cuantas = max(1, int(datos.get("count", len(tipos))))
        ids = [fragmento.etiqueta for fragmento in solicitud.fragmentos]
        origen = "source" if ids else "model_knowledge"
        dificultades = [
            DifficultyLevel.EASY.value,
            DifficultyLevel.EASY.value,
            DifficultyLevel.MEDIUM.value,
            DifficultyLevel.MEDIUM.value,
            DifficultyLevel.HARD.value,
        ]

        preguntas: list[dict[str, Any]] = []
        for indice in range(cuantas):
            tipo = tipos[indice % len(tipos)]
            objetivo = objetivos[indice % len(objetivos)]
            base = {
                "question_type": tipo,
                "difficulty": dificultades[indice % len(dificultades)],
                "stem": self._enunciado(tipo, tema, indice),
                "explanation": f"Porque {objetivo.lower().rstrip('.')}, aplicado a {tema}.",
                "learning_objective": objetivo[:240],
                "estimated_seconds": 45,
                "origin": origen,
                "source_chunk_ids": ids[:2],
            }
            base.update(self._cuerpo_y_clave(tipo, tema, indice))
            preguntas.append(base)
        return {"questions": preguntas}

    def _enunciado(self, tipo: str, tema: str, indice: int) -> str:
        """Enunciado coherente con el tipo de pregunta."""
        match tipo:
            case QuestionType.TRUE_FALSE.value:
                return f"¿Es cierto lo siguiente sobre {tema}?"
            case QuestionType.FILL_BLANK.value:
                return f"Completa la frase sobre {tema}."
            case QuestionType.MATCHING.value:
                return f"Relaciona cada concepto de {tema} con su definición."
            case QuestionType.ORDERING.value:
                return f"Ordena los pasos para aplicar {tema}."
            case QuestionType.OPEN_SHORT.value:
                return f"Explica con tus palabras qué es {tema} y para qué sirve."
            case QuestionType.SQL_EXERCISE.value:
                return f"Escribe la consulta que resuelve el caso de {tema}."
            case _:
                return f"¿Cuál de estas afirmaciones describe mejor {tema}? ({indice + 1})"

    def _cuerpo_y_clave(self, tipo: str, tema: str, indice: int) -> dict[str, Any]:
        """`body` y `answer_key` consistentes para cada tipo del MVP."""
        match tipo:
            case QuestionType.TRUE_FALSE.value:
                verdadero = indice % 2 == 0
                afirmacion = (
                    f"{tema} se aplica al caso descrito en tu material."
                    if verdadero
                    else f"{tema} no tiene ninguna relación con tu material."
                )
                return {"body": {"statement": afirmacion}, "answer_key": {"correct": verdadero}}
            case QuestionType.FILL_BLANK.value:
                return {
                    "body": {
                        "text": f"Para aplicar {tema} primero hay que {{{{1}}}} y después {{{{2}}}}.",
                        "blanks": [{"index": 1}, {"index": 2}],
                    },
                    "answer_key": {
                        "blanks": [
                            {"index": 1, "accepted": ["analizar", "entender"]},
                            {"index": 2, "accepted": ["aplicar", "practicar"]},
                        ]
                    },
                }
            case QuestionType.MATCHING.value:
                return {
                    "body": {
                        "left": [
                            {"key": "l1", "text": f"Definición de {tema}"},
                            {"key": "l2", "text": f"Ejemplo de {tema}"},
                            {"key": "l3", "text": f"Error frecuente con {tema}"},
                        ],
                        "right": [
                            {"key": "r1", "text": "Un caso resuelto paso a paso"},
                            {"key": "r2", "text": "Confundirlo con un concepto vecino"},
                            {"key": "r3", "text": "Qué es y para qué sirve"},
                        ],
                    },
                    "answer_key": {
                        "pairs": [
                            {"left": "l1", "right": "r3"},
                            {"left": "l2", "right": "r1"},
                            {"left": "l3", "right": "r2"},
                        ]
                    },
                }
            case QuestionType.ORDERING.value:
                return {
                    "body": {
                        "items": [
                            {"key": "i2", "text": "Aplicarlo a un caso"},
                            {"key": "i1", "text": "Entender el concepto"},
                            {"key": "i3", "text": "Revisar el resultado"},
                        ]
                    },
                    "answer_key": {"order": ["i1", "i2", "i3"]},
                }
            case QuestionType.OPEN_SHORT.value:
                return {
                    "body": {
                        "rubric": {
                            "criteria": [
                                {"key": "c1", "text": f"Define {tema}", "weight": 50},
                                {"key": "c2", "text": "Da un ejemplo o un uso", "weight": 50},
                            ],
                            "max_words": 80,
                        }
                    },
                    "answer_key": {
                        "reference_answer": (
                            f"{tema} es el concepto central de esta lección y se usa para "
                            "resolver casos concretos."
                        ),
                        "must_include": [tema.split()[0].lower(), "ejemplo"],
                    },
                }
            case QuestionType.SQL_EXERCISE.value:
                return {
                    "body": {
                        "schema_sql": (
                            "CREATE TABLE clientes (id INTEGER, nombre VARCHAR, ciudad VARCHAR);"
                        ),
                        "seed_data": [
                            "INSERT INTO clientes VALUES (1, 'Ada', 'Santiago');",
                            "INSERT INTO clientes VALUES (2, 'Alan', 'Valparaíso');",
                            "INSERT INTO clientes VALUES (3, 'Grace', 'Santiago');",
                        ],
                        "prompt": "Devuelve los nombres de los clientes de Santiago.",
                        "ordered": False,
                    },
                    "answer_key": {
                        "reference_sql": "SELECT nombre FROM clientes WHERE ciudad = 'Santiago';"
                    },
                }
            case _:
                return {
                    "body": {
                        "options": [
                            {"key": "a", "text": f"{tema} solo sirve para memorizar."},
                            {"key": "b", "text": f"{tema} resuelve un problema concreto y verificable."},
                            {"key": "c", "text": f"{tema} es un sinónimo de cualquier otro concepto."},
                            {"key": "d", "text": f"{tema} no aparece en tu material."},
                        ]
                    },
                    "answer_key": {"correct_option": "b"},
                }

    # ------------------------------------------------------------------
    # Juez
    # ------------------------------------------------------------------
    def _veredicto(self, solicitud: SolicitudIA) -> dict[str, Any]:
        """Puntúa de verdad: compara la respuesta con la rúbrica y con `must_include`."""
        datos = solicitud.datos
        respuesta = _normalizar(str(datos.get("answer", "")))
        rubrica = datos.get("rubric") or {}
        criterios = rubrica.get("criteria") if isinstance(rubrica, dict) else None
        criterios = criterios if isinstance(criterios, list) and criterios else [
            {"key": "c1", "text": "Responde a la pregunta", "weight": 100}
        ]
        obligatorios = [_normalizar(str(t)) for t in datos.get("must_include", []) if str(t).strip()]

        evaluados: list[dict[str, str]] = []
        puntaje = 0.0
        faltan: list[str] = []
        for criterio in criterios:
            clave = str(criterio.get("key", "c"))
            peso = float(criterio.get("weight", 100 / len(criterios)))
            palabras = [
                palabra
                for palabra in _normalizar(str(criterio.get("text", ""))).split()
                if len(palabra) > 4
            ]
            aciertos = sum(1 for palabra in palabras if palabra in respuesta)
            if palabras and aciertos >= max(1, len(palabras) // 2):
                evaluados.append({"key": clave, "met": "full"})
                puntaje += peso
            elif aciertos:
                evaluados.append({"key": clave, "met": "partial"})
                puntaje += peso / 2
                faltan.append(str(criterio.get("text", clave))[:120])
            else:
                evaluados.append({"key": clave, "met": "none"})
                faltan.append(str(criterio.get("text", clave))[:120])

        if obligatorios:
            presentes = sum(1 for termino in obligatorios if termino in respuesta)
            puntaje = (puntaje + 100.0 * presentes / len(obligatorios)) / 2

        puntaje = max(0.0, min(100.0, round(puntaje, 2)))
        veredicto = "correct" if puntaje >= 70 else ("partial" if puntaje >= 40 else "incorrect")
        palabras_respuesta = len(respuesta.split())
        confianza = 0.9 if palabras_respuesta >= 8 else (0.55 if palabras_respuesta >= 3 else 0.3)
        return {
            "score": puntaje,
            "verdict": veredicto,
            "confidence": confianza,
            "feedback": (
                "Bien: cubres lo esencial."
                if veredicto == "correct"
                else "Te falta concretar: " + ("; ".join(faltan[:2]) or "desarrolla más la idea.")
            ),
            "criteria": evaluados,
            "missing": faltan[:6],
            "flags": ["prompt_injection"] if "ignora" in respuesta and "instruccion" in respuesta else [],
        }

    # ------------------------------------------------------------------
    # Re-explicación
    # ------------------------------------------------------------------
    def _explicacion(self, solicitud: SolicitudIA) -> dict[str, Any]:
        """Explicación alternativa con el enfoque pedido y sus citas."""
        datos = solicitud.datos
        enfoque = str(datos.get("approach", "analogy"))
        tema = str(datos.get("topic_title", "el tema"))
        apoyo = _frases(solicitud.fragmentos[0].text, 2) if solicitud.fragmentos else []
        detalle = " ".join(f"{frase}." for frase in apoyo) if apoyo else (
            "Vamos a reconstruirlo desde cero, sin dar nada por sabido."
        )
        cuerpo = (
            f"Probemos otra vía con **{tema}**, esta vez con un enfoque de tipo «{enfoque}».\n\n"
            f"{detalle}\n\n"
            "Lo que te estaba fallando no es el concepto entero, sino un paso concreto: "
            "revisa ese paso con calma y el resto encaja solo."
        )
        return {
            "approach": enfoque,
            "body": cuerpo,
            "citations": [fragmento.etiqueta for fragmento in solicitud.fragmentos[:4]],
            "check_question": f"¿Sabrías explicarle {tema} a alguien en dos frases?",
        }

    # ------------------------------------------------------------------
    def _generico(self, solicitud: SolicitudIA) -> dict[str, Any]:
        """Salida mínima para tareas sin constructor propio (narrativa, groundedness)."""
        return {
            "title": str(solicitud.datos.get("title", "Territorio sin nombre"))[:80],
            "body": solicitud.instruccion[:400],
        }


__all__ = ["ProveedorSimulado"]
