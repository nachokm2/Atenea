"""Worker de Atenea: la cola de trabajos y el bucle que la consume.

Contrato §1.2 («Hosting: Railway — API + worker + Postgres/pgvector»), §3.3
(`generation_jobs` **es** la cola) y §7.5 (`GET /jobs/{id}`, `GET /paths/{id}/generation`).

Dos piezas, con una frontera deliberada:

* :mod:`app.worker.cola` — **primitivas de cola** sobre `generation_jobs`: encolar, tomar
  con `FOR UPDATE SKIP LOCKED`, progreso, pasos persistidos, reintentos con retroceso
  exponencial, cancelación. La usan también los routers de la API para encolar, así que
  no sabe nada de cómo se ejecuta un trabajo.
* :mod:`app.worker.principal` — **el bucle**: toma un trabajo, lo despacha al módulo que
  sabe hacerlo (`ingestion` para la ingesta, `ai` para la generación) y lo cierra. Se
  arranca con ``python -m app.worker.principal`` y es **seguro correr varias instancias**.

No hay Redis ni broker: PostgreSQL es la única pieza de datos del sistema.
"""

from __future__ import annotations
