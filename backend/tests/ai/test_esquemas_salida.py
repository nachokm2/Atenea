"""Esquemas estrictos de salida y reintento acotado cuando la IA no cumple el esquema."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.modules.ai import esquemas_salida as es
from app.modules.ai.proveedor import ProveedorIA, RespuestaIA, SolicitudIA, UsoIA, uso_vacio


@pytest.mark.parametrize(
    "modelo",
    [
        es.SalidaRuta,
        es.SalidaLeccion,
        es.SalidaLotePreguntas,
        es.SalidaVeredicto,
        es.SalidaExplicacion,
    ],
)
def test_el_esquema_es_estricto_y_autocontenido(modelo: type[es.EsquemaSalida]) -> None:
    """Sin `$ref`, con todo objeto cerrado y todas sus propiedades obligatorias."""
    esquema = es.esquema_estricto(modelo)
    crudo = json.dumps(esquema)
    assert "$ref" not in crudo
    assert "$defs" not in crudo
    assert esquema["additionalProperties"] is False
    assert set(esquema["required"]) == set(esquema["properties"].keys())


def test_hay_un_esquema_por_tarea() -> None:
    """Cada tarea estructurada declara su modelo de salida."""
    for tarea in ("path_design", "lesson", "questions", "judge", "re_explanation"):
        assert es.esquema_de_tarea(tarea) is not None
    assert es.esquema_de_tarea("narrative") is None


def test_rechaza_los_tipos_de_pregunta_reservados() -> None:
    """`case_study` y `code_exercise` están reservados para fase 2/3 (D13)."""
    with pytest.raises(Exception, match="fuera del MVP"):
        es.SalidaPregunta.model_validate(
            {"question_type": "case_study", "stem": "Un caso largo de estudio"}
        )


def test_la_clave_debe_encajar_con_el_cuerpo() -> None:
    """Una opción correcta que no existe entre las opciones invalida la pregunta."""
    buena = es.SalidaPregunta.model_validate(
        {
            "question_type": "multiple_choice",
            "stem": "¿Qué hace un LEFT JOIN?",
            "body": {"options": [{"key": "a", "text": "uno"}, {"key": "b", "text": "dos"}]},
            "answer_key": {"correct_option": "b"},
        }
    )
    mala = es.SalidaPregunta.model_validate(
        {
            "question_type": "multiple_choice",
            "stem": "¿Qué hace un LEFT JOIN?",
            "body": {"options": [{"key": "a", "text": "uno"}, {"key": "b", "text": "dos"}]},
            "answer_key": {"correct_option": "z"},
        }
    )
    assert buena.clave_completa() is True
    assert mala.clave_completa() is False


class _ProveedorTerco(ProveedorIA):
    """Proveedor de prueba que devuelve basura las primeras `fallos` veces."""

    nombre = "terco"

    def __init__(self, fallos: int) -> None:
        super().__init__()
        self.fallos = fallos
        self.llamadas = 0

    def generar_estructurado(self, solicitud: SolicitudIA) -> RespuestaIA:
        self.llamadas += 1
        uso = UsoIA(model_id="m", provider=self.nombre, input_tokens=10, output_tokens=5)
        self._anotar(uso, solicitud.tarea)
        contenido: dict[str, Any]
        if self.llamadas <= self.fallos:
            contenido = {"approach": "analogy"}  # falta `body`
        else:
            contenido = {
                "approach": "analogy",
                "body": "Una explicación suficientemente larga para pasar el mínimo de caracteres.",
                "citations": [],
                "check_question": "",
            }
        return RespuestaIA(contenido=contenido, uso=uso, tarea=solicitud.tarea)

    def generar_texto(self, solicitud: SolicitudIA) -> RespuestaIA:  # pragma: no cover
        return RespuestaIA(contenido="", uso=uso_vacio(), tarea=solicitud.tarea)


def _solicitud() -> SolicitudIA:
    return SolicitudIA(tarea="re_explanation", sistema="s", instruccion="Explica el tema")


def test_reintenta_y_acaba_validando() -> None:
    """Un fallo de esquema se reintenta con el error concreto y se acaba validando."""
    proveedor = _ProveedorTerco(fallos=1)
    solicitud = _solicitud()
    salida, respuesta = es.generar_validado(
        proveedor, solicitud, es.SalidaExplicacion, max_intentos=2
    )
    assert salida.approach == "analogy"
    assert proveedor.llamadas == 2
    assert respuesta.reintentos == 1
    # El coste de los reintentos también se contabiliza.
    assert respuesta.uso.input_tokens == 20
    # La instrucción original queda intacta para la siguiente llamada.
    assert "Corrección obligatoria" not in solicitud.instruccion


def test_el_reintento_esta_acotado() -> None:
    """Agotados los intentos se lanza `SalidaInvalida` (502 GENERATION_FAILED)."""
    proveedor = _ProveedorTerco(fallos=99)
    with pytest.raises(es.SalidaInvalida) as error:
        es.generar_validado(proveedor, _solicitud(), es.SalidaExplicacion, max_intentos=2)
    assert proveedor.llamadas == 2
    assert error.value.code == "GENERATION_FAILED"
    assert error.value.status_code == 502
    assert error.value.details["attempts"] == 2
