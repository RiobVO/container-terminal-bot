"""Экспорт CSV для импорта в 1С.

Один плоский файл без листов-месяцев: строка на контейнер, сортировка
по дате прибытия. Формат под 1С: разделитель «;», кодировка UTF-8 с BOM
(utf-8-sig), запятая как десятичный разделитель, даты ДД.ММ.ГГГГ.

Данные те же, что у xlsx-генератора: уже отфильтрованный список
контейнеров готовит вызывающий хэндлер, тарификацию считает
``services.calculator.calculate_container_cost``.
"""
import csv
import logging
from pathlib import Path

from services.calculator import calculate_container_cost
# Хелперы xlsx-генератора переиспользуются осознанно, чтобы не
# дублировать доступ к полям, парсинг дат, сортировку и карту статусов.
from services.report_generator import STATUS_MAP, _get, _parse_date, _sort_rows

logger = logging.getLogger(__name__)

HEADERS: tuple[str, ...] = (
    "Номер контейнера",
    "Компания",
    "Тип",
    "Дата прибытия",
    "Дата убытия",
    "Статус",
    "Дней на терминале",
    "Входной сбор",
    "Хранение",
    "Итого",
)

DELIMITER = ";"
ENCODING = "utf-8-sig"


def _format_money(value: float) -> str:
    """Сумма с двумя знаками и запятой как десятичным разделителем (1С)."""
    return f"{value:.2f}".replace(".", ",")


def _format_date(val: str | None) -> str:
    """Дата БД → «ДД.ММ.ГГГГ»; пустая строка, если даты нет."""
    dt = _parse_date(val)
    return dt.strftime("%d.%m.%Y") if dt else ""


def _build_row(c, settings: dict) -> list[str]:
    """Одна строка CSV: реквизиты контейнера + тарификация."""
    cost = calculate_container_cost(
        c, settings,
        comp_entry_fee=_get(c, "comp_entry_fee"),
        comp_free_days=_get(c, "comp_free_days"),
        comp_storage_rate=_get(c, "comp_storage_rate"),
        comp_storage_period_days=_get(c, "comp_storage_period_days"),
    )
    return [
        _get(c, "display_number") or "",
        _get(c, "company_name") or "—",
        _get(c, "type") or "—",
        _format_date(_get(c, "arrival_date")),
        _format_date(_get(c, "departure_date")),
        STATUS_MAP.get(c["status"], c["status"]),
        str(cost["days"]),
        # «Входной сбор» — начисленная сумма (0 для in_transit), чтобы
        # сходилось: входной сбор + хранение = итого.
        _format_money(cost["entry"]),
        _format_money(cost["storage"]),
        _format_money(cost["total"]),
    ]


def build_csv_report(
    containers: list,
    settings: dict[str, float],
    out_dir: Path,
    filename: str,
) -> Path:
    """Генерирует плоский CSV-файл для импорта в 1С.

    Контейнеры уже отфильтрованы вызывающим кодом (по компании/статусу).
    Если список пуст — в файле остаётся только строка заголовков.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    # newline="" обязателен для модуля csv: он сам пишет CRLF.
    with open(path, "w", encoding=ENCODING, newline="") as f:
        writer = csv.writer(f, delimiter=DELIMITER)
        writer.writerow(HEADERS)
        for c in _sort_rows(containers):
            writer.writerow(_build_row(c, settings))
    logger.info("CSV для 1С: %s (контейнеров: %d)", path, len(containers))
    return path
