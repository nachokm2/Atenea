"""Módulo `ingestion`: material del usuario, fragmentos, embeddings y recuperación.

Contrato §1.3, §3.3, §5.8, §6.12, §7.5, §8.7.

El recorrido completo de un material, de principio a fin:

```
POST /documents  ─┐
POST /paste      ─┴→ servicio.subir_archivo / pegar_texto
                        · tipo real por magic bytes (extraccion)
                        · tope de tamaño y de páginas (ingestion.max_*)
                        · deduplicación por SHA-256 del binario
                        · almacén privado con clave opaca (almacenamiento)
                        · versión nueva + trabajo PENDING en la cola
                              │
                              ▼  worker (app/worker/principal.py)
                  servicio.procesar_version
                        · extraer  (extraccion)   → texto limpio + páginas
                        · trocear  (fragmentacion) → estructura, código y tablas íntegros
                        · embeber  (embeddings)    → Vector(512), proveedor intercambiable
                        · READY + evento DOCUMENT_INGESTED
                              │
                              ▼
                  recuperacion.recuperar  → vectorial + léxico, fusión RRF (§6.12)
```

Superficie pública que usan los demás módulos (nunca tocando estas tablas por su cuenta):

- **Alta y ciclo de vida** (:mod:`app.modules.ingestion.servicio`):
  :func:`subir_archivo`, :func:`pegar_texto`, :func:`procesar_version`,
  :func:`reindexar_version`, :func:`listar_documentos`, :func:`obtener_documento`,
  :func:`borrar_documento`, :func:`purgar_documentos`.
- **Recuperación** (:mod:`app.modules.ingestion.recuperacion`): :func:`recuperar`, que es
  lo que el módulo `ai` usa para construir el contexto de cualquier generación.
- **Embeddings** (:mod:`app.modules.ingestion.embeddings`): :func:`obtener_proveedor`,
  con el `mock` determinista por defecto y `voyage` en producción.
- **API**: `router` (:mod:`app.modules.ingestion.router`), que monta el agente de
  integración en `app/api/v1/__init__.py`.

Dos invariantes que no se negocian: **el material del usuario es entrada no confiable**
(§8.7) y **toda consulta filtra por `user_id`**; lo ajeno responde `404`, no `403`.
"""

from __future__ import annotations

from app.modules.ingestion.embeddings import (
    AjustesEmbeddings,
    ProveedorEmbeddings,
    ProveedorMock,
    ProveedorOpenAI,
    ProveedorVoyage,
    ajustes_de,
    embeber_por_lotes,
    obtener_proveedor,
)
from app.modules.ingestion.extraccion import (
    ArchivoDemasiadoGrande,
    DocumentoIlegible,
    TextoExtraido,
    TipoDetectado,
    TipoNoAdmitido,
    detectar_tipo,
    extraer,
    limpiar_texto,
)
from app.modules.ingestion.fragmentacion import (
    Fragmento,
    ParametrosTroceo,
    analizar_bloques,
    fragmentar,
    texto_para_embeber,
)
from app.modules.ingestion.recuperacion import (
    FragmentoRecuperado,
    ResultadoRecuperacion,
    fusionar_rrf,
    recuperar,
)
from app.modules.ingestion.servicio import (
    EstadoGeneracion,
    LimitesIngesta,
    PaginaDocumentos,
    ResultadoDocumento,
    ResultadoIngesta,
    biblioteca_por_defecto,
    borrar_documento,
    documentos_de_ruta,
    estado_generacion,
    limites,
    listar_documentos,
    obtener_documento,
    obtener_fragmento,
    pegar_texto,
    procesar_version,
    purgar_documentos,
    reindexar_version,
    subir_archivo,
    version_vigente,
)

__all__ = [
    "AjustesEmbeddings",
    "ArchivoDemasiadoGrande",
    "DocumentoIlegible",
    "EstadoGeneracion",
    "Fragmento",
    "FragmentoRecuperado",
    "LimitesIngesta",
    "PaginaDocumentos",
    "ParametrosTroceo",
    "ProveedorEmbeddings",
    "ProveedorMock",
    "ProveedorOpenAI",
    "ProveedorVoyage",
    "ResultadoDocumento",
    "ResultadoIngesta",
    "ResultadoRecuperacion",
    "TextoExtraido",
    "TipoDetectado",
    "TipoNoAdmitido",
    "ajustes_de",
    "analizar_bloques",
    "biblioteca_por_defecto",
    "borrar_documento",
    "detectar_tipo",
    "documentos_de_ruta",
    "embeber_por_lotes",
    "estado_generacion",
    "extraer",
    "fragmentar",
    "fusionar_rrf",
    "limites",
    "limpiar_texto",
    "listar_documentos",
    "obtener_documento",
    "obtener_fragmento",
    "obtener_proveedor",
    "pegar_texto",
    "procesar_version",
    "purgar_documentos",
    "recuperar",
    "reindexar_version",
    "subir_archivo",
    "texto_para_embeber",
    "version_vigente",
]
