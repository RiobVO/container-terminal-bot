"""Тесты services/csv_export.py: плоский CSV для импорта в 1С."""
import codecs
import csv

from services.csv_export import (
    DELIMITER,
    ENCODING,
    HEADERS,
    _format_date,
    _format_money,
    build_csv_report,
)

# Тариф стандартный: вход 20$, 30 бесплатных дней, 20$ за период 30 дней.
SETTINGS = {
    "default_entry_fee": 20.0,
    "default_free_days": 30,
    "default_storage_rate": 20.0,
    "default_storage_period_days": 30,
}


def _container(**kw) -> dict:
    """Вывезенный контейнер с фиксированными датами — расчёт детерминирован."""
    base = {
        "display_number": "TEMU 6275401",
        "company_name": "Acme",
        "type": "40HQ",
        "status": "departed",
        "arrival_date": "2026-01-10",
        "departure_date": "2026-03-15 00:00:00",
        "comp_entry_fee": None,
        "comp_free_days": None,
        "comp_storage_rate": None,
        "comp_storage_period_days": None,
    }
    base.update(kw)
    return base


def _read_rows(path) -> list[list[str]]:
    with open(path, encoding=ENCODING, newline="") as f:
        return list(csv.reader(f, delimiter=DELIMITER))


# ---------------------------------------------------------------------------
# Чистые функции форматирования
# ---------------------------------------------------------------------------


def test_format_money_decimal_comma():
    assert _format_money(60.0) == "60,00"
    assert _format_money(0.5) == "0,50"


def test_format_date_variants():
    assert _format_date("2026-01-10") == "10.01.2026"
    assert _format_date("2026-03-15 00:00:00") == "15.03.2026"
    assert _format_date(None) == ""


# ---------------------------------------------------------------------------
# Файл целиком
# ---------------------------------------------------------------------------


def test_bom_and_encoding(tmp_path):
    path = build_csv_report([_container()], SETTINGS, tmp_path, "r.csv")
    raw = path.read_bytes()
    assert raw.startswith(codecs.BOM_UTF8)
    # После BOM текст валиден как UTF-8
    assert "Номер контейнера" in raw.decode("utf-8-sig")


def test_header_row_and_delimiter(tmp_path):
    path = build_csv_report([], SETTINGS, tmp_path, "r.csv")
    text = path.read_text(encoding=ENCODING)
    first_line = text.splitlines()[0]
    assert first_line == DELIMITER.join(HEADERS)
    assert first_line.count(";") == len(HEADERS) - 1


def test_empty_containers_header_only(tmp_path):
    path = build_csv_report([], SETTINGS, tmp_path, "r.csv")
    rows = _read_rows(path)
    assert rows == [list(HEADERS)]


def test_row_values_departed(tmp_path):
    """10.01→15.03: 64 дня, 34 платных, 2 периода → хранение 40$, итого 60$."""
    path = build_csv_report([_container()], SETTINGS, tmp_path, "r.csv")
    rows = _read_rows(path)
    assert rows[1] == [
        "TEMU 6275401",
        "Acme",
        "40HQ",
        "10.01.2026",
        "15.03.2026",
        "Вывезен",
        "64",
        "20,00",
        "40,00",
        "60,00",
    ]


def test_row_in_transit_empty_dates_and_dashes(tmp_path):
    """В пути без компании и типа: пустые даты, прочерки, нулевые суммы."""
    c = _container(
        status="in_transit",
        arrival_date=None,
        departure_date=None,
        company_name=None,
        type=None,
    )
    path = build_csv_report([c], SETTINGS, tmp_path, "r.csv")
    rows = _read_rows(path)
    assert rows[1] == [
        "TEMU 6275401", "—", "—", "", "", "В пути",
        "0", "0,00", "0,00", "0,00",
    ]


def test_rows_sorted_by_arrival_date(tmp_path):
    late = _container(display_number="LATE 1111111", arrival_date="2026-02-01")
    early = _container(display_number="EARL 2222222", arrival_date="2026-01-01")
    path = build_csv_report([late, early], SETTINGS, tmp_path, "r.csv")
    rows = _read_rows(path)
    assert [r[0] for r in rows[1:]] == ["EARL 2222222", "LATE 1111111"]


def test_semicolon_in_company_name_quoted(tmp_path):
    """Точка с запятой внутри поля экранируется и не ломает разбор."""
    c = _container(company_name='ООО "Ромашка; и Ко"')
    path = build_csv_report([c], SETTINGS, tmp_path, "r.csv")
    rows = _read_rows(path)
    assert rows[1][1] == 'ООО "Ромашка; и Ко"'
    assert len(rows[1]) == len(HEADERS)


def test_company_tariff_applied(tmp_path):
    """Индивидуальный тариф компании уходит в расчёт, а не стандартный."""
    c = _container(comp_entry_fee=50.0, comp_free_days=0,
                   comp_storage_rate=10.0, comp_storage_period_days=1)
    path = build_csv_report([c], SETTINGS, tmp_path, "r.csv")
    rows = _read_rows(path)
    # 64 платных дня × 10$ = 640$, вход 50$, итого 690$
    assert rows[1][7:] == ["50,00", "640,00", "690,00"]


def test_creates_out_dir_and_returns_path(tmp_path):
    out_dir = tmp_path / "sub" / "dir"
    path = build_csv_report([], SETTINGS, out_dir, "r.csv")
    assert path == out_dir / "r.csv"
    assert path.exists()
