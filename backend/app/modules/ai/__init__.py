"""Capa de IA de Atenea: orquestación de Claude, del sandbox y de la adaptación.

Principio rector del brief, que este paquete aplica sin excepción: **IA solo donde
aporta valor real, contenido siempre respaldado por las fuentes y jamás una llamada
innecesaria.**

Mapa del paquete:

| Módulo | Responsabilidad |
|---|---|
| `proveedor` | Interfaz `ProveedorIA`, enrutamiento por `ai.models`, plantillas y coste |
| `claude` | Proveedor real (SDK `anthropic`, caché de prefijo, reintentos) |
| `simulado` | Proveedor determinista sin red ni coste: desarrollo y **todas** las pruebas |
| `esquemas_salida` | Esquemas JSON estrictos de cada salida y validación con reintento |
| `arquitecto_ruta` | Fase A: corpus → esquema de ruta, recuperación híbrida y cobertura |
| `autor_leccion` | Fase B: generación perezosa por módulo, caché permanente, procedencia |
| `juez` | Respuestas abiertas: rúbrica, confianza y escalado |
| `sandbox_sql` | DuckDB de solo lectura sobre datasets sintéticos (coste 0) |
| `adaptativo` | Detección determinista de debilidad; la IA solo redacta la explicación |
| `costos` | Presupuesto global, cuotas por usuario y degradación elegante |
| `schemas` | Esquemas Pydantic de salida que consumen las rutas de §7 |

Este módulo **no posee tablas propias** (§1.3): escribe en `generation_jobs`,
`prompt_templates` y `content_provenance` (archivo `ingestion.py`) y en las tablas de
`content`.
"""

from __future__ import annotations

from app.modules.ai.proveedor import (
    ProveedorIA,
    RespuestaIA,
    SolicitudIA,
    UsoIA,
    crear_proveedor,
)

__all__ = [
    "ProveedorIA",
    "RespuestaIA",
    "SolicitudIA",
    "UsoIA",
    "crear_proveedor",
]
