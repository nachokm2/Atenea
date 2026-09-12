"""Banco de pruebas del camino de IA: de un documento real a una ruta jugable.

Recorre lo que ocurre cuando alguien sube material y pide aprender: ingesta,
fragmentación, embeddings, diseño de la ruta y redacción del primer módulo. Al
final enseña lo que importa de verdad, que no es que responda 200:

- qué estructura salió (módulos, temas, lecciones, preguntas),
- cómo está escrita una lección y si sus preguntas tienen sentido,
- de qué fragmento del documento sale cada cosa (trazabilidad),
- y cuánto costó, en tokens y en dólares.

Funciona igual con el proveedor simulado y con Claude real, así que sirve para
dos cosas distintas: comprobar que la maquinaria está bien conectada (sin gastar
nada) y medir la calidad y el costo reales.

    # Sin coste, para verificar el circuito:
    python scripts/probar_ia.py

    # Con Claude real (exige ANTHROPIC_API_KEY en el .env):
    python scripts/probar_ia.py --proveedor claude --documento mi_apunte.pdf

Requisitos: la API levantada (`python -m uvicorn app.main:app --port 8010`
desde `backend/`) y la base migrada y sembrada.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass

RAIZ = Path(__file__).resolve().parent.parent
BACKEND = RAIZ / "backend"
BASE = os.environ.get("ATENEA_API", "http://127.0.0.1:8010/api/v1")

VERDE = "\033[92m"
ROJO = "\033[91m"
GRIS = "\033[90m"
NEGRITA = "\033[1m"
FIN = "\033[0m"

#: Material por defecto: un documento técnico real, en español, del propio repo.
DOCUMENTO_POR_DEFECTO = RAIZ / "docs" / "auditoria" / "04-arquitectura-ia-rag.md"

OBJETIVO_POR_DEFECTO = (
    "Quiero entender cómo funciona una arquitectura RAG: qué hace cada etapa, "
    "desde que se sube un documento hasta que el modelo responde con sus fuentes."
)


def titulo(texto: str) -> None:
    print(f"\n{NEGRITA}{texto}{FIN}")
    print(GRIS + "─" * min(70, len(texto) + 10) + FIN)


def dato(etiqueta: str, valor: object) -> None:
    print(f"  {etiqueta:<34} {valor}")


def _hay_clave() -> bool:
    """¿Hay credencial de Anthropic?

    Se pregunta a la configuración de la aplicación, no a las variables de
    entorno: la clave vive en el `.env` de la raíz, que es de donde la lee el
    worker. El valor nunca se imprime.
    """
    sys.path.insert(0, str(BACKEND))
    try:
        from app.core.config import Settings  # noqa: PLC0415

        return bool((Settings().anthropic_api_key or "").strip())
    except Exception:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _esperar_api() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def _vaciar_cola() -> tuple[int, str]:
    """Ejecuta el worker hasta vaciar la cola y devuelve su salida."""
    proceso = subprocess.run(
        [sys.executable, "-m", "app.worker.principal", "--drain"],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    return proceso.returncode, (proceso.stdout or "") + (proceso.stderr or "")


def _costos(path_id: str) -> list[dict]:
    """Lee de `generation_jobs` lo que costó generar esta ruta."""
    sys.path.insert(0, str(BACKEND))
    from sqlalchemy import create_engine, text  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415

    motor = create_engine(settings.database_url)
    with motor.connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT job_type, status, provider, model_id,
                       input_tokens, cached_input_tokens, output_tokens, cost_usd,
                       progress_label, error_message
                FROM generation_jobs
                WHERE learning_path_id = :ruta
                ORDER BY created_at
                """
            ),
            {"ruta": path_id},
        ).mappings()
        return [dict(f) for f in filas]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prueba el camino de IA de Atenea.")
    parser.add_argument("--documento", default=str(DOCUMENTO_POR_DEFECTO))
    parser.add_argument("--objetivo", default=OBJETIVO_POR_DEFECTO)
    parser.add_argument("--nivel", default="beginner", choices=["beginner", "intermediate", "advanced"])
    parser.add_argument(
        "--conocimiento",
        default="Arquitectura RAG",
        help="Sobre qué conocimiento se aprende; será el territorio del mapa.",
    )
    parser.add_argument(
        "--proveedor",
        default=None,
        choices=["mock", "claude"],
        help="Sobrescribe AI_PROVIDER solo para esta ejecución del worker.",
    )
    parser.add_argument("--espera", type=int, default=900, help="Segundos máximos de generación.")
    args = parser.parse_args(argv)

    documento = Path(args.documento)
    if not documento.is_file():
        print(f"{ROJO}No existe el documento: {documento}{FIN}")
        return 1
    if not _esperar_api():
        print(f"{ROJO}La API no responde en {BASE}.{FIN}")
        print("Levántala con:  cd backend && python -m uvicorn app.main:app --port 8010")
        return 1

    if args.proveedor:
        os.environ["AI_PROVIDER"] = args.proveedor

    proveedor = os.environ.get("AI_PROVIDER", "(el del .env)")
    titulo("Punto de partida")
    dato("documento", f"{documento.name} ({documento.stat().st_size / 1024:.0f} KB)")
    dato("objetivo", args.objetivo[:60] + "…")
    dato("conocimiento", args.conocimiento)
    dato("proveedor de IA", proveedor)
    if proveedor == "claude" and not _hay_clave():
        print()
        print(f"{ROJO}Falta ANTHROPIC_API_KEY: ponla en el .env de la raíz.{FIN}")
        return 1

    cliente = httpx.Client(base_url=BASE, timeout=120.0)

    # ---------------------------------------------------------------- cuenta
    correo = f"ia-{uuid.uuid4().hex[:10]}@aprendices-atenea.cl"
    r = cliente.post("/auth/register", json={"email": correo, "password": "Reino2026seguro"})
    if r.status_code >= 400:
        print(f"{ROJO}No se pudo crear la cuenta: {r.text[:300]}{FIN}")
        return 1
    cliente.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    cliente.post(
        "/characters",
        json={"name": "Cata de IA", "archetype": "arcane"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    # ------------------------------------------------------------- documento
    titulo("1 · Ingesta del material")
    inicio = time.time()
    r = cliente.post(
        "/documents",
        files={"file": (documento.name, documento.read_bytes(), "text/markdown")},
        data={"title": documento.stem},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    if r.status_code >= 400:
        print(f"{ROJO}Falló la subida: {r.status_code} {r.text[:400]}{FIN}")
        return 1
    creado = r.json()
    # La respuesta es `DocumentCreatedOut {document, job, duplicate, retry}`.
    documento_id = str((creado.get("document") or creado).get("id"))
    dato("documento subido", documento_id)
    if creado.get("duplicate"):
        dato("ya existía", "sí: se reutiliza la ingesta anterior")

    codigo, salida = _vaciar_cola()
    dato("ingesta procesada en", f"{time.time() - inicio:.0f} s")
    if codigo != 0:
        print(f"{ROJO}El worker falló durante la ingesta:{FIN}\n{salida[-1500:]}")
        return 1

    detalle = cliente.get(f"/documents/{documento_id}").json()
    version = detalle.get("current_version") or {}
    dato("estado", detalle.get("status"))
    dato("tipo detectado", detalle.get("document_type"))
    dato("fragmentos", version.get("chunk_count", "(no informado)"))
    dato("palabras", version.get("word_count", "(no informado)"))

    # ------------------------------------------------------------------ ruta
    titulo("2 · Diseño de la ruta")
    inicio = time.time()
    r = cliente.post(
        "/paths",
        json={
            "goal_text": args.objetivo,
            "declared_level": args.nivel,
            "source_mode": "con_fuente",
            "document_ids": [documento_id],
            "knowledge_area_hint": args.conocimiento,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    if r.status_code >= 400:
        print(f"{ROJO}No se pudo crear la ruta: {r.status_code} {r.text[:400]}{FIN}")
        return 1
    path_id = r.json().get("path", {}).get("path_id") or r.json().get("path_id")
    dato("ruta encolada", path_id)

    codigo, salida = _vaciar_cola()
    if codigo != 0:
        print(f"{ROJO}El worker falló generando:{FIN}\n{salida[-2000:]}")

    # Confirmar la ruta es lo que encola la Fase B: la redacción del primer
    # módulo. Sin este paso el usuario tendría el esqueleto y ninguna lección.
    confirmacion = cliente.post(
        f"/paths/{path_id}/confirm",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    dato("ruta confirmada", confirmacion.status_code)
    if confirmacion.status_code >= 400:
        print(f"{GRIS}  {confirmacion.text[:200]}{FIN}")
    _vaciar_cola()

    # El worker ya vació la cola; aquí solo se le dan unas pocas vueltas más por
    # si el diseño encoló la generación del primer módulo.
    limite = time.time() + args.espera
    estado = {}
    vueltas = 0
    while time.time() < limite and vueltas < 6:
        estado = cliente.get(f"/paths/{path_id}/generation").json()
        if estado.get("status") in {"ready", "failed", "completed", "succeeded"}:
            break
        if estado.get("first_module_ready"):
            break
        codigo_w, salida_w = _vaciar_cola()
        if codigo_w != 0:
            print(f"{ROJO}El worker falló:{FIN}")
            print(salida_w[-1200:])
            break
        vueltas += 1
        time.sleep(1)
    dato("generación", f"{estado.get('status')} · {estado.get('progress_pct', 0)}%")
    dato("tiempo total", f"{time.time() - inicio:.0f} s")
    if estado.get("status") == "failed":
        print(f"{ROJO}La generación falló: {estado}{FIN}")

    # -------------------------------------------------------------- contenido
    titulo("3 · Qué escribió")
    ruta = cliente.get(f"/paths/{path_id}").json()
    modulos = ruta.get("modules") or []
    dato("título", ruta.get("title") or ruta.get("path", {}).get("title"))
    dato("módulos", len(modulos))

    lecciones: list[dict] = []
    for modulo in modulos:
        print(f"\n  {NEGRITA}{modulo.get('position', '?')}. {modulo.get('title')}{FIN}")
        if modulo.get("summary"):
            print(f"     {GRIS}{modulo['summary'][:150]}{FIN}")
        for tema in modulo.get("topics") or []:
            propias = tema.get("lessons") or []
            lecciones.extend(propias)
            print(f"     · {tema.get('title')} {GRIS}({len(propias)} lecciones){FIN}")

    if not lecciones:
        print(f"\n{ROJO}No se generó ninguna lección. Revisa el registro del worker.{FIN}")
        print(salida[-1200:])
        return 1

    titulo("4 · Una lección por dentro")
    leccion = cliente.get(f"/lessons/{lecciones[0].get('lesson_id') or lecciones[0].get('id')}").json()
    print(f"  {NEGRITA}{leccion.get('title')}{FIN}")
    for bloque in (leccion.get("blocks") or [])[:4]:
        cuerpo = str(bloque.get("content") or bloque.get("body") or "")
        print(f"\n  [{bloque.get('block_type', '?')}] {cuerpo[:320].strip()}")
    procedencia = leccion.get("provenance") or []
    dato("\n  bloques", len(leccion.get("blocks") or []))
    dato("  con procedencia", f"{len(procedencia)} referencias al documento")
    for p in procedencia[:3]:
        fragmento = str(p.get("chunk_id") or "")[:8]
        print(f"    {GRIS}← fragmento {fragmento} · origen {p.get('origin', '?')} "
              f"· puesto {p.get('retrieval_rank', '?')} en la recuperación{FIN}")

    titulo("5 · Las preguntas")
    actividad = cliente.post(
        f"/lessons/{leccion.get('lesson_id') or leccion.get('id')}/start",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    ).json()
    preguntas = actividad.get("questions") or []
    dato("preguntas", len(preguntas))
    for pregunta in preguntas[:4]:
        tipo = pregunta.get("question_type") or pregunta.get("type")
        enunciado = pregunta.get("stem") or "(sin enunciado)"
        print()
        print(f"  [{tipo}] {enunciado}")
        if pregunta.get("learning_objective"):
            print(f"     {GRIS}objetivo: {pregunta['learning_objective']}{FIN}")
        cuerpo = pregunta.get("body") or {}
        opciones = cuerpo.get("options") or cuerpo.get("choices") or []
        for opcion in opciones[:4]:
            texto = opcion.get("text") if isinstance(opcion, dict) else opcion
            print(f"     {GRIS}- {texto}{FIN}")
        if not opciones and cuerpo:
            print(f"     {GRIS}{str(cuerpo)[:160]}{FIN}")
    fuga = [p for p in preguntas if "answer_key" in str(p)]
    print(f"\n  {'✓' if not fuga else '✗'} la clave de respuesta no viaja al cliente")

    # ----------------------------------------------------------------- costos
    titulo("6 · Lo que costó")
    trabajos = _costos(path_id)
    if not trabajos:
        print("  (sin trabajos registrados)")
        return 0
    print(f"  {'trabajo':<22}{'modelo':<20}{'entrada':>9}{'caché':>9}{'salida':>9}{'USD':>10}")
    tot_in = tot_cache = tot_out = 0
    tot_usd = 0.0
    for t in trabajos:
        tot_in += t["input_tokens"] or 0
        tot_cache += t["cached_input_tokens"] or 0
        tot_out += t["output_tokens"] or 0
        tot_usd += float(t["cost_usd"] or 0)
        print(
            f"  {str(t['job_type'])[:21]:<22}{str(t['model_id'] or '-')[:19]:<20}"
            f"{t['input_tokens'] or 0:>9}{t['cached_input_tokens'] or 0:>9}"
            f"{t['output_tokens'] or 0:>9}{float(t['cost_usd'] or 0):>10.4f}"
        )
    print(f"  {'TOTAL':<42}{tot_in:>9}{tot_cache:>9}{tot_out:>9}{tot_usd:>10.4f}")

    if tot_usd == 0 and (tot_in or tot_out):
        # El proveedor simulado cuenta los tokens que gastaría el real pero no
        # cobra. Con esa cuenta se puede proyectar el costo antes de gastarlo.
        precios = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0),
                   "claude-haiku-4-5": (1.0, 5.0)}
        proyectado = 0.0
        for t in trabajos:
            entrada, salida = precios.get(str(t["model_id"]), (0.0, 0.0))
            proyectado += (t["input_tokens"] or 0) / 1e6 * entrada
            proyectado += (t["output_tokens"] or 0) / 1e6 * salida
        print()
        print(f"  {GRIS}Con Claude real, estos mismos tokens costarían "
              f"unos {proyectado:.3f} USD.{FIN}")

    fallidos = [t for t in trabajos if t["status"] not in ("SUCCEEDED", "succeeded", "DONE", "done")]
    if fallidos:
        print(f"\n  {ROJO}Trabajos no completados:{FIN}")
        for t in fallidos:
            print(f"    {t['job_type']} · {t['status']} · {(t['error_message'] or '')[:120]}")

    print(f"\n{VERDE}Recorrido de IA completo.{FIN}")
    if proveedor == "mock":
        print(f"{GRIS}Fue con el proveedor simulado: el circuito está bien conectado, "
              f"pero la calidad y el costo reales solo se ven con --proveedor claude.{FIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
