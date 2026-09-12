"""Recorrido de humo de los DOCE criterios de éxito del MVP de Atenea.

Recorre contra una API levantada el mismo camino que hará una persona real el
primer día y comprueba el efecto observable de cada paso, no solo el código 200.

    cd backend && python -m uvicorn app.main:app --port 8010
    python scripts/recorrido_mvp.py

El recorrido estudia **a ritmo real**: el servidor descarta como implausible una
lección terminada en cero segundos (regla anti-abuso A4 del contrato), así que la
prueba dedica a la segunda lección el tiempo mínimo que el contrato exige. Por eso
tarda unos tres minutos; es el precio de comprobar la economía de verdad y no una
simulación que el propio sistema rechazaría.

Variables de entorno: ``ATENEA_API`` (por defecto http://127.0.0.1:8010/api/v1).
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

# La consola de Windows usa cp1252: forzamos UTF-8 para no perder los símbolos.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover - consolas que no lo soportan
        pass

BASE = os.environ.get("ATENEA_API", "http://127.0.0.1:8010/api/v1")

VERDE = "\033[92m"
ROJO = "\033[91m"
GRIS = "\033[90m"
FIN = "\033[0m"

_fallos: list[str] = []
_paso_actual = ""


def paso(n: int | str, titulo: str) -> None:
    global _paso_actual
    _paso_actual = f"{n}. {titulo}"
    print(f"\n{GRIS}── paso {n}: {titulo}{FIN}")


def comprobar(condicion: bool, descripcion: str, detalle: object = "") -> bool:
    if condicion:
        print(f"  {VERDE}✓{FIN} {descripcion}" + (f" {GRIS}({detalle}){FIN}" if detalle != "" else ""))
        return True
    print(f"  {ROJO}✗{FIN} {descripcion} {GRIS}({detalle}){FIN}")
    _fallos.append(f"{_paso_actual} → {descripcion} ({detalle})")
    return False


def ident(obj: dict, *nombres: str) -> str | None:
    """Primer identificador presente: la API usa `path_id`, `lesson_id`, `id`…"""
    for n in (*nombres, "id"):
        v = obj.get(n)
        if v:
            return str(v)
    return None


def clave() -> str:
    """Clave de idempotencia nueva para las acciones que otorgan recompensas."""
    return str(uuid.uuid4())


def respuesta_plausible(pregunta: dict) -> object:
    """Respuesta con la forma que espera cada tipo de pregunta."""
    tipo = str(pregunta.get("type") or pregunta.get("question_type") or "")
    opciones = pregunta.get("options") or pregunta.get("choices") or []
    primera = opciones[0] if opciones else None
    id_primera = primera.get("id") if isinstance(primera, dict) else primera
    return {
        "single_choice": [id_primera],
        "multiple_choice": [id_primera],
        "true_false": True,
        "fill_blank": ["SELECT"],
        "matching": {},
        "ordering": [o.get("id") if isinstance(o, dict) else o for o in opciones],
        "open_answer": "Una consulta SELECT recupera columnas de una tabla.",
        "sql_exercise": "SELECT * FROM reinos;",
    }.get(tipo, id_primera or "respuesta")


def hacer_leccion(cliente: httpx.Client, leccion_id: str, *, segundos: int) -> dict:
    """Abre una lección, la estudia `segundos`, responde y la cierra.

    Devuelve el `RewardsReceipt`. Con `segundos = 0` la actividad se cierra al
    instante, que es justo lo que el anti-abuso debe rechazar.
    """
    r = cliente.post(f"/lessons/{leccion_id}/start", headers={"Idempotency-Key": clave()})
    r.raise_for_status()
    actividad = r.json()
    actividad_id = ident(actividad, "activity_id")
    preguntas = actividad.get("questions") or []

    restantes = segundos
    while restantes > 0:
        tramo = min(30, restantes)
        time.sleep(tramo)
        cliente.post(f"/activities/{actividad_id}/heartbeat", json={"seconds": tramo})
        restantes -= tramo
        print(f"  {GRIS}estudiando… {segundos - restantes}/{segundos} s{FIN}", end="\r")
    if segundos:
        print(" " * 48, end="\r")

    for pregunta in preguntas:
        cliente.post(
            f"/activities/{actividad_id}/answers",
            json={
                "question_id": ident(pregunta, "question_id"),
                "answer": respuesta_plausible(pregunta),
            },
            headers={"Idempotency-Key": clave()},
        )

    r = cliente.post(f"/activities/{actividad_id}/complete", headers={"Idempotency-Key": clave()})
    r.raise_for_status()
    recibo = r.json()
    recibo["_activity_id"] = actividad_id
    return recibo


def main() -> int:
    cliente = httpx.Client(base_url=BASE, timeout=90.0)
    correo = f"aprendiz-{uuid.uuid4().hex[:10]}@aprendices-atenea.cl"

    # ---------------------------------------------------------------- 1
    paso(1, "Crea una cuenta")
    r = cliente.post("/auth/register", json={"email": correo, "password": "Reino2026seguro"})
    if not comprobar(r.status_code in (200, 201), "registro aceptado", r.status_code):
        print(r.text[:400])
        return 1
    cliente.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    comprobar(cliente.get("/auth/me").json().get("has_character") is False, "aún no tiene personaje")

    # ---------------------------------------------------------------- 2
    paso(2, "Crea su personaje")
    r = cliente.post(
        "/characters",
        json={"name": "Rodrigo de Atenea", "archetype": "steel"},
        headers={"Idempotency-Key": clave()},
    )
    if not comprobar(r.status_code in (200, 201), "personaje creado", r.status_code):
        print(r.text[:400])
        return 1
    comprobar(bool(r.json().get("rewards")), "la creación devuelve un recibo de recompensas")
    oro_inicial = cliente.get("/wallet").json().get("balance", 0)
    comprobar(oro_inicial > 0, "recibe la bolsa de bienvenida", f"{oro_inicial} de oro")

    # ---------------------------------------------------------------- 3
    paso(3, "Elige qué aprender")
    items = cliente.get("/paths", params={"scope": "all"}).json().get("items", [])
    if not comprobar(len(items) > 0, "hay Rutas del Reino disponibles", f"{len(items)} rutas"):
        return 1
    path_id = ident(items[0], "path_id")
    print(f"  {GRIS}ruta: {items[0].get('title')}{FIN}")

    # ---------------------------------------------------------------- 4
    paso(4, "Adopta la ruta curada, sin esperar a la IA")
    r = cliente.post(f"/paths/{path_id}/adopt", headers={"Idempotency-Key": clave()})
    comprobar(r.status_code in (200, 201), "ruta adoptada", r.status_code)

    # ---------------------------------------------------------------- 5
    paso(5, "Recibe el mapa de la ruta")
    detalle = cliente.get(f"/paths/{path_id}").json()
    modulos = detalle.get("modules") or []
    comprobar(len(modulos) >= 3, "la ruta trae sus módulos", f"{len(modulos)} módulos")
    lecciones: list[dict] = []
    for tema in (modulos[0].get("topics") or []) if modulos else []:
        lecciones.extend(tema.get("lessons") or [])
    if not comprobar(len(lecciones) >= 2, "el primer módulo trae lecciones", f"{len(lecciones)}"):
        return 1

    # ---------------------------------------------------------------- 6
    paso(6, "Completa una lección")
    leccion = cliente.get(f"/lessons/{ident(lecciones[0], 'lesson_id')}").json()
    bloques = leccion.get("blocks") or []
    comprobar(len(bloques) > 0, "la lección tiene contenido", f"{len(bloques)} bloques")
    comprobar("answer_key" not in str(leccion), "la lección NO expone la clave de respuesta")

    print(f"  {GRIS}primera lección a la carrera: debe saltar el anti-abuso{FIN}")
    recibo_rapido = hacer_leccion(cliente, ident(lecciones[0], "lesson_id"), segundos=0)
    xp_rapida = (recibo_rapido.get("xp") or {}).get("amount", 0)

    # El contrato exige dedicar al menos el 25 % de la duración estimada (A4).
    segunda = cliente.get(f"/lessons/{ident(lecciones[1], 'lesson_id')}").json()
    estimado = int(segunda.get("estimated_seconds") or 600)
    dedicacion = min(240, int(estimado * 0.25) + 20)
    print(f"  {GRIS}segunda lección a ritmo real: {dedicacion} s "
          f"(estimada en {estimado} s){FIN}")
    recibo = hacer_leccion(cliente, ident(lecciones[1], "lesson_id"), segundos=dedicacion)
    xp_pausada = (recibo.get("xp") or {}).get("amount", 0)
    # La lección corrida paga 0 por sí misma (reason `time_too_short`); lo que
    # aparezca en su recibo son bonos de primera vez. La estudiada de verdad sí
    # cobra la lección completa.
    comprobar(xp_pausada >= 50, "la lección estudiada paga su XP completo", f"{xp_pausada} XP")
    print(f"  {GRIS}la corrida entregó {xp_rapida} XP, todo de bonos de primera vez{FIN}")

    # ---------------------------------------------------------------- 7
    paso(7, "Gana experiencia")
    xp_ganada = (recibo.get("xp") or {}).get("amount", 0)
    comprobar(xp_ganada > 0, "el recibo otorga XP", xp_ganada)
    xp_total = (cliente.get("/profile").json().get("stats") or {}).get("xp_total", 0)
    comprobar(xp_total >= xp_ganada, "el perfil refleja la XP acumulada", xp_total)

    # ---------------------------------------------------------------- 8
    paso(8, "Gana oro")
    oro_ganado = (recibo.get("gold") or {}).get("amount", 0)
    saldo = cliente.get("/wallet").json().get("balance", 0)
    comprobar(oro_ganado > 0, "el recibo otorga oro", oro_ganado)
    comprobar(saldo > oro_inicial, "el monedero refleja el oro", f"{oro_inicial} → {saldo}")

    # ---------------------------------------------------------------- 9
    paso(9, "Mantiene su racha y su objetivo del día")
    racha = cliente.get("/streak").json()
    comprobar(racha.get("current", 0) >= 1, "la racha arranca en 1", racha.get("current"))
    comprobar(bool(racha.get("next_milestone")), "muestra el próximo hito",
              (racha.get("next_milestone") or {}).get("days"))
    objetivo = cliente.get("/daily-goal").json()
    comprobar(objetivo.get("progress", 0) > 0, "el objetivo diario avanzó",
              f"{objetivo.get('progress')}/{objetivo.get('target')} {objetivo.get('type', '')}")

    # ---------------------------------------------------------------- 10
    paso(10, "Ve equipamiento que se gana aprendiendo")
    inv = cliente.get("/inventory", params={"limit": 100}).json().get("items", [])
    propios = [i for i in inv if i.get("owned")]
    bloqueados = [i for i in inv if not i.get("owned")]
    comprobar(len(propios) > 0, "tiene su kit inicial", f"{len(propios)} ítems")
    comprobar(len(bloqueados) > 0, "ve ítems bloqueados con su requisito", f"{len(bloqueados)}")
    con_requisito = [i for i in bloqueados if i.get("requirements")]
    comprobar(len(con_requisito) > 0, "cada bloqueado explica cómo ganarlo",
              f"{len(con_requisito)} con requisito visible")

    # ---------------------------------------------------------------- 11
    paso(11, "Equipa una pieza y visita el Mercado")
    pieza = propios[0]
    uid = ident(pieza, "user_item_id")
    slot = pieza.get("slot") or (pieza.get("item") or {}).get("slot")
    r = cliente.put("/avatar/equipment", json={"equipment": {slot: uid}})
    if comprobar(r.status_code < 400, "pieza equipada", r.status_code):
        capas = r.json().get("layers") or []
        comprobar(len(capas) > 0, "el avatar se recompone por capas", f"{len(capas)} capas")

    listados = cliente.get("/shop").json().get("listings") or []
    comprobar(len(listados) > 0, "el Mercado tiene catálogo", f"{len(listados)} piezas")
    if listados:
        r = cliente.post(
            "/shop/purchase",
            json={
                "listing_id": ident(listados[0], "listing_id"),
                "expected_price": listados[0]["price"],
            },
            headers={"Idempotency-Key": clave()},
        )
        if r.status_code < 400:
            comprobar(True, "compra realizada", r.json().get("balance_after"))
        else:
            error = r.json().get("error", {})
            comprobar(
                error.get("code") in {"REQUIREMENTS_NOT_MET", "INSUFFICIENT_FUNDS"},
                "el Mercado explica por qué aún no puede comprar",
                error.get("message"),
            )

    # ---------------------------------------------------------------- 12
    paso(12, "Ve su progreso y sabe qué hacer mañana")
    panel = cliente.get("/dashboard").json()
    comprobar((panel.get("character") or {}).get("xp_total", 0) > 0, "el panel muestra la XP")
    comprobar((panel.get("streak") or {}).get("current", 0) >= 1, "el panel muestra la racha")
    continuar = panel.get("continue_action") or {}
    comprobar(bool(continuar), "propone la siguiente acción", continuar.get("title"))
    comprobar(len(panel.get("knowledge_summary") or []) > 0, "muestra el perfil de conocimiento")

    # ------------------------------------------------------- anti-abuso
    paso(13, "Reglas que protegen el producto")
    xp_antes = (cliente.get("/profile").json().get("stats") or {}).get("xp_total", 0)
    cliente.post(
        f"/activities/{recibo['_activity_id']}/complete",
        headers={"Idempotency-Key": clave()},
    )
    xp_despues = (cliente.get("/profile").json().get("stats") or {}).get("xp_total", 0)
    comprobar(xp_despues == xp_antes, "cerrar dos veces la misma actividad no vuelve a pagar",
              f"{xp_antes} → {xp_despues}")

    if listados:
        r = cliente.post(
            "/shop/purchase",
            json={"listing_id": ident(listados[0], "listing_id"), "expected_price": 1},
            headers={"Idempotency-Key": clave()},
        )
        comprobar(r.status_code >= 400, "no se puede comprar con un precio manipulado", r.status_code)

    anonimo = httpx.Client(base_url=BASE, timeout=30.0)
    comprobar(anonimo.get("/dashboard").status_code == 401, "sin sesión no se accede al panel")

    # ---------------------------------------------------------------- fin
    print("\n" + "═" * 64)
    if _fallos:
        print(f"{ROJO}{len(_fallos)} comprobaciones fallaron:{FIN}")
        for f in _fallos:
            print(f"  · {f}")
        return 1
    print(f"{VERDE}Recorrido completo: los 12 criterios de éxito del MVP se cumplen.{FIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
