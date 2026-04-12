import re
from datetime import date, datetime

CONTAINER_RE = re.compile(r"^([A-Z]{4})\s*(\d{7})$")


def normalize_container_number(raw: str) -> str | None:
    """Нормализует номер контейнера к виду 'TEMU 6275401'. Возвращает None при невалидном формате."""
    m = CONTAINER_RE.match(raw.strip().upper())
    if not m:
        return None
    return f"{m.group(1)} {m.group(2)}"


def parse_ru_date(s: str) -> date | None:
    """Парсит дату в формате ДД.ММ.ГГГГ. Возвращает None при ошибке."""
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def format_ru_date(d: date | str | None) -> str:
    """Форматирует дату в ДД.ММ.ГГГГ. Возвращает '—' при None."""
    if d is None:
        return "—"
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.strftime("%d.%m.%Y")


def now_hms() -> str:
    """Текущее время в формате HH-MM-SS для имён файлов."""
    return datetime.now().strftime("%H-%M-%S")


def calculate_total(
    arrival: date,
    departure: date | None,
    entry_fee: float,
    free_days: int,
    storage_rate: float,
    storage_period_days: int,
) -> tuple[int, float]:
    """
    Рассчитывает количество дней хранения и итоговую сумму.

    Формула:
        days_stored = (departure or today) - arrival
        billable    = max(0, days_stored - free_days)
        storage     = (billable / storage_period_days) * storage_rate
        total       = entry_fee + storage
    """
    end = departure or date.today()
    days_stored = max(0, (end - arrival).days)
    billable = max(0, days_stored - free_days)
    storage_cost = (billable / storage_period_days) * storage_rate if storage_period_days else 0.0
    return days_stored, round(entry_fee + storage_cost, 2)


def slugify_company(name: str) -> str:
    """Заменяет небезопасные для имени файла символы на '_'."""
    return re.sub(r"[^\w\-]+", "_", name, flags=re.UNICODE).strip("_") or "company"


def months_list(n: int = 12) -> list[str]:
    """Возвращает список последних n месяцев в формате YYYY-MM (от текущего к более ранним)."""
    today = date.today()
    result = []
    year, month = today.year, today.month
    for _ in range(n):
        result.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return result
