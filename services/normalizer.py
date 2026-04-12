"""Нормализация номера контейнера."""
import re

_CONTAINER_RE = re.compile(r"^[A-Z]{4}\d{7}$")


def normalize_container_number(raw: str) -> tuple[str, str] | None:
    """
    Нормализует номер контейнера.

    Возвращает (normalized, display) или None при невалидном формате.
    normalized = "CASS1234567" (для БД и поиска)
    display = "CASS 1234567" (для показа)
    """
    cleaned = raw.strip().upper().replace(" ", "").replace("-", "")
    if not _CONTAINER_RE.match(cleaned):
        return None
    display = f"{cleaned[:4]} {cleaned[4:]}"
    return cleaned, display
