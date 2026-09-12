"""Detección de tipo real, validación de límites y extracción de texto (§5.8, §8.7).

El contrato es explícito (§8.7): *«Validación de subidas: extensión, tipo MIME,
**magic bytes**, tamaño y número de páginas antes de encolar»*. Aquí manda el
**contenido**, no el nombre: un `.pdf` que en realidad es un ejecutable se rechaza, y
un `.dat` que empieza por `%PDF-` se acepta como PDF.

Formatos del MVP (`DocumentType`): `PDF`, `DOCX`, `MARKDOWN`, `TXT` y `PASTED_TEXT`.
`URL` e `IMAGE` están reservados para la fase 2 y se rechazan con
`415 UNSUPPORTED_FILE_TYPE`.

Errores del catálogo cerrado de §8.1 que emite este módulo:

* `413 FILE_TOO_LARGE` — supera `ingestion.max_file_mb` o `ingestion.max_pdf_pages`.
* `415 UNSUPPORTED_FILE_TYPE` — el contenido no es ninguno de los formatos del MVP.
* `422 DOCUMENT_UNREADABLE` — PDF escaneado sin texto (`details.reason =
  "scanned_pdf_no_text"`) o material insuficiente (`details.min_words`).

La extracción conserva la estructura que después necesita el troceador: encabezados
como `#` de Markdown, bloques de código entre vallas y tablas en formato de tubería.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import AteneaError
from app.models.enums import DocumentType

#: Tipos admitidos en el MVP. `URL` e `IMAGE` quedan fuera (fase 2).
TIPOS_ADMITIDOS: frozenset[DocumentType] = frozenset(
    {
        DocumentType.PDF,
        DocumentType.DOCX,
        DocumentType.MARKDOWN,
        DocumentType.TXT,
        DocumentType.PASTED_TEXT,
    }
)

#: Tipo MIME canónico de cada formato, para la cabecera y la telemetría.
MIME_POR_TIPO: dict[DocumentType, str] = {
    DocumentType.PDF: "application/pdf",
    DocumentType.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocumentType.MARKDOWN: "text/markdown",
    DocumentType.TXT: "text/plain",
    DocumentType.PASTED_TEXT: "text/plain",
}

#: Extensiones que el cliente suele mandar; solo desempatan Markdown frente a texto plano.
EXTENSIONES_MARKDOWN: frozenset[str] = frozenset({".md", ".markdown", ".mdown", ".mkd"})

#: Firmas binarias conocidas que **no** son formatos del MVP (mensaje de rechazo claro).
FIRMAS_RECHAZADAS: tuple[tuple[bytes, str], ...] = (
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "Documento de Word antiguo (.doc)"),
    (b"\x89PNG\r\n\x1a\n", "Imagen PNG"),
    (b"\xff\xd8\xff", "Imagen JPEG"),
    (b"GIF8", "Imagen GIF"),
    (b"%!PS", "PostScript"),
    (b"\x7fELF", "Ejecutable"),
    (b"MZ", "Ejecutable de Windows"),
    (b"Rar!", "Archivo comprimido RAR"),
    (b"\x1f\x8b", "Archivo comprimido GZIP"),
    (b"{\\rtf", "Documento RTF"),
)

#: Palabras vacías para la detección de idioma (heurística barata, sin dependencias).
_VACIAS_ES = frozenset(
    "de la que el en y a los del se las por un para con no una su al lo como más pero sus"
    " le ya o este sí porque esta entre cuando muy sin sobre también me hasta hay donde".split()
)
_VACIAS_EN = frozenset(
    "the of and to in a is that it for on with as was are be this by or an at from not have"
    " has but they you we can which their there when where more than into".split()
)


class DocumentoIlegible(AteneaError):
    """422 · PDF escaneado sin texto o material insuficiente (§8.1)."""

    code = "DOCUMENT_UNREADABLE"
    status_code = 422


class TipoNoAdmitido(AteneaError):
    """415 · El contenido no corresponde a ningún formato del MVP (§8.1)."""

    code = "UNSUPPORTED_FILE_TYPE"
    status_code = 415


class ArchivoDemasiadoGrande(AteneaError):
    """413 · Supera `ingestion.max_file_mb` o `ingestion.max_pdf_pages` (§8.1)."""

    code = "FILE_TOO_LARGE"
    status_code = 413


@dataclass(slots=True)
class TipoDetectado:
    """Resultado de mirar los primeros bytes del fichero."""

    document_type: DocumentType
    mime: str
    #: `True` cuando la extensión del cliente contradecía al contenido (se registra).
    extension_incoherente: bool = False


@dataclass(slots=True)
class RangoPagina:
    """Tramo del texto extraído que corresponde a una página del original."""

    numero: int
    char_start: int
    char_end: int


@dataclass(slots=True)
class TextoExtraido:
    """Texto normalizado de un documento más lo que hace falta para trazarlo."""

    texto: str
    document_type: DocumentType
    page_count: int | None = None
    word_count: int = 0
    token_count: int = 0
    language: str | None = None
    paginas: list[RangoPagina] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def pagina_de(self, posicion: int) -> int | None:
        """Número de página que contiene un offset de carácter (o `None`)."""
        for rango in self.paginas:
            if rango.char_start <= posicion < rango.char_end:
                return rango.numero
        return self.paginas[-1].numero if self.paginas else None


# ---------------------------------------------------------------------------
# Detección de tipo por contenido
# ---------------------------------------------------------------------------


def _es_docx(datos: bytes) -> bool:
    """Un DOCX es un ZIP que contiene `word/document.xml`."""
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as paquete:
            nombres = set(paquete.namelist())
    except (zipfile.BadZipFile, OSError):
        return False
    return "word/document.xml" in nombres


def _texto_decodificable(datos: bytes) -> str | None:
    """Devuelve el texto si el binario es texto plano legible; `None` si es binario."""
    muestra = datos[:65536]
    if b"\x00" in muestra:
        return None
    for codificacion in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = datos.decode(codificacion)
        except (UnicodeDecodeError, LookupError):
            continue
        # Un texto real no está lleno de caracteres de control.
        control = sum(1 for caracter in texto[:4000] if ord(caracter) < 32 and caracter not in "\n\r\t")
        if control > max(4, len(texto[:4000]) // 100):
            return None
        return texto
    return None


def _parece_markdown(texto: str) -> bool:
    """Heurística de Markdown: encabezados, vallas de código, listas o tablas."""
    marcas = 0
    for linea in texto.splitlines()[:400]:
        recortada = linea.strip()
        if re.match(r"^#{1,6}\s+\S", recortada):
            marcas += 2
        elif recortada.startswith(("```", "~~~")):
            marcas += 2
        elif re.match(r"^([-*+]\s+\S|\d+[.)]\s+\S)", recortada):
            marcas += 1
        elif recortada.count("|") >= 2:
            marcas += 1
        elif re.search(r"\[[^\]]+\]\([^)]+\)", recortada):
            marcas += 1
        if marcas >= 3:
            return True
    return False


def detectar_tipo(nombre_archivo: str | None, datos: bytes) -> TipoDetectado:
    """Determina el formato real por **magic bytes** y contenido, no por la extensión.

    La extensión solo se usa como desempate entre Markdown y texto plano, que son el
    mismo binario a ojos del sistema de ficheros.
    """
    if not datos:
        raise TipoNoAdmitido(
            "El archivo está vacío. Sube un documento con contenido.",
            details={"reason": "empty_file"},
        )

    extension = ""
    if nombre_archivo and "." in nombre_archivo:
        extension = "." + nombre_archivo.rsplit(".", 1)[-1].strip().lower()

    cabecera = datos[:1024].lstrip(b"\xef\xbb\xbf \t\r\n")

    if cabecera.startswith(b"%PDF-"):
        return TipoDetectado(
            DocumentType.PDF,
            MIME_POR_TIPO[DocumentType.PDF],
            extension_incoherente=extension not in ("", ".pdf"),
        )

    if cabecera.startswith(b"PK\x03\x04"):
        if _es_docx(datos):
            return TipoDetectado(
                DocumentType.DOCX,
                MIME_POR_TIPO[DocumentType.DOCX],
                extension_incoherente=extension not in ("", ".docx"),
            )
        raise TipoNoAdmitido(
            "Ese archivo comprimido no es un documento de Word (.docx).",
            details={"reason": "zip_not_docx"},
        )

    for firma, etiqueta in FIRMAS_RECHAZADAS:
        if cabecera.startswith(firma):
            raise TipoNoAdmitido(
                f"{etiqueta} no está admitido. Sube un PDF, DOCX, Markdown o TXT.",
                details={"reason": "unsupported_signature", "detected": etiqueta},
            )

    texto = _texto_decodificable(datos)
    if texto is None:
        raise TipoNoAdmitido(
            "No reconocimos el formato del archivo. Sube un PDF, DOCX, Markdown o TXT.",
            details={"reason": "binary_content"},
        )

    if extension in EXTENSIONES_MARKDOWN or _parece_markdown(texto):
        return TipoDetectado(DocumentType.MARKDOWN, MIME_POR_TIPO[DocumentType.MARKDOWN])
    return TipoDetectado(DocumentType.TXT, MIME_POR_TIPO[DocumentType.TXT])


def validar_tamano(datos: bytes, *, max_bytes: int) -> None:
    """Comprueba el tope de `ingestion.max_file_mb` antes de tocar el disco."""
    if len(datos) > max_bytes:
        raise ArchivoDemasiadoGrande(
            "El archivo es demasiado grande. El máximo es "
            f"{max_bytes // (1024 * 1024)} MB.",
            details={"byte_size": len(datos), "max_bytes": max_bytes},
        )


# ---------------------------------------------------------------------------
# Limpieza y métricas del texto
# ---------------------------------------------------------------------------

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ESPACIOS_FINALES = re.compile(r"[ \t]+$", re.MULTILINE)
_LINEAS_VACIAS = re.compile(r"\n{3,}")
_GUION_CORTE = re.compile(r"(\w)[-­]\n(\w)")
_PALABRA = re.compile(r"\w+", re.UNICODE)


def limpiar_texto(texto: str, *, unir_guiones: bool = False) -> str:
    """Normaliza el texto extraído sin destruir código, tablas ni sangrías.

    Se hace, en este orden: normalización Unicode NFC, unificación de saltos de línea,
    borrado de caracteres de control, unión de palabras cortadas por guión al final de
    línea (solo PDF), borrado de espacios al final de cada línea y colapso de tres o más
    líneas en blanco a dos. La sangría inicial **se conserva**: es significativa en
    código y en listas.
    """
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFC", texto)
    normalizado = normalizado.replace("\r\n", "\n").replace("\r", "\n")
    normalizado = normalizado.replace(" ", " ").replace("​", "")
    normalizado = _CONTROL.sub("", normalizado)
    if unir_guiones:
        normalizado = _GUION_CORTE.sub(r"\1\2", normalizado)
    normalizado = _ESPACIOS_FINALES.sub("", normalizado)
    normalizado = _LINEAS_VACIAS.sub("\n\n", normalizado)
    return normalizado.strip("\n")


def contar_palabras(texto: str) -> int:
    """Número de palabras del texto (unidad de `ingestion.min_words_for_path`)."""
    return len(_PALABRA.findall(texto))


def estimar_tokens(texto: str) -> int:
    """Estimación de tokens sin llamar al proveedor: ~4 caracteres por token.

    Sirve para el tope `ingestion.max_corpus_tokens` y para el troceador. Es una
    aproximación deliberada: el recuento exacto depende del tokenizador del modelo y
    no justifica una dependencia ni una llamada de red en la ingesta.
    """
    if not texto:
        return 0
    return max(1, round(len(texto) / 4))


def detectar_idioma(texto: str) -> str:
    """Detecta `es` o `en` por palabras vacías; devuelve `es` ante la duda (producto en español)."""
    palabras = [palabra.lower() for palabra in _PALABRA.findall(texto[:20000])]
    if not palabras:
        return "es"
    es = sum(1 for palabra in palabras if palabra in _VACIAS_ES)
    en = sum(1 for palabra in palabras if palabra in _VACIAS_EN)
    return "en" if en > es * 1.2 else "es"


def _quitar_encabezados_repetidos(paginas: list[str]) -> list[str]:
    """Elimina cabeceras y pies que se repiten en la mayoría de las páginas de un PDF."""
    if len(paginas) < 4:
        return paginas
    candidatos: dict[str, int] = {}
    for pagina in paginas:
        lineas = [linea.strip() for linea in pagina.splitlines() if linea.strip()]
        for linea in lineas[:1] + lineas[-1:]:
            if 0 < len(linea) <= 90:
                candidatos[linea] = candidatos.get(linea, 0) + 1
    umbral = max(3, int(len(paginas) * 0.6))
    repetidas = {linea for linea, veces in candidatos.items() if veces >= umbral}
    if not repetidas:
        return paginas
    limpias: list[str] = []
    for pagina in paginas:
        lineas = pagina.splitlines()
        limpias.append("\n".join(linea for linea in lineas if linea.strip() not in repetidas))
    return limpias


# ---------------------------------------------------------------------------
# Extractores por formato
# ---------------------------------------------------------------------------


def _extraer_pdf(datos: bytes, *, max_paginas: int, min_chars_por_pagina: int) -> TextoExtraido:
    """Extrae el texto de un PDF y rechaza el PDF escaneado sin capa de texto."""
    from pypdf import PdfReader  # noqa: PLC0415 - importación perezosa: solo en la ingesta

    # `PyPdfError` es la raíz de la jerarquía de errores de pypdf (lectura, flujo,
    # dependencias); se importa por su nombre actual para no atarse a un alias antiguo.
    from pypdf.errors import PyPdfError as PdfError  # noqa: PLC0415

    try:
        lector = PdfReader(io.BytesIO(datos))
        if getattr(lector, "is_encrypted", False):
            try:
                lector.decrypt("")
            except Exception:  # noqa: BLE001 - cifrado con contraseña real
                raise DocumentoIlegible(
                    "El PDF está protegido con contraseña y no podemos leerlo.",
                    details={"reason": "encrypted_pdf"},
                ) from None
        paginas_pdf = list(lector.pages)
    except DocumentoIlegible:
        raise
    except (PdfError, OSError, ValueError) as exc:
        raise DocumentoIlegible(
            "El PDF está dañado o no se puede abrir.",
            details={"reason": "corrupt_pdf"},
        ) from exc

    total = len(paginas_pdf)
    if total == 0:
        raise DocumentoIlegible(
            "El PDF no tiene páginas.", details={"reason": "empty_pdf", "page_count": 0}
        )
    if total > max_paginas:
        raise ArchivoDemasiadoGrande(
            f"El PDF tiene {total} páginas y el máximo es {max_paginas}.",
            details={"page_count": total, "max_pdf_pages": max_paginas},
        )

    crudas: list[str] = []
    for pagina in paginas_pdf:
        try:
            crudas.append(pagina.extract_text() or "")
        except Exception:  # noqa: BLE001 - una página rota no invalida el documento
            crudas.append("")

    caracteres = sum(len(texto.strip()) for texto in crudas)
    if caracteres < min_chars_por_pagina * total:
        # Mensaje del contrato (§8.1, `DOCUMENT_UNREADABLE`) con el motivo en `details`,
        # que es el mismo que viaja en el evento `DOCUMENT_FAILED` (§4.2).
        raise DocumentoIlegible(
            details={
                "reason": "scanned_pdf_no_text",
                "page_count": total,
                "chars_extracted": caracteres,
                "min_chars_per_page": min_chars_por_pagina,
            }
        )

    limpias = _quitar_encabezados_repetidos(crudas)

    partes: list[str] = []
    rangos: list[RangoPagina] = []
    posicion = 0
    for numero, cruda in enumerate(limpias, start=1):
        pagina = limpiar_texto(cruda, unir_guiones=True)
        bloque = pagina + "\n\n"
        partes.append(bloque)
        rangos.append(RangoPagina(numero=numero, char_start=posicion, char_end=posicion + len(bloque)))
        posicion += len(bloque)

    texto = limpiar_texto("".join(partes))
    return TextoExtraido(
        texto=texto,
        document_type=DocumentType.PDF,
        page_count=total,
        word_count=contar_palabras(texto),
        token_count=estimar_tokens(texto),
        language=detectar_idioma(texto),
        paginas=rangos,
    )


def _tabla_docx_a_markdown(tabla: Any) -> str:
    """Convierte una tabla de Word en una tabla Markdown de tuberías (bloque atómico)."""
    filas: list[list[str]] = []
    for fila in tabla.rows:
        celdas = [" ".join(celda.text.split()) for celda in fila.cells]
        filas.append(celdas)
    if not filas:
        return ""
    ancho = max(len(fila) for fila in filas)
    lineas = []
    for indice, fila in enumerate(filas):
        completa = fila + [""] * (ancho - len(fila))
        lineas.append("| " + " | ".join(completa) + " |")
        if indice == 0:
            lineas.append("| " + " | ".join(["---"] * ancho) + " |")
    return "\n".join(lineas)


def _extraer_docx(datos: bytes) -> TextoExtraido:
    """Extrae párrafos, encabezados y tablas de un DOCX conservando su orden real."""
    import docx  # noqa: PLC0415 - importación perezosa
    from docx.table import Table  # noqa: PLC0415
    from docx.text.paragraph import Paragraph  # noqa: PLC0415

    try:
        documento = docx.Document(io.BytesIO(datos))
    except Exception as exc:  # noqa: BLE001 - python-docx lanza excepciones variadas
        raise DocumentoIlegible(
            "El documento de Word está dañado y no se puede leer.",
            details={"reason": "corrupt_docx"},
        ) from exc

    partes: list[str] = []
    cuerpo = documento.element.body
    for hijo in cuerpo.iterchildren():
        etiqueta = hijo.tag.rsplit("}", 1)[-1]
        if etiqueta == "p":
            parrafo = Paragraph(hijo, documento)
            texto = parrafo.text.strip()
            if not texto:
                continue
            estilo = (parrafo.style.name or "") if parrafo.style is not None else ""
            nivel = re.match(r"^Heading (\d)", estilo) or re.match(r"^Título (\d)", estilo)
            if nivel:
                partes.append("#" * min(6, int(nivel.group(1))) + " " + texto)
            elif "Code" in estilo or "Código" in estilo:
                partes.append("```\n" + parrafo.text.rstrip() + "\n```")
            elif re.match(r"^List", estilo):
                partes.append("- " + texto)
            else:
                partes.append(texto)
        elif etiqueta == "tbl":
            tabla = _tabla_docx_a_markdown(Table(hijo, documento))
            if tabla:
                partes.append(tabla)

    texto = limpiar_texto("\n\n".join(partes))
    return TextoExtraido(
        texto=texto,
        document_type=DocumentType.DOCX,
        page_count=None,
        word_count=contar_palabras(texto),
        token_count=estimar_tokens(texto),
        language=detectar_idioma(texto),
    )


def _extraer_texto_plano(datos: bytes, tipo: DocumentType) -> TextoExtraido:
    """Decodifica Markdown o texto plano y lo normaliza tal cual (la estructura se respeta)."""
    crudo = _texto_decodificable(datos)
    if crudo is None:
        raise TipoNoAdmitido(
            "No pudimos leer el archivo como texto.", details={"reason": "undecodable_text"}
        )
    texto = limpiar_texto(crudo)
    return TextoExtraido(
        texto=texto,
        document_type=tipo,
        page_count=None,
        word_count=contar_palabras(texto),
        token_count=estimar_tokens(texto),
        language=detectar_idioma(texto),
    )


def extraer(
    datos: bytes,
    tipo: DocumentType,
    *,
    max_paginas: int,
    min_chars_por_pagina: int,
) -> TextoExtraido:
    """Extrae el texto según el formato detectado y devuelve sus métricas.

    `max_paginas` sale de `ingestion.max_pdf_pages` y `min_chars_por_pagina` de
    `ingestion.scanned_pdf_min_chars_per_page`: ningún número de juego se escribe aquí.
    """
    if tipo == DocumentType.PDF:
        return _extraer_pdf(
            datos, max_paginas=max_paginas, min_chars_por_pagina=min_chars_por_pagina
        )
    if tipo == DocumentType.DOCX:
        return _extraer_docx(datos)
    if tipo in (DocumentType.MARKDOWN, DocumentType.TXT, DocumentType.PASTED_TEXT):
        return _extraer_texto_plano(datos, tipo)
    raise TipoNoAdmitido(
        "Ese formato aún no está admitido.", details={"reason": "phase_2", "type": str(tipo)}
    )


def validar_material_suficiente(extraido: TextoExtraido, *, min_palabras: int) -> None:
    """Rechaza el material que no da para diseñar una ruta (`ingestion.min_words_for_path`)."""
    if extraido.word_count < min_palabras:
        raise DocumentoIlegible(
            "El material es demasiado corto para construir una ruta. "
            f"Necesitamos al menos {min_palabras} palabras.",
            details={
                "reason": "insufficient_content",
                "min_words": min_palabras,
                "word_count": extraido.word_count,
            },
        )


__all__ = [
    "EXTENSIONES_MARKDOWN",
    "FIRMAS_RECHAZADAS",
    "MIME_POR_TIPO",
    "TIPOS_ADMITIDOS",
    "ArchivoDemasiadoGrande",
    "DocumentoIlegible",
    "RangoPagina",
    "TextoExtraido",
    "TipoDetectado",
    "TipoNoAdmitido",
    "contar_palabras",
    "detectar_idioma",
    "detectar_tipo",
    "estimar_tokens",
    "extraer",
    "limpiar_texto",
    "validar_material_suficiente",
    "validar_tamano",
]
