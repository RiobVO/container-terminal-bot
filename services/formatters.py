"""Общие утилиты форматирования и парсинга пользовательского ввода.

Собраны из handlers/containers.py, handlers/companies.py и
handlers/settings.py, где жили одинаковыми копиями.
"""
from datetime import datetime

# Форматы дат, в которых значения хранятся в БД.
_DB_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def fmt_dt(val: str | None) -> str:
    """Дата-время из БД → «ДД.ММ.ГГГГ ЧЧ:ММ»; пусто → «—», мусор как есть."""
    if not val:
        return "—"
    for fmt in _DB_DATE_FORMATS:
        try:
            return datetime.strptime(val, fmt).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            continue
    return val


def fmt_short_date(val: str | None) -> str:
    """Дата из БД → «ДД.ММ.ГГГГ» (без времени); пусто → «—», мусор как есть."""
    if not val:
        return "—"
    for fmt in _DB_DATE_FORMATS:
        try:
            return datetime.strptime(val, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return val


def period_label(period_days: int) -> str:
    """Человеческое описание периода начисления."""
    if period_days <= 1:
        return "ежедневный тариф"
    if period_days == 30:
        return "ежемесячный тариф"
    return f"каждые {period_days} дн."


def mark(is_custom: bool) -> str:
    """Пометка тарифного параметра: индивидуальный или стандартный."""
    return "индивидуальный" if is_custom else "стандартный"


def parse_float(text: str | None) -> float | None:
    """Число ≥ 0 из ввода пользователя (запятая допустима), иначе None."""
    try:
        v = float((text or "").strip().replace(",", "."))
        return v if v >= 0 else None
    except ValueError:
        return None


def parse_int_nonneg(text: str | None) -> int | None:
    """Целое ≥ 0 из ввода пользователя, иначе None."""
    try:
        v = int((text or "").strip())
        return v if v >= 0 else None
    except ValueError:
        return None


def parse_int_positive(text: str | None) -> int | None:
    """Целое ≥ 1 из ввода пользователя, иначе None."""
    try:
        v = int((text or "").strip())
        return v if v >= 1 else None
    except ValueError:
        return None
