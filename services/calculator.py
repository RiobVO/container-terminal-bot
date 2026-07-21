"""Расчёт стоимости хранения контейнера.

Модель тарифа (per-company, с фолбэком на global_settings):
- entry_fee $ — стоимость входа.
- free_days — сколько дней после прибытия хранение бесплатное.
- storage_rate $ — ставка платного хранения за один период.
- storage_period_days — длительность периода в днях. 1 = ежедневный тариф,
  30 = ежемесячный, любое другое N — «каждые N дней».

Периоды считаются через math.ceil: даже неполный период тарифицируется
полностью.
"""
import math
from datetime import datetime


def calculate_container_cost(
    container,
    settings: dict[str, float],
    *,
    comp_entry_fee: float | None = None,
    comp_free_days: int | None = None,
    comp_storage_rate: float | None = None,
    comp_storage_period_days: int | None = None,
) -> dict:
    """Рассчитывает стоимость контейнера по гибкой модели тарифа.

    container — строка БД (dict-like) с полями status, arrival_date,
    departure_date.
    settings — global_settings как {key: value}.
    comp_* — индивидуальные параметры компании (None = стандартный).

    Возвращает словарь с ключами:
    - entry, storage, total — денежные суммы
    - days — дней на терминале
    - billable_days — дней подлежащих оплате (days - free_days, ≥ 0)
    - periods — число полных периодов к оплате
    - period_days — фактический storage_period_days
    - entry_fee, free_days, storage_rate — фактические значения, которые
      применялись
    - entry_is_custom, free_days_is_custom, storage_rate_is_custom,
      storage_period_is_custom — флаги, что значение взято от компании
    """
    default_entry = float(settings.get("default_entry_fee", 20.0))
    default_free_days = int(settings.get("default_free_days", 30))
    default_storage_rate = float(settings.get("default_storage_rate", 20.0))
    default_storage_period = int(
        settings.get("default_storage_period_days", 30)
    )

    entry_fee = (
        comp_entry_fee if comp_entry_fee is not None else default_entry
    )
    free_days = (
        int(comp_free_days) if comp_free_days is not None else default_free_days
    )
    storage_rate = (
        comp_storage_rate
        if comp_storage_rate is not None
        else default_storage_rate
    )
    period_days = (
        int(comp_storage_period_days)
        if comp_storage_period_days is not None
        else default_storage_period
    )
    if period_days < 1:
        period_days = 1

    entry_is_custom = comp_entry_fee is not None
    free_days_is_custom = comp_free_days is not None
    storage_rate_is_custom = comp_storage_rate is not None
    storage_period_is_custom = comp_storage_period_days is not None

    status = container["status"]
    arrival_raw = container["arrival_date"]

    if status == "in_transit" or arrival_raw is None:
        return {
            "entry": 0.0,
            "storage": 0.0,
            "total": 0.0,
            "days": 0,
            "billable_days": 0,
            "periods": 0,
            "period_days": period_days,
            "entry_fee": entry_fee,
            "free_days": free_days,
            "storage_rate": storage_rate,
            "entry_is_custom": entry_is_custom,
            "free_days_is_custom": free_days_is_custom,
            "storage_rate_is_custom": storage_rate_is_custom,
            "storage_period_is_custom": storage_period_is_custom,
        }

    departure_raw = container["departure_date"]

    arrival = _parse_dt(arrival_raw)
    end = _parse_dt(departure_raw) if departure_raw else datetime.now()

    days_on_terminal = max(0, (end - arrival).days)
    billable_days = max(0, days_on_terminal - free_days)

    if period_days <= 1:
        periods = billable_days
    else:
        periods = math.ceil(billable_days / period_days) if billable_days > 0 else 0

    storage_cost = round(periods * storage_rate, 2)
    total = round(entry_fee + storage_cost, 2)

    return {
        "entry": round(entry_fee, 2),
        "storage": storage_cost,
        "total": total,
        "days": days_on_terminal,
        "billable_days": billable_days,
        "periods": periods,
        "period_days": period_days,
        "entry_fee": entry_fee,
        "free_days": free_days,
        "storage_rate": storage_rate,
        "entry_is_custom": entry_is_custom,
        "free_days_is_custom": free_days_is_custom,
        "storage_rate_is_custom": storage_rate_is_custom,
        "storage_period_is_custom": storage_period_is_custom,
    }


def _parse_dt(val: str) -> datetime:
    """Парсит дату из строки."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    raise ValueError(f"Не удалось распарсить дату: {val}")
