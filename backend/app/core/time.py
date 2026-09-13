"""Utilidades de tiempo UTC y de «día del usuario» según su zona horaria IANA.

Contrato §8.6:

- **Todo** timestamp de la base de datos y de la API es UTC (ISO 8601 con `Z`).
- `local_date` la calcula **siempre el servidor** convirtiendo `occurred_at` a
  `users.timezone`; viaja en el evento y se persiste. Ningún consumidor la recalcula.
- El corte del día es la **medianoche local** del usuario: es la pieza crítica de
  la racha, del objetivo diario y de los agregados por fecha.
- Está prohibido `datetime.now()` sin zona: aquí siempre se usa `utcnow()`.
"""

from __future__ import annotations

from datetime import UTC, date as date_type, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: Zona horaria por defecto del producto (coincide con `users.timezone`).
DEFAULT_TIMEZONE = "America/Santiago"

#: Tolerancia de sincronización cliente/servidor en minutos (`streak.sync_tolerance_min`
#: en `game_configs` es la fuente de verdad; esto es solo el respaldo).
DEFAULT_SYNC_TOLERANCE_MIN = 10

UTC = UTC


def utcnow() -> datetime:
    """Instante actual en UTC, siempre consciente de zona."""
    return datetime.now(UTC)


def get_zone(tz: str | ZoneInfo | None) -> ZoneInfo:
    """Resuelve una zona IANA; cae a la zona por defecto si el nombre no existe."""
    if isinstance(tz, ZoneInfo):
        return tz
    try:
        return ZoneInfo(tz or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def ensure_utc(dt: datetime) -> datetime:
    """Devuelve el instante en UTC.

    Un `datetime` ingenuo se interpreta como UTC (nunca como hora local del servidor).
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_zone(dt: datetime, tz: str | ZoneInfo | None) -> datetime:
    """Convierte un instante a la zona horaria indicada."""
    return ensure_utc(dt).astimezone(get_zone(tz))


def user_local_now(tz: str | ZoneInfo | None) -> datetime:
    """Momento actual expresado en la zona horaria del usuario."""
    return to_zone(utcnow(), tz)


def user_local_date(dt: datetime | None, tz: str | ZoneInfo | None) -> date_type:
    """Fecha local del usuario para un instante dado (`local_date` del contrato).

    Si `dt` es `None` se usa el instante actual. El resultado es un `date`, que es
    lo que se persiste en `streak_days.local_date`, `xp_transactions.local_date`, etc.
    """
    return to_zone(dt or utcnow(), tz).date()


def day_bounds_utc(day: date_type, tz: str | ZoneInfo | None) -> tuple[datetime, datetime]:
    """Límites en UTC `[inicio, fin)` de una fecha local del usuario.

    El fin se calcula como la medianoche local del día siguiente, de modo que los
    días de 23 o 25 horas por cambio de horario de verano quedan bien cubiertos.
    """
    zone = get_zone(tz)
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def day_start_utc(day: date_type, tz: str | ZoneInfo | None) -> datetime:
    """Medianoche local de una fecha, expresada en UTC."""
    return day_bounds_utc(day, tz)[0]


def local_day_length_hours(day: date_type, tz: str | ZoneInfo | None) -> float:
    """Duración real en horas de una fecha local (23, 24 o 25 con horario de verano)."""
    start, end = day_bounds_utc(day, tz)
    return (end - start).total_seconds() / 3600


def utc_offset_hours(dt: datetime, tz: str | ZoneInfo | None) -> float:
    """Desfase horario respecto a UTC, en horas, para un instante y una zona."""
    offset = to_zone(dt, tz).utcoffset()
    return 0.0 if offset is None else offset.total_seconds() / 3600


def timezone_shift_hours(
    from_tz: str | ZoneInfo | None,
    to_tz: str | ZoneInfo | None,
    at: datetime | None = None,
) -> float:
    """Salto horario entre dos zonas (positivo hacia el este).

    Un salto de módulo ≥ 3 h habilita el ajuste por viaje de la racha (§6.10).
    """
    moment = at or utcnow()
    return utc_offset_hours(moment, to_tz) - utc_offset_hours(moment, from_tz)


def resolve_occurred_at(
    client_timestamp: datetime | None,
    *,
    server_timestamp: datetime | None = None,
    tolerance_minutes: int = DEFAULT_SYNC_TOLERANCE_MIN,
) -> datetime:
    """Decide el `occurred_at` de un hecho del cliente (§6.10).

    Se acepta la marca del cliente si difiere de la del servidor en menos de la
    tolerancia; fuera de esa ventana manda siempre el servidor.
    """
    server = ensure_utc(server_timestamp) if server_timestamp else utcnow()
    if client_timestamp is None:
        return server
    client = ensure_utc(client_timestamp)
    if abs((client - server).total_seconds()) <= tolerance_minutes * 60:
        return client
    return server


def isoformat_z(dt: datetime) -> str:
    """Serializa un instante como ISO 8601 en UTC terminado en `Z`."""
    return ensure_utc(dt).isoformat().replace("+00:00", "Z")


def is_valid_timezone(tz: str) -> bool:
    """Indica si la cadena es una zona horaria IANA válida."""
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


__all__ = [
    "DEFAULT_SYNC_TOLERANCE_MIN",
    "DEFAULT_TIMEZONE",
    "UTC",
    "day_bounds_utc",
    "day_start_utc",
    "ensure_utc",
    "get_zone",
    "is_valid_timezone",
    "isoformat_z",
    "local_day_length_hours",
    "resolve_occurred_at",
    "timezone_shift_hours",
    "to_zone",
    "user_local_date",
    "user_local_now",
    "utc_offset_hours",
    "utcnow",
]
